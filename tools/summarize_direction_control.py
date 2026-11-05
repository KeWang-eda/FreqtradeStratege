"""Paired direction controls with count-weighted synchronous date-block CIs."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from quant.infrastructure.experiment_store import file_hash


def compare(data,baseline,candidate,draws=5000):
    keys=['period','date','pair']
    a=data[data.arm==baseline].set_index(keys).sort_index()
    b=data[data.arm==candidate].set_index(keys).sort_index()
    if a.empty or not a.index.is_unique or not a.index.equals(b.index):
        raise ValueError('Missing, duplicated or unpaired direction predictions')
    if not np.isfinite(a[['truth','prediction']]).all().all() or not np.isfinite(b[['truth','prediction']]).all().all():
        raise ValueError('Nonfinite direction predictions/truth')
    np.testing.assert_array_equal(a.truth,b.truth)
    np.testing.assert_array_equal(a.ready,b.ready)
    if not a.ready.isin([0,1]).all():
        raise ValueError('Expected binary readiness for this isolated DI study')
    paired=pd.DataFrame({'baseline':(np.sign(a.prediction)==np.sign(a.truth)).astype(int),
                         'candidate':(np.sign(b.prediction)==np.sign(b.truth)).astype(int),'ready':a.ready})
    result={'baseline':baseline,'candidate':candidate,'all_n':len(paired),
            'ready_n':int(paired.ready.eq(1).sum()),'masks':{},
            'method':f'{draws} circular synchronous date-block draws within period/fold; seed42 per block; eligible-count ratio',
            'scope':'reused development; conditional fitted-model/coverage uncertainty, no cumulative selection correction'}
    for mask_name in ['all','ready']:
        scores=paired.reset_index().copy()
        eligible=np.ones(len(scores),dtype=bool) if mask_name=='all' else scores.ready.eq(1).to_numpy()
        covered=scores.loc[eligible]
        if covered.empty:
            raise ValueError('No eligible comparison rows')
        scores['n']=eligible.astype(int)
        scores['delta']=(scores.candidate-scores.baseline)*eligible
        folds=[{'period':period,'n':len(g),'baseline_correct':int(g.baseline.sum()),
                'candidate_correct':int(g.candidate.sum()),'delta':float((g.candidate-g.baseline).mean())}
               for period,g in covered.groupby('period')]
        groups=[g.groupby('date')[['delta','n']].sum().to_numpy() for _,g in scores.groupby('period')]
        ci={}
        for block in [6,12,24]:
            rng=np.random.default_rng(42)
            numerator,denominator=np.zeros(draws),np.zeros(draws)
            for values in groups:
                starts=rng.integers(0,len(values),size=(draws,int(np.ceil(len(values)/block))))
                indices=((starts[:,:,None]+np.arange(block))%len(values)).reshape(draws,-1)[:,:len(values)]
                sampled=values[indices]
                numerator+=sampled[:,:,0].sum(axis=1)
                denominator+=sampled[:,:,1].sum(axis=1)
            if not (denominator>0).all():
                raise ValueError('Bootstrap draw without eligible rows')
            ci[str(block)]=np.quantile(numerator/denominator,[.025,.975]).tolist()
        result['masks'][mask_name]={'n':len(covered),'baseline_correct':int(covered.baseline.sum()),
            'candidate_correct':int(covered.candidate.sum()),'delta':float((covered.candidate-covered.baseline).mean()),
            'gained':int((covered.candidate>covered.baseline).sum()),'lost':int((covered.candidate<covered.baseline).sum()),
            'folds':folds,'date_block_ci95':ci}
    primary=result['masks']['ready']
    # This gate was preregistered for exactly three training-internal folds.
    # Diagnostics may contain other counts, but they cannot silently inherit it.
    applicable=len(primary['folds'])==3
    result['gate_scope']={'expected_periods':3,'actual_periods':len(primary['folds']),
                          'applicable':applicable,'purpose':'development admission only'}
    result['production_eligible']=False
    result['external_gate_passed']=bool(applicable and primary['delta']>0 and sum(f['delta']>0 for f in primary['folds'])>=2
                                       and all(v[0]>0 for v in primary['date_block_ci95'].values()))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('artifacts/native-direction-audit/clv-control-inner'))
    parser.add_argument('--baseline',default='base')
    parser.add_argument('--candidate',default='clv')
    parser.add_argument('--summary',type=Path)
    args=parser.parse_args()
    result=compare(pd.read_parquet(args.directory/'predictions.parquet'),args.baseline,args.candidate)
    result['predictions_sha256']=file_hash(args.directory/'predictions.parquet')
    with (args.summary or args.directory/'summary.json').open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))
