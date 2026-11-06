# Feature-family importance stability

The versioned XGBoost inventory was aggregated by semantic family across 18
saved models. This is a screening report, not a feature-selection result.

| family | mean gain fraction | nonzero usage |
| --- | ---: | ---: |
| volatility | 0.0344 | 77.8% |
| ATR ratio | 0.0295 | 59.5% |
| RSI | 0.0113 | 39.3% |
| momentum | 0.0075 | 32.5% |
| calendar | 0.0069 | 25.0% |

The remaining families had lower average gain and/or sparse usage. High gain
does not prove temporal direction utility, especially for correlated inputs;
the existing paired ablations remain the promotion evidence. The report is used
to select one pre-registered family hypothesis at a time, followed by paired
forward direction scoring and block bootstrap.

Reproduce with:

```bash
conda run --no-capture-output -n quant python tools/summarize_feature_families.py
```

