# ATR-normalized historical momentum interaction

The candidate was motivated by Moreira & Muir (2017), *Volatility-Managed
Portfolios*, which motivates scaling signals by observable volatility.  The
paper does not establish that this interaction improves this model.  The
candidate was fixed as the causal interaction
`momentum_p / atr_ratio_p` for `p in {6,14,24}`.  Both components already
exist, so this tests one explicit interaction rather than claiming three new
independent indicators.

The rolling experiment kept the existing training rows, labels, feature
pipeline inputs, XGBoost parameters, recency weights and 42-candle prediction
windows fixed.  The interaction was computed from same-candle native columns;
no future rows were used.  It covered the six previously frozen weeks and three
pairs (756 common prediction points).  The baseline was the already recorded
`52.51%` direction accuracy on those points.

The candidate scored `385/756 = 50.93%`, a decline of `1.59pp`.  Pair and week
results were mixed, with a pronounced ETH decline in week 5; there is no basis
for production promotion.  The feature is rejected and no configuration was
changed.

Reproduction uses `tools/run_volnorm_feature_ablation.py` with project-relative
defaults and output under `artifacts/direction-threshold-study/volnorm-momentum-ablation-v3`.
