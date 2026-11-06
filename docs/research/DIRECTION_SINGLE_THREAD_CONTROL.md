# XGBoost single-thread reproducibility control

Prior project audits found small differences between repeated multi-threaded
XGBoost fits.  This control tested `n_jobs=1` against the current absolute-error
main model, based on XGBoost's deterministic single-thread execution behavior.
No feature, label, objective, weight, split or tree parameter changed.

On the complete three-pair reserved tail (6,684 rows), both configurations
produced exactly `50.5386%` direction accuracy.  The control therefore has no
measured direction improvement, although it remains useful for reproducible
future experiments.  Production configuration is unchanged because this was a
reproducibility control, not an accuracy gain.

Configuration: `configs/experiments/l1main-single-thread.yaml`.
