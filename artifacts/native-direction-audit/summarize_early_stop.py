"""Paired, synchronized date-block sensitivity; reused development only."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate', choices=['direction_error', 'l1', 'sigmoid', 'body_ablation', 'binary_objective', 'binary_logloss'], default='direction_error')
parser.add_argument('--baseline', default='rmse')
parser.add_argument('--directory', type=Path)
args = parser.parse_args()
candidate = args.candidate
default_directory = {'direction_error': 'early-stop-control', 'l1': 'l1-objective-control', 'sigmoid': 'score-sigmoid-control', 'body_ablation': 'body-feature-ablation', 'binary_objective': 'binary-objective-control', 'binary_logloss':'binary-logloss-control'}
out = args.directory or Path('artifacts/native-direction-audit') / default_directory[candidate]
d = pd.read_parquet(out / 'predictions.parquet')
keys = ['period', 'date', 'pair']
a = d[d.arm == args.baseline].set_index(keys).sort_index()
b = d[d.arm == candidate].set_index(keys).sort_index()
assert a.index.is_unique and a.index.equals(b.index)
assert np.array_equal(a.truth, b.truth)
assert np.array_equal(a.ready, b.ready)
scores = pd.DataFrame({
    'baseline': (np.sign(a.prediction) == np.sign(a.truth)).astype(int),
    'candidate': (np.sign(b.prediction) == np.sign(b.truth)).astype(int),
    'ready': a.ready,
})
scores['delta'] = scores.candidate - scores.baseline
result = {
    'baseline_arm': args.baseline, 'candidate_arm': candidate,
    'n': len(scores), 'coverage': float((scores.ready == 1).mean()),
    'overall': scores[['baseline', 'candidate', 'delta']].mean().to_dict(),
    'periods': scores.groupby('period')[['baseline', 'candidate', 'delta']].mean().to_dict('index'),
    'gained': int((scores.delta > 0).sum()), 'lost': int((scores.delta < 0).sum()),
    'date_block_ci95': {},
    'dates_per_period': scores.reset_index().groupby('period').date.nunique().to_dict(),
    'limitation': 'reused historical development; frozen-model window sensitivity, not untouched confirmation',
}
groups = [g.groupby('date').delta.mean().to_numpy() for _, g in scores.reset_index().groupby('period')]
for block in [6, 12, 24]:
    rng = np.random.default_rng(42)
    means = []
    for _ in range(5000):
        sampled = []
        for group in groups:
            starts = rng.integers(0, len(group), size=int(np.ceil(len(group) / block)))
            values = np.concatenate([group[(start + np.arange(block)) % len(group)] for start in starts])
            sampled.append(values[:len(group)])
        means.append(float(np.concatenate(sampled).mean()))
    result['date_block_ci95'][str(block)] = np.quantile(means, [.025, .975]).tolist()
(out / 'summary.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
