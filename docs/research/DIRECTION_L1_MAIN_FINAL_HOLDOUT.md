# Absolute-error main model on the reserved tail

The current model uses a squared-error primary XGBoost model plus an
absolute-error blend.  The single predeclared candidate made the primary
model itself use XGBoost `reg:absoluteerror`, leaving the blend weight,
features, labels, time splits, sample weights, calibration and early stopping
unchanged.  The basis is the robustness of absolute loss to heavy-tailed
outliers (Koenker & Bassett, 1978, quantile regression) and XGBoost's official
`reg:absoluteerror` objective documentation.  Earlier project development
folds also showed a direction improvement for this objective, so this was a
replication on the reserved tail rather than a new parameter sweep.

On the existing two-pair reserved tail (4,456 rows):

| model | direction accuracy |
|---|---:|
| current squared-error/L1 blend | 49.9776% |
| absolute-error main/L1 blend | 50.9650% |

The candidate gains `+0.9874pp` over the current model and is above the same
tail's majority-direction reference (`50.3815%`).  Per-pair accuracy is BTC
`50.7630%` and ETH `51.1670%`.  However, the paired two-day block bootstrap
(3,000 draws, seed 42) gives `[-2.021pp, +4.150pp]`, crossing zero.  This is a
promising point estimate but does not meet the project's stable-promotion
gate; no production configuration is changed.

Reproduction config: `configs/experiments/xgboost_l1_main_final.yaml`.
Run artifact: `artifacts/experiments/l1-main-final-holdout-v1`.
