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

The paired development result is **+12 correct predictions (+1.587 pp)**.
The six-week window is already exposed development data, so this result is not
an independent confirmation and does not change production configuration.

Reference for the design: XGBoost parameter documentation (feature inputs and
validation lifecycle), and Gama et al. (2014), *A Survey on Concept Drift
Adaptation*, ACM Computing Surveys 46(4), for testing whether regime-related
inputs improve temporal generalization rather than assuming they do.

Reproduce with:

```bash
conda run --no-capture-output -n quant \
  python tools/run_lag_volatility_ablation.py
```

