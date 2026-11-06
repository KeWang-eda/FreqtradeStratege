# Hinge objective replication on the 2023 historical window

The 2024 H10 inner-fold hinge result was positive in point value but its block
interval crossed zero.  We therefore repeated the exact objective-only test on
the separate `base-20230701-direction-confirm1` source window, before making
any production decision.  The rationale is the same: XGBoost's documented
`binary:hinge` hard-classification objective and the surrogate-loss analysis of
Bartlett, Jordan & McAuliffe (2006).  This replication does not use the earlier
bagging rationale; only the objective changes.

All three pairs used the same native feature pipeline, labels, maturity purge,
recency weights, seed, inner chronological split, tree cap and threshold as
the logistic control.  There were 3,908 common ready predictions.

| fold | logistic accuracy | hinge accuracy | hinge minus logistic |
|---:|---:|---:|---:|
| 0 | 51.106% | 49.809% | -0.130pp |
| 1 | 47.477% | 48.700% | +0.123pp |
| 2 | 54.128% | 50.917% | -0.321pp |

Pooled logistic accuracy was `1,989/3,908 = 50.896%`; hinge was
`1,946/3,908 = 49.795%`, a decline of `1.101pp`.  The paired two-day block
bootstrap (2,000 draws, seed 42) was `[-3.288pp, +1.221pp]`.  The candidate
fails the predeclared gate: it is below baseline, only one of three folds
improves, and the interval crosses zero.

The 2024 point gain therefore does not replicate in 2023.  Hinge is rejected;
the production objective remains logistic/regression as configured.  Outputs
are under `artifacts/native-direction-audit/{logistic23-v1,hinge23-v1}`.
