# Direction-classifier final-tail comparison

The current production research configuration optimizes a continuous
volatility-normalized return with RMSE, while the selected primary metric is
direction accuracy.  Based on XGBoost's objective definitions and the standard
distinction between regression loss and classification loss, I predeclared one
single intervention: replace the regression estimator with
`xgboost_direction` (`binary:logistic`, validation `logloss`).  Features,
chronological split, maturity purge, recency weighting, tree depth, learning
rate, regularization, seed and early stopping were held fixed.  No threshold
search or parameter search was performed.

The existing project-relative local research config contains BTC and ETH; this
comparison therefore covers those two pairs and 4,456 common final-tail rows.
The final tail is `2025-10-09 08:00 UTC` through `2026-10-15 12:00 UTC`.

| model | final-tail direction accuracy |
|---|---:|
| current regression/L1 candidate | 49.9776% |
| direction classifier | 49.8878% |

The classifier is `-0.0878pp` below the current candidate.  Per pair, BTC is
49.6409% and ETH 50.1346%; the regression candidate is BTC 49.9102% and ETH
50.0449%.  The candidate is rejected for this data split and no production
objective change is made.  The result is a direct check that aligning the loss
with the metric is not sufficient by itself.

Reproduction configuration: `configs/experiments/xgboost_direction_final.yaml`.
The run artifact is `artifacts/experiments/direction-final-holdout-v1`.
