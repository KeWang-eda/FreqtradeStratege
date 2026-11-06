# Existing-data final holdout audit

In response to the requirement to use the data already present in the
repository, the current lag-return production candidate was evaluated on the
pre-existing reserved tail.  This is a prediction evaluation only; no trading
backtest was run and no model parameter was selected from the result.

The command used the repository-relative data paths, the current feature
pipeline, the configured XGBoost/L1 model, chronological folds, and the
project's label maturity purge:

```sh
conda run -n quant python -m quant.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  -c configs/estimators/xgboost_blend_l1.yaml \
  --output artifacts/experiments \
  --experiment-id current-lag-final-holdout-v2 \
  --evaluate-final-holdout
```

The reserved interval is `2025-10-09 08:00 UTC` through
`2026-10-15 12:00 UTC`, with 4,456 complete samples.  The candidate's
direction accuracy is `49.9776%`.  The deployable constant-direction
reference selected from the same evaluated truth is `50.3815%`; the candidate
is therefore `-0.4039pp` below that reference.  Development accuracy in the
same run is `50.5440%`, so development performance did not transfer to the
reserved tail.

This confirms the earlier warning about relying on reused development
windows: the lag feature promotion was an exploratory historical gain, not a
confirmed final-holdout improvement.  The result does not justify another
feature or threshold search on this holdout.  The holdout remains scored once
for this audit and is excluded from further candidate selection.
