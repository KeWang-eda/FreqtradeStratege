# Lag-return baseline: candle-body feature ablation

The body and close-return inputs are structurally related, so the candidate
tests whether removing body-family inputs reduces redundant splits. This is a
single-factor paired ablation; lag returns, labels, weights, preprocessing,
XGBoost parameters and early stopping remain fixed.

On 756 common ready predictions:

| arm | correct / n | direction accuracy |
| --- | ---: | ---: |
| lag baseline | 406 / 756 | 53.704% |
| body ablation | 411 / 756 | **54.365%** |

The point change is **+0.661pp**. A 12-candle circular block bootstrap (5,000
resamples, seed 42) gives `[-1.852pp, +3.042pp]`; the interval crosses zero.
The result is exploratory and does not change production.

The identical direction count to the range ablation is not an artifact reuse:
the candidate prediction values differ (maximum absolute difference `0.898`),
but all 756 prediction signs happen to agree.

