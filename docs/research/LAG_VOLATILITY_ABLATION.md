# Lag-return baseline: volatility feature ablation

## Hypothesis

The six and twenty-four candle rolling volatility inputs may add regime noise to
the direction boundary after causal lag returns are present. The candidate
removes only `%-volatility-6` and `%-volatility-24`.

This is a research ablation, not a production feature-contract change. The
feature calculation remains causal (`close.pct_change().rolling(std)`).

## Evidence

The experiment used the same native training and validation rows, labels,
sample weights, XGBoost parameters, seed, early stopping, lag-return features,
and UTC prediction dates. The candidate refit its preprocessing pipeline after
removing the two columns. All 756 paired predictions were ready.

| arm | correct / n | direction accuracy |
| --- | ---: | ---: |
| lag-return baseline | 406 / 756 | 53.704% |
| lag-return + volatility ablation | 418 / 756 | **55.291%** |

The first pilot produced 418/756 correct candidate predictions, but its output
did not include a paired baseline prediction and its runner changed the
feature set by adding lag returns while removing volatility. Therefore the
418/756 figure is **not a valid ablation delta** and must not be interpreted as
a measured uplift. A corrected paired run is required before any production
decision. The six-week window is already exposed development data in any case.

Reference for the design: XGBoost parameter documentation (feature inputs and
validation lifecycle), and Gama et al. (2014), *A Survey on Concept Drift
Adaptation*, ACM Computing Surveys 46(4), for testing whether regime-related
inputs improve temporal generalization rather than assuming they do.

Reproduce with:

```bash
conda run --no-capture-output -n quant \
  python tools/run_lag_volatility_ablation.py
```

