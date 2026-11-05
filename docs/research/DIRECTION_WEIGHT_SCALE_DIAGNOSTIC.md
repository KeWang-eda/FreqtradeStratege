# Recency-weight scale diagnostic

## Hypothesis

FreqAI's `weight_factor=0.9` determines the relative recency weights.  The
remaining unresolved question was whether the absolute sum of those weights
interacts with XGBoost's fixed `reg_lambda` and changes the effective
regularization.  This is distinct from testing another recency factor: the
candidate divides the exact same weight vector by its training mean, so every
new/old weight ratio is unchanged.

The mechanism follows FreqAI's exponential recent-sample weighting and
XGBoost's regularized weighted objective (Chen & Guestrin, 2016,
<https://arxiv.org/abs/1603.02754>; XGBoost parameter reference,
<https://xgboost.readthedocs.io/en/stable/parameter.html>).  It is an
exploratory historical test, not evidence that the references guarantee a
gain here.

## Controlled comparison

The baseline and candidate used identical relative weights, rows, labels,
features, three purged walk-forward folds, inner validation, seed, thread
count, XGBoost parameters, blend settings and prediction calibration.  The
candidate alone enabled `normalize_sample_weight: true`.  The prediction
files contain the same 28,401 development samples.

| arm | direction accuracy | fold 0 | fold 1 | fold 2 |
|---|---:|---:|---:|---:|
| current scale | 50.9102% | 49.3557% | 51.4998% | 51.8753% |
| mean-normalized scale | 50.9947% | 49.3663% | 51.6054% | 52.0127% |

The point difference is `+0.0845pp` (24 additional correct predictions),
below the predeclared `+0.25pp` gate.  The synchronized 4-day block bootstrap
(2,000 draws, seed 42) gives `[-0.0916pp, +0.2596pp]`, which crosses zero.
The candidate therefore does not demonstrate a reliable direction-accuracy
gain and is rejected for production.  The `normalize_sample_weight` switch
remains an explicit research-only option with default `false`; no production
configuration is changed.

The experiment entry points are
`configs/experiments/l1-weight-scale-baseline.yaml` and
`configs/experiments/l1-weight-scale-control.yaml`, with outputs under
`artifacts/experiments/l1-weight-scale-{baseline,normalized}`.
