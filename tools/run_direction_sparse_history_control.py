"""Fixed-span, fixed-tree supervised thinning; one diagnostic, not a sweep."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

from quant.infrastructure.experiment_store import file_hash
from quant.models.native_direction import NativeDirectionLearner


def mature_rows(rows,samples,available):
    ends=pd.to_datetime(samples.loc[rows.index,'label_end_time'],utc=True)
    return rows.loc[ends<available]


def sparse_positions(n,size=344):
    if n<size or size<2:
        raise ValueError('Need at least size>=2 chronologically ordered training rows')
    positions=np.rint(np.linspace(0,n-1,size)).astype(int)
    if len(np.unique(positions))!=size:
        raise ValueError('Nonunique training positions')
    return positions


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    source=Path('artifacts/native-direction-audit/seed-control-inner')
    config=json.loads(Path('config.json').read_text())
    period=json.loads((source/'protocol.json').read_text())['source_period']
    root=Path('artifacts/native-prediction-study/runs')/period
    report=json.loads((root/'training_run.json').read_text())
    protocol={'question':'does sparse supervised sampling over same historical span alter fold2 direction performance?',
        'selection':'344 indices rint(linspace(0,1041,344)); no label-based selection; fold2 only',
        'fixed':'saved1042-gradient-train pipeline, native DI, original weight subset, seed0, tree count selected by full reference',
        'tree_count_limit':'candidate does not select own trees; full baseline validation-selected budget held fixed',
        'scope':'reused single-fold mechanism diagnostic, not three-fold admission or production confirmation',
        'confounding':'changes label overlap/effective size and total weights relative to regularization; not pure n causal effect',
        'reference':'https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.learning_curve.html',
        'source_sha256':file_hash(source/'predictions.parquet'),
        'config_sha256':file_hash(Path('config.json'))}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2))
    prior=pd.read_parquet(source/'predictions.parquet')
    rows=[];audits=[]
    for info in report['pairs']:
        pair=info['pair'];symbol=pair.split('/')[0]
        directory=root/info['model_directory']
        md=json.loads(next(directory.glob('*metadata.json')).read_text())
        audit=directory/md['native_training_audit']
        raw=pd.read_parquet(audit/'train_before_preprocessing.parquet')
        sample=pd.read_parquet(audit/'samples.parquet');sample.index=sample.source_index.astype(int)
        raw=raw.loc[sample.loc[raw.index].sort_values('candle_timestamp').index]
        quarters=np.array_split(np.arange(len(raw)),4)
        test=raw.iloc[quarters[3]]
        past=mature_rows(raw.iloc[np.concatenate(quarters[:3])],sample,sample.loc[test.index,'available_at'].min())
        past=past.assign(sample_weight=FreqaiDataKitchen.set_weights_higher_recent(SimpleNamespace(config=config),len(past)))
        boundary=int(len(past)*.8);valid=past.iloc[boundary:]
        train=mature_rows(past.iloc[:boundary],sample,sample.loc[valid.index,'available_at'].min())
        assert len(train)==1042
        pipeline_path=source/f'{symbol}-fold2-pipeline.joblib'
        fp=joblib.load(pipeline_path);identity=file_hash(pipeline_path)
        assert fp.fit_indices.equals(train.index)
        X,y,w=fp.transform(train[md['training_features_list']],train[[md['label_list'][0]]],train.sample_weight.to_numpy())
        T,ready,_=fp.transform(test[md['training_features_list']],outlier_check=True)
        baseline=NativeDirectionLearner.load(source/f'{symbol}-fold2-seed0-learner.joblib',preprocessing_id=identity)
        base=baseline.predict_margin(T,preprocessing_id=identity)
        p=f'{period}-fold2'
        old=prior[(prior.period==p)&(prior.pair==pair)&(prior.arm=='seed_0')].set_index('date').loc[pd.DatetimeIndex(sample.loc[test.index,'candle_timestamp'])]
        np.testing.assert_array_equal(base,old.prediction)
        np.testing.assert_array_equal(test[md['label_list'][0]],old.truth)
        np.testing.assert_array_equal(ready,old.ready)
        selected=sparse_positions(len(X))
        params=dict(baseline.params)
        params.pop('early_stopping_rounds',None);params.pop('callbacks',None)
        params['n_estimators']=baseline.estimator.get_booster().num_boosted_rounds()
        model=xgb.XGBClassifier(**params)
        binary=(y.iloc[:,0]>0).astype(int)
        model.fit(X.iloc[selected],binary.iloc[selected],sample_weight=np.asarray(w)[selected],verbose=False)
        score=2*model.predict_proba(T)[:,1]-1
        path=output/f'{symbol}-model.joblib';joblib.dump(model,path)
        np.testing.assert_array_equal(score,2*joblib.load(path).predict_proba(T)[:,1]-1)
        for j,idx in enumerate(test.index):
            for arm,value in [('base',base[j]),('sparse',score[j])]:
                rows.append({'period':p,'pair':pair,'date':sample.loc[idx,'candle_timestamp'],
                    'truth':float(test.loc[idx,md['label_list'][0]]),'prediction':float(value),'ready':int(ready[j]),'arm':arm})
        audits.append({'pair':pair,'full_n':len(X),'sparse_n':len(selected),'trees':params['n_estimators'],
            'pipeline_sha256':identity,'model_sha256':file_hash(path),'selected_source_indices':X.index[selected].tolist(),
            'full_weight_sum':float(np.asarray(w).sum()),'sparse_weight_sum':float(np.asarray(w)[selected].sum()),
            'full_positive':float(binary.mean()),'sparse_positive':float(binary.iloc[selected].mean()),
            'first_index':int(X.index[0]),'last_index':int(X.index[-1])})
        print(pair,'completed',flush=True)
    d=pd.DataFrame(rows);d.to_parquet(output/'predictions.parquet',index=False)
    (output/'audit.json').write_text(json.dumps(audits,indent=2))
    d['correct']=np.sign(d.prediction)==np.sign(d.truth)
    print(d[d.ready==1].groupby('arm').correct.agg(['sum','size','mean']).to_string())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('artifacts/native-direction-audit/sparse-history-control'))
    args=parser.parse_args();run(args.output)
