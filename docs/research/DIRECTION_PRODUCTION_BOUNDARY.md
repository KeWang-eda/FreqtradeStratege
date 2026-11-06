# Direction research and production boundary

The current production FreqAI entry remains `XGBoostRegressorES` with the
volatility-normalized return target and RMSE early stopping.  The native
`NativeDirectionLearner` experiments are separate research heads; their
historical direction scores cannot be called a production improvement until a
registered production adapter and an unexposed time-forward confirmation exist.

As of the current data snapshot, BTC/ETH/BNB 4h candles end on 2026-10-15 and
the available direction windows have already been inspected.  The formal
holdout policy also denies numeric access before preregistration and admission.
Consequently no new independent window is available for the next H8
logloss-early-stopping confirmation.  Reusing prior windows would create a
selection loop, so no production switch is made.  The next authorized model
iteration is frozen: compare direction-head own logloss early stopping with a
fixed-tree binary control on a future registered window, requiring paired
direction-accuracy block-bootstrap lower bounds above zero in two independent
windows.
