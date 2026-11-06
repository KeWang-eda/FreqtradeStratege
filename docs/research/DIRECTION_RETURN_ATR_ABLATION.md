# ATR-scaled one-bar return feature

The candidate was `return_1 / ATR_ratio_14`, computed only from the current
and completed historical candle.  The motivation was the project's
ATR-normalized future label and the volatility-management mechanism described
by Moreira & Muir (2017), *Volatility-Managed Portfolios*.  This is a separate
candidate from the previously rejected `momentum/ATR` interaction.

The feature was added as one column to each training, validation and prediction
frame.  All labels, weights, XGBoost settings, early stopping and six-week
three-pair development windows were fixed.  It scored `379/756 = 50.1323%`,
versus the current-feature baseline `397/756 = 52.5132%`, a decline of
`2.381pp`.

The candidate is rejected and no production configuration changes.  Reproduce
with `tools/run_return_atr_ablation.py --output
artifacts/direction-threshold-study/return-atr-ablation-v1`.
