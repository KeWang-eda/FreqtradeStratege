"""Grouped validation permutation diagnostic for all feature families."""
import argparse, json
from pathlib import Path
import joblib, numpy as np, pandas as pd

FAMILIES = {
    "atr":"atr-ratio", "rsi":"rsi", "ema":"ema-distance", "sma":"sma-distance",
    "momentum":"momentum", "relative-volume":"relative-volume", "volume-change":"volume-change",
    "return":"return", "body":"body", "range":"range", "volatility":"volatility",
    "calendar":"hour|day-of-week", "lag-return":"lag-return",
}
def fam(c):
    for k,v in FAMILIES.items():
        if any(x in c for x in v.split('|')): return k
    return 'other'
def run(root, output, repeats=20):
    output.mkdir(parents=True, exist_ok=False); rows=[]; rng=np.random.default_rng(42)
    for md_dir in sorted(root.glob('week-*/userdir/models/*/sub-train-*')):
        meta=json.loads(next(md_dir.glob('*metadata.json')).read_text()); audit=next((md_dir/'native_training_audit').glob('*'))
        valid=pd.read_parquet(audit/'test_after_preprocessing.parquet'); label=meta['label_list'][0]; cols=meta['training_features_list']
        model=joblib.load(next(md_dir.glob('*model.joblib'))); y=valid[label].to_numpy(); X=valid[cols].copy(); base=np.sign(model.predict(X))==np.sign(y)
        groups={k:[i for i,c in enumerate(cols) if fam(c)==k] for k in FAMILIES}; groups={k:v for k,v in groups.items() if v}
        for name,idx in groups.items():
            scores=[]
            for _ in range(repeats):
                xp=X.copy(); order=rng.permutation(len(X)); xp.iloc[:,idx]=X.iloc[order,idx].to_numpy(); scores.append(float((np.sign(model.predict(xp))==np.sign(y)).mean()))
            rows.append({'week':md_dir.parts[-4],'pair':meta.get('pair',md_dir.name),'family':name,'n_features':len(idx),'baseline_accuracy':float(base.mean()),'permuted_accuracy_mean':float(np.mean(scores)),'delta_mean':float(np.mean(scores)-base.mean()),'delta_q025':float(np.quantile(np.array(scores)-base.mean(),.025)),'delta_q975':float(np.quantile(np.array(scores)-base.mean(),.975))})
    pd.DataFrame(rows).to_csv(output/'group_permutation.csv',index=False); print(pd.DataFrame(rows).groupby('family').delta_mean.mean().sort_values())
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path('artifacts/direction-threshold-study/rolling')); p.add_argument('--output',type=Path,default=Path('artifacts/direction-threshold-study/group-permutation-v1')); a=p.parse_args(); run(a.root,a.output)
