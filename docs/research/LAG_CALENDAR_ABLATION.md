# Lag-return baseline: calendar feature ablation

## Hypothesis

Hour-of-day and day-of-week inputs can encode calendar effects that are stable
in sample but unstable across crypto market regimes. This follows the temporal
generalization concern in Gama et al. (2014), *A Survey on Concept Drift
Adaptation*, ACM Computing Surveys 46(4). The candidate removes only
`%-hour` and `%-day-of-week` from the current lag-return baseline.

## Paired result

Both arms use the same rows, labels, weights, lag-return features, preprocessing
lifecycle, XGBoost parameters, seed and early stopping. All 756 paired rows are
ready.

| arm | correct / n | direction accuracy |
| --- | ---: | ---: |
| lag-return baseline | 406 / 756 | 53.704% |
| calendar ablation | 414 / 756 | **54.762%** |

The point change is **+8 correct predictions (+1.058 pp)**. A 12-candle circular
block bootstrap (seed 42, 5,000 resamples) gives `[-1.720 pp, +3.968 pp]`, so
the interval crosses zero. This is an exposed development window and is not a
production promotion decision.

Reproduce with:

```bash
conda run --no-capture-output -n quant \
  python tools/run_lag_volatility_ablation.py \
  --remove '%-hour,%-day-of-week' \
  --output artifacts/direction-threshold-study/lag-calendar-ablation-v1
```

