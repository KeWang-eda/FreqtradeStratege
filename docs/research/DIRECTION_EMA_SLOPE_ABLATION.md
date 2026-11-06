# Fast/slow EMA distance interaction

The candidate was fixed as
`EMA_distance(6) - EMA_distance(24)`, a causal trend-slope interaction.  The
mechanism is motivated by Moskowitz, Ooi & Pedersen (2012), *Time Series
Momentum*, Journal of Financial Economics 104(2), 228–250.  That reference
supports testing trend persistence, not the claim that this feature works for
the present horizon.

The experiment added exactly one column to the existing native training and
prediction inputs.  Labels, weights, XGBoost parameters, early stopping, seed
and six-week × three-pair development windows were fixed.  It produced
`379/756 = 50.1323%`, versus the recorded current-feature baseline
`397/756 = 52.5132%`, a decline of `2.381pp`.

The candidate is rejected; no production feature or configuration changes.
Reproduction: `tools/run_ema_slope_ablation.py --output
artifacts/direction-threshold-study/ema-slope-ablation-v1`.
