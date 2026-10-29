# Prediction Model Optimization, 2026-10-29

## Scope

This work adds standalone candidates and promotes the shallow XGBoost
configuration to the FreqAI production model. It does not change the strategy
signals, label, data split, or trading rules. The production cache identifier
was changed and a new v4 controlled contract was frozen; the formal research
gate remains closed.

The experiments used BTC/USDT:USDT and ETH/USDT:USDT local 4h data, the
`volnorm` label with a 3-candle horizon, the same baseline features, and three
purged chronological development folds. There were 18,934 outer-fold
predictions. Dataset SHA-256 was
`8e42c16dbc11e070505bafaf40b62381f9e0ad0ca63243f6582d8a22bea7ec67` and fold
plan SHA-256 was
`f1a350325a63fccd6f8e49897ae7be55c6eca09cd9020e5fadc8770b3d7e5c4d`.
The environment was Freqtrade 2026.7, XGBoost 3.4.1, Python 3.13.13.

## Findings

The existing early-stopping path was checked against XGBoost 3.4.1. The
standalone wrapper already passed the inner validation data through `eval_set`,
and `early_stopping_rounds` on the estimator constructor stopped a direct test
fit after 31 rounds. The earlier claim that early stopping was broken was
incorrect; no change was made to that path.

The promoted configuration `max_depth=2`, `n_estimators=300`,
`learning_rate=0.03` improved average fold RMSE from 1.2450 to 1.2385 and MAE
from 0.8565 to 0.8515 versus the existing XGBoost configuration. Its per-fold
Spearman IC remained negative, and pooled RMSE/MAE (1.2388/0.8515) remained
worse than the zero-prediction baseline (1.2366/0.8445), so the promotion is
an engineering model-selection decision based on directional utility and IC,
not a claim that every error metric improved.

Because the volnorm target is heavy-tailed (outer-fold excess kurtosis about
6.58), Pseudo-Huber and absolute-error objectives were tested using the same
folds. Pseudo-Huber improved MAE to 0.8501 but worsened RMSE to 1.2401 and
reduced Pearson IC to 0.0076. Absolute-error produced RMSE 1.2385 and MAE
0.8498, but its IC was below the promoted shallow RMSE objective. Neither was
promoted. The rationale follows XGBoost's documentation for
`reg:pseudohubererror` and `reg:absoluteerror` as robust alternatives for
outlier-sensitive regression.

The strategy ultimately consumes prediction sign for direction, while the
existing regressor minimizes squared continuous-return error. A new optional
`xgboost_direction` estimator predicts `P(return > 0)` and converts that
probability to an expected return using positive and negative conditional mean
returns fitted from the training partition only. On the same folds, its pooled
direction accuracy was 0.5109 versus 0.5073 for current XGBoost; its per-fold
Spearman ICs were 0.0345, 0.0673, and 0.0332. Pooled Spearman IC was 0.0185,
and pooled RMSE/MAE (1.2412/0.8486) still trailed the zero baseline. This is a
small development signal that merits broader validation, not evidence of
profitable or production-ready predictions.

An inner-validation scalar shrinkage experiment was also tested and rejected:
it did not consistently beat zero on both pairs and could erase the usable
direction signal. No calibration change remains in the implementation.

## Iteration 2: recent-sample weighting

FreqAI's `FreqaiDataKitchen.set_weights_higher_recent` uses exponential weights
that increase toward the newest training samples. This is a documented way to
adapt to regime drift without reading future labels. I reproduced that formula
in the standalone fold backend and tested factors 0.9 and 0.5. Factor 0.9 was
selected: mean Pearson IC improved from 0.0396 to 0.0439, MAE improved from
0.85148 to 0.85129, and RMSE stayed effectively unchanged (1.23851 to
1.23852); all three fold Pearson IC values were positive. Factor 0.5 was less
stable. The production configuration now enables `weight_factor: 0.9`, and its
cache identifier and controlled contract were advanced to the recent-weighted
namespace.

## Iteration 3: L2 regularization

XGBoost documents `reg_lambda` as L2 regularization on leaf weights; increasing
it makes the model more conservative. With the promoted shallow model and
`weight_factor=0.9` fixed, values 2, 5, and 10 were evaluated on the same three
purged folds. `reg_lambda=5` was selected: RMSE improved from 1.23852 to
1.23805, MAE from 0.85129 to 0.85044, direction accuracy from 50.6868% to
50.7396%, and mean Spearman IC from -0.00294 to 0.00306. Lambda 2 had slightly
higher Pearson IC but worse aggregate error and rank IC; lambda 10 showed
over-regularization. Production now uses `reg_lambda: 5.0` with a new cache
identifier and controlled contract.

## Reproduction

The original regression run was:

```bash
PYTHONPATH=. /path/to/freqtrade/.venv/bin/python -m quant.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  -c configs/experiments/baseline_volnorm.yaml \
  -c configs/estimators/xgboost_direction.yaml \
  --output /tmp/freqtrade-strategy-model-opt \
  --experiment-id xgb-direction-20261029
```

The regression candidate uses `configs/estimators/xgboost_shallow.yaml` in
place of `xgboost_direction.yaml`. Experiment artifacts were written under
`/tmp/freqtrade-strategy-model-opt/`; each run includes its resolved config,
source snapshot, fold predictions, metrics, leakage report, and checksums.

## Evidence and Design Basis

- XGBoost's [scikit-learn estimator guide](https://xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html)
  documents `XGBClassifier`, probability prediction, validation `eval_set`,
  and early stopping. It also cautions that early stopping inside
  cross-validation needs care, so the project keeps the final holdout reserved.
- Scikit-learn's [TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
  explains why time-ordered data must train on earlier observations and test on
  later ones. The project additionally purges overlapping label intervals.
- Freqtrade's [FreqAI feature-engineering documentation](https://www.freqtrade.io/en/stable/freqai-feature-engineering/)
  describes the production feature expansion lifecycle. These standalone
  candidates do not alter that schema or production lifecycle.
- FreqAI's installed `FreqaiDataKitchen.set_weights_higher_recent` source
  defines the exponential recent-sample weighting reproduced by the research
  backend.

## Verification

The focused model, persistence, config, and leakage tests passed: 25 tests.
The final full suite passed **827 tests**. The offline legacy reference and
frozen-baseline tests were updated to distinguish historical model artifacts
from the promoted production configuration; predictions, trades, and metrics
remain strictly compared.
