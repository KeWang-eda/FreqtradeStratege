"""Development-fold test of causal one-bar return scaled by ATR(14)."""
from pathlib import Path
import json, joblib, numpy as np, pandas as pd
from xgboost import XGBRegressor
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def add(frame, symbol):
    frame=frame.copy(); r=next(c for c in frame if c.startswith(f"%-return_gen_{symbol}/USDTUSDT_4h")); a=next(c for c in frame if c.startswith(f"%-atr-ratio-period_14_{symbol}/USDTUSDT_4h")); frame[f"%-return-atr14_{symbol}"]=frame[r]/frame[a].replace(0,np.nan); return frame

def run(output):
    rows=[]; root=Path('artifacts/direction-threshold-study/rolling'); ext=Path('artifacts/direction-threshold-study/extended')
    for wd in sorted((p for p in root.glob('week-*') if p.is_dir()),key=lambda p:int(p.name.split('-')[1])):
        week=int(wd.name.split('-')[1])
        for md_dir in sorted((wd/'userdir/models').glob('*/sub-train-*')):
            symbol=md_dir.name.split('-')[2].split('_')[0]; md=json.loads(next(md_dir.glob('*_metadata.json')).read_text()); audit=next((md_dir/'native_training_audit').glob('*')); tr=add(pd.read_parquet(audit/'train_after_preprocessing.parquet'),symbol); va=add(pd.read_parquet(audit/'test_after_preprocessing.parquet'),symbol); base=md['training_features_list']; candidate=f"%-return-atr14_{symbol}"; cols=base+[candidate]; label=md['label_list'][0]; lp=joblib.load(next(md_dir.glob('*_label_pipeline.pkl'))); ytr=lp.inverse_transform(tr[[label]])[0].iloc[:,0].to_numpy(float); yv=lp.inverse_transform(va[[label]])[0].iloc[:,0].to_numpy(float); orig=joblib.load(next(md_dir.glob('*_model.joblib'))); params=orig.get_params(); params.update(n_estimators=300,early_stopping_rounds=30,n_jobs=1); params.pop('eval_metric',None); model=XGBRegressor(**params,eval_metric='rmse'); model.fit(tr[cols],ytr,sample_weight=tr.sample_weight.to_numpy(),eval_set=[(va[cols],yv)],sample_weight_eval_set=[va.sample_weight.to_numpy()],verbose=False); pred=add(pd.read_parquet(md_dir/'populated_prediction.parquet'),symbol).iloc[:42]; p=model.predict(pred[cols]); bt=pd.read_parquet(ext/f'20260101-{symbol}.parquet'); bt=bt[bt.new].copy(); dates=pd.date_range(pd.Timestamp('2026-01-01',tz='UTC')+pd.Timedelta(days=7*(week-1)),periods=42,freq='4h',tz='UTC'); truth=bt.set_index('date').loc[dates,'truth'].to_numpy(float); rows += [{'week':week,'pair':symbol,'date':str(d),'truth':float(t),'prediction':float(q),'correct':bool(np.sign(q)==np.sign(t))} for d,t,q in zip(dates,truth,p)]
    out=pd.DataFrame(rows); out.to_parquet(output/'predictions.parquet',index=False); print('accuracy',out.correct.mean(),len(out)); print(out.groupby(['week','pair']).correct.mean().to_string())
if __name__=='__main__':
 import argparse; p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False); run(a.output)
