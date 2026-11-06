# All-feature importance inventory

FreqAI's `plot_feature_importances` setting is enabled, but plots are not a
versioned or auditable source. This research exporter reads every saved
XGBoost booster in the rolling development models and writes gain, split
weight, and cover for every schema feature, together with model and schema
SHA256 values.

Run:

```bash
conda run --no-capture-output -n quant \
  python tools/export_xgb_feature_importance.py
```

The current inventory contains 18 model snapshots and 1,920 feature/model
rows. The highest mean gain entries are ATR-ratio period features, followed by
volatility, RSI and SMA features. Gain is descriptive only: correlated columns
split importance, and a high gain does not establish direction accuracy. The
inventory therefore generates feature-family hypotheses; it never selects or
deletes a feature. Any candidate must pass paired temporal evaluation with the
direction-accuracy and block-bootstrap gates.

