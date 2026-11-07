# VFI histogram ablation

## Question

Does adding one causal Volume Flow Indicator histogram feature improve the sole promotion metric, direction accuracy, over the production lag-return baseline?

## Basis and protocol

The candidate is `%-vfi-hist`, produced by the repository's `technical` 1.7.0 implementation (LazyBear/Chris Moody VFI formula). The implementation uses current and historical OHLCV only and therefore does not look ahead. The feature was added as one factor to the existing lag-return feature contract. Baseline and candidate were fit independently for every rolling week/pair with the same preprocessing, XGBoost parameters, labels, weights, and 756 common prediction rows. No trading backtest was used.

## Result

| arm | correct | accuracy |
|---|---:|---:|
| production lag-return baseline | 406/756 | 53.704% |
| + VFI histogram | 391/756 | 51.720% |

Paired block bootstrap (12 candles, seed 42) gives a candidate-minus-baseline change of **-1.984 percentage points**, 95% interval **[-4.365, +0.397]**.

## Decision

VFI histogram is rejected for production promotion. The feature is removed from the candidate contract; the production configuration remains unchanged. This closes the VFI leaf of the feature-family branch and redirects the anomaly tree to condition-drift diagnostics before another feature experiment.

## Reproduction

```bash
conda run -n quant python tools/run_lag_volatility_ablation.py \
  --add-vfi --remove '' \
  --output artifacts/direction-threshold-study/vfi-hist-ablation-v1
```
