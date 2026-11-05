"""Prediction-only controls using saved native preprocessing and model snapshots.

Run from the project root with conda quant. Inputs and outputs default to
project-relative locations. No trading simulation or production config edit.
"""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from quant.infrastructure.experiment_store import file_hash
from quant.market_data import load_ohlcv
from quant.models.native_direction import NativeDirectionLearner
from quant.validation.native_features import populate_native_features

ROOT = Path('artifacts/native-prediction-study/runs')
SOURCE = Path('artifacts/native-direction-audit/l1-extended-prediction/predictions.parquet')


def main(output, candidate='binary_logloss', source=SOURCE, config_path=Path('config.json')):
    output.mkdir(parents=True, exist_ok=False)
    protocol = {
        'hypothesis': 'near duplicate candle body and close return inputs impair direction generalization',
        'selection': 'remove all %-body_gen columns from learner only; keep return and all other inputs',
        'fixed': 'saved native train/validation rows, preprocessing, DI, labels, weights, params, RMSE early stopping30',
        'scope': 'reused historical frozen-model development; no untouched holdout or daily live retrain',
        'effect': 'complete learner feature-set ablation, including changed colsample paths; not isolated microstructure effect',
        'threshold': 'zero in original label units',
        'magnitude_calibration': 'omitted from both arms because native positive power preserves sign',
        'reference': 'https://xgboost.readthedocs.io/en/stable/parameter.html#parameters-for-tree-booster',
        'source': str(source),
        'config_path': str(config_path),
        'config_sha256': file_hash(config_path),
        'promotion': 'requires stable paired direction gain; correlation alone is insufficient',
    }
    if candidate in {'binary_objective', 'binary_logloss'}:
        protocol.update({
            'hypothesis': 'conditional mean sign need not equal the most probable future direction',
            'selection': 'all original native features kept; binary label is original y>0',
            'change': 'native-feature binary logistic learner instead of squared-error regression',
            'fixed': 'native feature/label provenance, train rows, weights, other params, tree count from saved regression',
            'tree_selection': 'n_estimators=saved native regression num_boosted_rounds; no candidate early stopping or search',
            'threshold': 'P(y>0)=0.5; score is direction margin 2*p-1, NOT volnorm return',
            'reference': 'https://xgboost.readthedocs.io/en/stable/parameter.html#learning-task-parameters',
            'effect': 'task-aligned learner with fixed tree budget; loss/label/output are coupled changes, not feature ablation',
        })
    if candidate == 'binary_logloss':
        protocol.update({
            'hypothesis': 'regression-selected tree budget limits the native binary learner',
            'change': 'fixed native binary trees to own weighted validation logloss early stopping',
            'fixed': 'binary objective, original native train/validation rows, weights, features, threshold0.5, other params',
            'tree_selection': 'max300; weighted validation logloss; patience30; fresh save_best callback',
            'primary_baseline': 'fixed_binary; regression rmse retained only as anchor',
            'scope': 'mechanism test on previously reused historical windows; not fresh confirmation',
            'effect': 'only tree selection differs from fixed_binary; binary loss, labels and direction_margin unchanged',
        })
    (output/'protocol.json').write_text(json.dumps(protocol, indent=2))
    expected = pd.read_parquet(source)
    expected = expected[expected.arm == 'rmse'].copy()
    config = json.loads(config_path.read_text())
    pairs = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT']
    frames = {p: load_ohlcv(Path(config.get('datadir', 'data'))/'futures'/(p.replace('/', '_').replace(':', '_')+'-4h-futures.feather')) for p in pairs}
    rows, audits, redundancy = [], [], []
    for period in sorted(expected.period.unique()):
        report = json.loads((ROOT/period/'training_run.json').read_text())
        for info in report['pairs']:
            pair = info['pair']
            directory = ROOT/period/info['model_directory']
            md = json.loads(next(directory.glob('*metadata.json')).read_text())
            label = md['label_list'][0]
            audit = directory/md['native_training_audit']
            train = pd.read_parquet(audit/'train_after_preprocessing.parquet')
            valid = pd.read_parquet(audit/'test_after_preprocessing.parquet')
            raw = pd.read_parquet(audit/'train_before_preprocessing.parquet')
            raw_valid = pd.read_parquet(audit/'test_before_preprocessing.parquet')
            saved = joblib.load(next(directory.glob('*model.joblib')))
            fp = joblib.load(next(directory.glob('*feature_pipeline.pkl')))
            lp = joblib.load(next(directory.glob('*label_pipeline.pkl')))
            all_features = list(saved.get_booster().feature_names)
            removed = [c for c in all_features if c.startswith('%-body_gen')] if candidate == 'body_ablation' else []
            if candidate == 'body_ablation':
                assert len(removed) == (6 if pair.startswith('BNB') else 4)
            selected = [c for c in all_features if c not in removed]
            for body in removed:
                ret = body.replace('%-body_gen', '%-return_gen', 1)
                assert ret in selected
                redundancy.append({'period': period, 'pair': pair, 'body': body, 'return': ret,
                                   'train_correlation': float(raw[body].corr(raw[ret])),
                                   'equal_fraction': float((raw[body] == raw[ret]).mean()),
                                   'max_absolute_difference': float((raw[body]-raw[ret]).abs().max())})
            current = expected[(expected.period == period) & (expected.pair == pair)].sort_values('date')
            start = pd.Timestamp(info['training_start']) - pd.Timedelta(hours=400)
            end = current.date.max() + pd.Timedelta(hours=16)
            sources = {p: f[(f.date >= start) & (f.date < end)].copy() for p, f in frames.items()}
            populated = populate_native_features(config, sources, pair).set_index('date')
            prediction = populated.loc[current.date].copy()
            assert np.array_equal(prediction[label].to_numpy(), current.truth.to_numpy())
            transformed, ready, _ = fp.transform(prediction[md['training_features_list']], outlier_check=True)
            assert np.array_equal(np.asarray(ready), current.ready.to_numpy())

            def inverse(values):
                frame = pd.DataFrame(np.asarray(values).reshape(-1, 1), columns=[label])
                result, _, _ = lp.inverse_transform(frame)
                return result[label].to_numpy()

            baseline = inverse(saved.predict(transformed[all_features]))
            assert np.allclose(baseline, current.prediction.to_numpy(), rtol=1e-6, atol=1e-7)
            assert np.array_equal(np.sign(baseline), np.sign(current.prediction.to_numpy()))
            params = saved.get_params().copy()
            params.pop('callbacks', None)
            params.pop('early_stopping_rounds', None)
            fixed_prediction = None
            if candidate in {'binary_objective', 'binary_logloss'}:
                params.update(objective='binary:logistic', eval_metric='logloss',
                              n_estimators=300 if candidate == 'binary_logloss' else saved.get_booster().num_boosted_rounds())
                if candidate == 'binary_logloss':
                    valid_y = raw_valid.loc[valid.index, label].to_numpy()
                    assert np.isfinite(valid_y).all()
                    reference_stage = 'binary-objective-replication' if 'direction-confirm' in period else 'binary-objective-control'
                    ref_path = Path('artifacts/native-direction-audit')/reference_stage/f"{period}-{pair.split('/')[0]}-model.joblib"
                    fixed = joblib.load(ref_path)
                    assert fixed.get_booster().feature_names == selected
                    assert fixed.get_booster().num_boosted_rounds() == saved.get_booster().num_boosted_rounds()
                    fixed_prediction = 2 * fixed.predict_proba(transformed[selected])[:, 1] - 1
                original_y = raw.loc[train.index, label].to_numpy()
                assert np.isfinite(original_y).all()
                if candidate == 'binary_logloss':
                    identity = file_hash(next(directory.glob('*feature_pipeline.pkl')))
                    learner = NativeDirectionLearner(preprocessing_id=identity, params=params)
                    learner.fit_preprocessed(
                        train[selected], raw.loc[train.index, label],
                        validation_features=valid[selected], validation_returns=raw_valid.loc[valid.index, label],
                        sample_weight=train.sample_weight, validation_weight=valid.sample_weight,
                    )
                    candidate_prediction = learner.predict_margin(transformed[selected], preprocessing_id=identity)
                    learner_path = output/f"{period}-{pair.split('/')[0]}-learner.joblib"
                    learner.save(learner_path)
                    restored = NativeDirectionLearner.load(learner_path, preprocessing_id=identity)
                    assert np.array_equal(candidate_prediction,
                                          restored.predict_margin(transformed[selected], preprocessing_id=identity))
                    model = learner.estimator
                else:
                    model = xgb.XGBClassifier(**params)
                    model.fit(train[selected], (original_y > 0).astype(int), sample_weight=train.sample_weight, verbose=False)
                    candidate_prediction = 2 * model.predict_proba(transformed[selected])[:, 1] - 1
            else:
                params['callbacks'] = [xgb.callback.EarlyStopping(rounds=30, save_best=True, maximize=False,
                                                                  data_name='validation_0', metric_name='rmse')]
                model = xgb.XGBRegressor(**params)
                model.fit(train[selected], train[label], sample_weight=train.sample_weight,
                          eval_set=[(valid[selected], valid[label])],
                          sample_weight_eval_set=[valid.sample_weight.to_numpy()], verbose=False)
                candidate_prediction = inverse(model.predict(transformed[selected]))
            joblib.dump(model, output/f"{period}-{pair.split('/')[0]}-model.joblib")
            for i, (_, row) in enumerate(current.iterrows()):
                arm_values = [('rmse', baseline[i]), (candidate, candidate_prediction[i])]
                if fixed_prediction is not None:
                    arm_values.append(('fixed_binary', fixed_prediction[i]))
                for arm, pred in arm_values:
                    rows.append({'period': period, 'pair': pair, 'date': row.date, 'arm': arm,
                                 'truth': float(row.truth), 'prediction': float(pred), 'ready': int(row.ready),
                                 'prediction_kind': 'direction_margin' if arm in {'binary_objective', 'binary_logloss', 'fixed_binary'} else 'volnorm_return'})
            audits.append({'period': period, 'pair': pair, 'train_n': len(train), 'valid_n': len(valid),
                           'future_n': len(current), 'removed': removed, 'selected_n': len(selected),
                           'baseline_best_iteration': saved.best_iteration,
                           'candidate_rounds': model.get_booster().num_boosted_rounds(),
                           'candidate_best_iteration': None if candidate == 'binary_objective' else model.best_iteration,
                           'validation_metric': model.get_params()['eval_metric'],
                           'baseline_replay_max_error': float(np.max(np.abs(baseline-current.prediction.to_numpy())))})
            print(period, pair, 'completed', flush=True)
    pd.DataFrame(rows).to_parquet(output/'predictions.parquet', index=False)
    (output/'audit.json').write_text(json.dumps(audits, indent=2))
    (output/'redundancy.json').write_text(json.dumps(redundancy, indent=2))
    d = pd.DataFrame(rows)
    d['correct'] = np.sign(d.prediction) == np.sign(d.truth)
    print(d.groupby(['period', 'arm']).correct.mean().to_string())
    print(d.groupby('arm').correct.agg(['mean','size','sum']).to_string())


def cli(default_candidate='binary_logloss'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', choices=['body_ablation', 'binary_objective', 'binary_logloss'], default=default_candidate)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--config', type=Path, default=Path('config.json'))
    args = parser.parse_args()
    default_directory = {'body_ablation':'body-feature-ablation', 'binary_objective':'binary-objective-control', 'binary_logloss':'binary-logloss-control'}[args.candidate]
    main(args.output or Path('artifacts/native-direction-audit')/default_directory, args.candidate, args.source, args.config)


if __name__ == '__main__':
    cli()
