# Lag-return baseline: range feature ablation

The feature stability diagnostic identified `range` as a candidate whose
direction relationship changes across time. Following Gama et al. (2014) on
concept drift, this paired experiment removes the complete native range family
(`%-range` and generated shifted variants) while retaining lag-return features.

Using identical training/validation rows, weights, pipelines, XGBoost
parameters, early stopping, UTC dates and common ready mask:

| arm | correct / n | direction accuracy |
| --- | ---: | ---: |
| lag baseline | 406 / 756 | 53.704% |
| range ablation | 411 / 756 | **54.365%** |

The point change is **+0.661pp**. A synchronized 12-candle circular block
bootstrap (5,000 resamples, seed 42) gives `[-1.852pp, +3.042pp]`; the interval
crosses zero. This remains an exposed development result and is not a
production promotion.

