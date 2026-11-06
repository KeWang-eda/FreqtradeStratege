# Binary hinge objective diagnostic

The direction head normally uses `binary:logistic` with weighted logloss.  This
diagnostic tested XGBoost's `binary:hinge` objective with `error`, motivated by
the distinction between probability losses and hard classification surrogate
losses (XGBoost parameter documentation; Bartlett, Jordan & McAuliffe, 2006,
*Convexity, classification, and risk bounds*).  The objective was the only
training change.  Features, labels, mature purged folds, native pipelines,
weights, seed, tree cap and decision semantics were held fixed.

On the three H10 inner forward folds (3,927 common ready rows), hinge scored
`2,021/3,927 = 51.464%` versus logistic seed-0 `1,953/3,927 = 49.732%`, a
point increase of `1.732pp`.  The paired fold changes were +11, +21 and +36
correct predictions (all three folds improved).

This is encouraging but does not pass the predeclared promotion gate: the
synchronized two-day block bootstrap (2,000 draws, seed 42) for the paired
direction difference is `[-0.614pp, +3.871pp]`, crossing zero.  The windows are
also historical development data already exposed during prior research.  Hinge
is therefore retained as a research candidate only; no production objective or
configuration is changed.

Implementation and output: `quant/models/native_direction.py`,
`quant/models/estimators.py`, `tools/run_native_direction_hinge_control.py`,
and `artifacts/native-direction-audit/hinge-control-v3/`.
