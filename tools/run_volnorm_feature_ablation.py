"""Add one causal momentum/ATR interaction to the frozen rolling folds."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json, joblib, numpy as np, pandas as pd
from xgboost import XGBRegressor

def add_ratio(frame, symbol):
    frame = frame.copy()
    for period in (6, 14, 24):
        m = next(c for c in frame if c.startswith(f"%-momentum-period_{period}_{symbol}/USDTUSDT_4h"))
        a = next(c for c in frame if c.startswith(f"%-atr-ratio-period_{period}_{symbol}/USDTUSDT_4h"))
        frame[f"%-volnorm-momentum-{period}_{symbol}"] = frame[m] / frame[a].replace(0, np.nan)
    return frame

def run(root, extended, output):
    rows=[]
    for week_dir in sorted((p for p in Path(root).glob('week-*') if p.is_dir()), key=lambda p:int(p.name.split('-')[1])):
        week=int(week_dir.name.split('-')[1])
        for model_dir in sorted((week_dir/'userdir/models').glob('*/sub-train-*')):
            symbol=model_dir.name.split('-')[2].split('_')[0]
            md=json.loads(next(model_dir.glob('*_metadata.json')).read_text()); audit=next((model_dir/'native_training_audit').glob('*'))
            train=add_ratio(pd.read_parquet(audit/'train_after_preprocessing.parquet'),symbol); valid=add_ratio(pd.read_parquet(audit/'test_after_preprocessing.parquet'),symbol)
            features=md['training_features_list']; candidate=[f'%-volnorm-momentum-{p}_{symbol}' for p in (6,14,24)]
            kept=features+candidate; label=md['label_list'][0]
            lp=joblib.load(next(model_dir.glob('*_label_pipeline.pkl')))
            ytr=lp.inverse_transform(train[[label]])[0].iloc[:,0].to_numpy(float); yv=lp.inverse_transform(valid[[label]])[0].iloc[:,0].to_numpy(float)
            original=joblib.load(next(model_dir.glob('*_model.joblib'))); params=original.get_params(); params.update(n_estimators=300,early_stopping_rounds=30,n_jobs=1); params.pop('eval_metric',None)
            model=XGBRegressor(**params,eval_metric='rmse'); model.fit(train[kept],ytr,sample_weight=train.sample_weight.to_numpy(),eval_set=[(valid[kept],yv)],sample_weight_eval_set=[valid.sample_weight.to_numpy()],verbose=False)
            pred=add_ratio(pd.read_parquet(model_dir/'populated_prediction.parquet'),symbol).iloc[:42]; p=model.predict(pred[kept])
            base=pd.read_parquet(Path(extended)/f'20260101-{symbol}.parquet'); base=base[base.new].copy(); dates=pd.date_range(pd.Timestamp('2026-01-01',tz='UTC')+pd.Timedelta(days=7*(week-1)),periods=42,freq='4h',tz='UTC'); truth=base.set_index('date').loc[dates,'truth'].to_numpy(float)
            rows.extend({'week':week,'pair':symbol,'date':str(d),'truth':float(t),'prediction':float(q),'correct':bool(np.sign(q)==np.sign(t))} for d,t,q in zip(dates,truth,p))
    out=pd.DataFrame(rows); out.to_parquet(output/'predictions.parquet',index=False); print(out.correct.mean(),len(out)); print(out.groupby(['week','pair']).correct.mean().to_string())
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path('artifacts/direction-threshold-study/rolling')); p.add_argument('--extended',type=Path,default=Path('artifacts/direction-threshold-study/extended')); p.add_argument('--output',type=Path,default=Path('artifacts/direction-threshold-study/volnorm-momentum-ablation')); a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False); run(a.root,a.extended,a.output)
