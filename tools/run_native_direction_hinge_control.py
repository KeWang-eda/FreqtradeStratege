"""H10 training-internal seed probability ensemble with fresh native pipelines."""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.freqai_interface import IFreqaiModel

from quant.infrastructure.experiment_store import file_hash
from quant.models.native_direction import NativeDirectionLearner
from quant.training.native_isolation import IdentityPreservingPipeline, validate_native_config


SEEDS = (0,)


def probability_mean(probabilities):
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[0] != len(SEEDS) or not values.shape[1]:
        raise ValueError('Expected five aligned probability members')
    if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError('Invalid member probabilities')
    return values.mean(axis=0)


def mature_rows(rows, samples, available):
    times = pd.to_datetime(samples.loc[rows.index, 'label_end_time'], utc=True)
    return rows.loc[times < available]


def run(output, config_path):
    output.mkdir(parents=True, exist_ok=False)
    source_period = 'base-20240701-direction-confirm1'
    root = Path('artifacts/native-prediction-study/runs') / source_period
    source_head = Path('artifacts/native-direction-audit/binary-logloss-learner-replication')
    report = json.loads((root/'training_run.json').read_text())
    config = json.loads(config_path.read_text())
    validate_native_config(config)
    protocol = {
        'hypothesis': 'randomized row/column sampling creates unstable direction boundaries; fixed probability averaging may help',
        'source_period': source_period, 'source': 'retained train_before_preprocessing ONLY; no external forecast/validation labels',
        'seeds': list(SEEDS), 'baseline': 'seed_0', 'candidate': 'binary_hinge',
        'seed_identity': 'saved H8 random_state=None resolves to Booster seed0; data_split seed42 is not tree seed',
        'folds': 'four consecutive training quarters; first1/2/3 predict next; chronological inner20% early stopping',
        'purge': 'outer past and inner train require label_end strictly before next available_at',
        'pipeline': 'fresh official native factory per fold, fit only inner gradient training; no full-window variance filtering',
        'weights': 'official FreqAI formula rebuilt per available mature history before inner split/purge',
        'early_stopping': 'each member own weighted logloss patience30 cap300; differing selected tree counts included in intervention',
        'decision': 'arithmetic mean probabilities; margin2p-1; threshold0.5; sign0 retained; no voting or seed selection',
        'primary_mask': 'common native DI ready==1; also report all rows and coverage; never count not-ready as errors',
        'gate': 'positive pooled primary delta, >=2 of3 fold deltas positive, all6/12/24 date-block95 lower bounds>0 before external runs',
        'scope': 'training-internal exploratory evidence on previously studied historical window; not independent confirmation',
        'prior_negative': '2026-10-30 standalone regression seed ensemble failed; this is binary probability with native fold preprocessing',
        'reference': 'Breiman1996 Bagging Predictors DOI10.1007/BF00058655; seed ensemble is not independent bootstrap bagging',
        'config':str(config_path), 'config_sha256':file_hash(config_path),
        'report_sha256':file_hash(root/'training_run.json'),
    }
    (output/'protocol.json').write_text(json.dumps(protocol, indent=2))
    rows, audits = [], []
    for info in report['pairs']:
        pair = info['pair']
        symbol = pair.split('/')[0]
        directory = root/info['model_directory']
        md = json.loads(next(directory.glob('*metadata.json')).read_text())
        audit = directory/md['native_training_audit']
        path = audit/'train_before_preprocessing.parquet'
        raw = pd.read_parquet(path)
        sample = pd.read_parquet(audit/'samples.parquet')
        sample.index = sample.source_index.astype(int)
        assert sample.index.is_unique and raw.index.is_unique
        order = sample.loc[raw.index].sort_values('candle_timestamp').index
        raw = raw.loc[order]
        features = md['training_features_list']  # before any fitted variance filter
        assert set(features) == {c for c in raw.columns if c.startswith('%')}
        label = md['label_list'][0]
        old_identity = file_hash(next(directory.glob('*feature_pipeline.pkl')))
        original = NativeDirectionLearner.load(source_head/f'{source_period}-{symbol}-learner.joblib', preprocessing_id=old_identity)
        actual_seed = json.loads(original.estimator.get_booster().save_config())['learner']['generic_param']['seed']
        assert actual_seed == '0'
        quarters = np.array_split(np.arange(len(raw)),4)
        for fold in range(3):
            test = raw.iloc[quarters[fold+1]]
            outer_available = pd.Timestamp(sample.loc[test.index,'available_at'].min())
            past = raw.iloc[np.concatenate(quarters[:fold+1])]
            past = mature_rows(past, sample, outer_available)
            weights = FreqaiDataKitchen.set_weights_higher_recent(SimpleNamespace(config=config), len(past))
            past = past.assign(sample_weight=weights)
            boundary = int(len(past)*.8)
            valid = past.iloc[boundary:]
            inner_available = pd.Timestamp(sample.loc[valid.index,'available_at'].min())
            train = mature_rows(past.iloc[:boundary], sample, inner_available)
            factory = IFreqaiModel.define_data_pipeline(SimpleNamespace(freqai_info=config['freqai']), threads=1)
            pipeline = IdentityPreservingPipeline(factory.steps, factory.fitparams)
            X, y, w = pipeline.fit_transform(train[features], train[[label]], train.sample_weight.to_numpy())
            pipeline_path = output/f'{symbol}-fold{fold}-pipeline.joblib'
            joblib.dump(pipeline,pipeline_path)
            identity = file_hash(pipeline_path)
            V, vy, vw = pipeline.transform(valid[features],valid[[label]],valid.sample_weight.to_numpy())
            T, ready, _ = pipeline.transform(test[features],outlier_check=True)
            assert T.index.equals(test.index) and len(ready)==len(test)
            assert np.isfinite(T.to_numpy()).all() and len(V)>0
            probabilities, rounds = [], []
            for seed in SEEDS:
                params = {**original.params, 'random_state':seed, 'objective':'binary:hinge', 'eval_metric':'error'}
                learner = NativeDirectionLearner(preprocessing_id=identity, params=params,
                                                 early_stopping_rounds=original.early_stopping_rounds)
                learner.fit_preprocessed(X,y[label],validation_features=V,validation_returns=vy[label],
                    sample_weight=pd.Series(w,index=X.index),validation_weight=pd.Series(vw,index=V.index))
                p = learner.predict_proba_up(T,preprocessing_id=identity)
                probabilities.append(p)
                rounds.append(learner.estimator.get_booster().num_boosted_rounds())
                learner.save(output/f'{symbol}-fold{fold}-seed{seed}-learner.joblib')
            probs = np.asarray(probabilities)
            ensemble = probability_mean(probs)
            disagreement = (np.sign(2*probs-1).max(axis=0) != np.sign(2*probs-1).min(axis=0))
            signs, counts = np.unique(np.sign(y[label]),return_counts=True)
            majority = int(signs[np.argmax(counts)])
            for i, idx in enumerate(test.index):
                values = [(f'seed_{seed}',float(2*probs[j,i]-1)) for j,seed in enumerate(SEEDS)]
                values += [('seed_ensemble',float(2*ensemble[i]-1)),('train_majority',majority)]
                for arm,value in values:
                    rows.append({'period':f'{source_period}-fold{fold}','pair':pair,
                        'date':sample.loc[idx,'candle_timestamp'],'truth':float(test.loc[idx,label]),
                        'prediction':value,'ready':int(ready[i]),'arm':arm,
                        'prediction_kind':'direction_margin' if arm!='train_majority' else 'constant_direction'})
            audits.append({'source_period':source_period,'pair':pair,'fold':fold,
                'raw_train_sha256':file_hash(path), 'source_metadata_sha256':file_hash(next(directory.glob('*metadata.json'))),
                'train_n_before_preprocessing':len(train),'valid_n_before_preprocessing':len(valid),
                'train_n':len(X),'valid_n':len(V),'test_n':len(T),'ready_n':int((np.asarray(ready)==1).sum()),
                'outer_first_available':str(outer_available),'inner_first_available':str(inner_available),
                'last_train_label_end':str(sample.loc[X.index,'label_end_time'].max()),
                'last_valid_label_end':str(sample.loc[V.index,'label_end_time'].max()),
                'pipeline_sha256':identity,'feature_n':len(X.columns),'member_rounds':rounds,
                'disagreement_rate':float(disagreement.mean()),'mean_probability_std':float(probs.std(axis=0).mean())})
            print(pair,fold,'completed; disagreement',disagreement.mean(),flush=True)
    pd.DataFrame(rows).to_parquet(output/'predictions.parquet',index=False)
    (output/'audit.json').write_text(json.dumps(audits,indent=2,allow_nan=False))
    d = pd.DataFrame(rows)
    d['correct'] = np.sign(d.prediction)==np.sign(d.truth)
    print('All rows:\n',d.groupby('arm').correct.agg(['sum','size','mean']).to_string())
    print('Ready rows:\n',d[d.ready==1].groupby('arm').correct.agg(['sum','size','mean']).to_string())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('artifacts/native-direction-audit/seed-control-inner'))
    parser.add_argument('--config',type=Path,default=Path('config.json'))
    args=parser.parse_args()
    run(args.output,args.config)
