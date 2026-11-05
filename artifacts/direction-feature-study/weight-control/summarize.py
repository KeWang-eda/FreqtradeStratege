from pathlib import Path
import pandas as pd,numpy as np,json
p=Path('artifacts/direction-feature-study/weight-control/predictions.parquet');d=pd.read_parquet(p);key=['fold','date','pair'];base=d[d.arm=='weighted'].set_index(key).sort_index();truth=np.sign(base.truth);scores={}
for arm in ['weighted','unweighted']:
    x=d[d.arm==arm].set_index(key).sort_index(); assert x.index.equals(base.index)
    scores[arm]=(x.pred.to_numpy()==truth.to_numpy()).astype(float)
a=scores['weighted'];b=scores['unweighted'];delta=b-a;g=pd.Series(delta,index=base.index).groupby(['fold','date']).mean();r={'weighted':float(a.mean()),'unweighted':float(b.mean()),'delta':float(delta.mean()),'gained':int((delta>0).sum()),'lost':int((delta<0).sum())};rng=np.random.default_rng(42)
for block in [6,12,24]:
 vals=[]
 for _ in range(5000):
  draw=[]
  for fold in range(3):
   x=g.loc[fold].to_numpy();st=rng.integers(len(x),size=int(np.ceil(len(x)/block)));ix=((st[:,None]+np.arange(block))%len(x)).ravel()[:len(x)];draw.extend(x[ix])
  vals.append(np.mean(draw))
 r[str(block)]=np.quantile(vals,[.025,.975]).tolist()
print(r);Path('artifacts/direction-feature-study/weight-control/summary.json').write_text(json.dumps(r,indent=2))
