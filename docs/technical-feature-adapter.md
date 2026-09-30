# Technical feature adapter

The repository `freqtrade/technical` is integrated as an optional feature source, not as a blind feature dump.

## Upstream audit

The reviewed upstream revision is `e3d0a05`. It provides:

- Trend and overlap indicators such as Supertrend, Ichimoku, HMA, VWMA, and Bollinger Bands.
- Momentum indicators such as RMI and Williams percent.
- Volatility indicators such as normalized ATR and Choppiness Index.
- Volume indicators such as VFI, VPCI, VWMA, and volume-weighted MACD.
- Resampling and merge utilities.
- A generic test suite covering output shapes, column names, and snapshots.

The package currently depends on pandas and TA-Lib and is licensed under GPLv3. Do not copy upstream source files into this repository without a license review. The first integration uses the installed package through an explicit adapter.

## Adapter

`strategies/technical_feature_adapter.py` defines:

- `TechnicalFeatureSpec`: the allowlisted feature metadata.
- `compute_technical_features()`: computes only the selected features on a copied DataFrame.
- `validate_technical_features()`: rejects empty or all-missing outputs.
- `TECHNICAL_FEATURE_VERSION`: feature identity for model and experiment records.

The initial candidate pack is deliberately small:

| Category | Candidates |
|---|---|
| Volatility | normalized ATR, Bollinger width, Bollinger percent B |
| Regime | Choppiness Index |
| Momentum | RMI, Williams percent |
| Trend | Supertrend distance and direction |
| Volume | VFI, VFI histogram, VWMA distance |

## Deliberate exclusions

- Ichimoku `chikou_span` is excluded because the upstream implementation uses a negative shift and explicitly warns not to use it for backtesting.
- `zema` is excluded because upstream marks it deprecated in favor of `dema`.
- `resampled_merge()` is not used by the first adapter. Multi-timeframe features require a separate causal alignment audit.
- Consensus indicators are not included in the first pack because they combine many lower-level indicators and make attribution harder.
- The whole upstream catalogue is not passed to XGBoost. Redundant features must pass cluster-level correlation, time-split IC, feature stability, and OOS tests first.

## Promotion path

1. Install a pinned `technical` version in the research environment.
2. Run adapter shape, NaN, warmup, and mutation tests.
3. Run causal/lookahead checks on every feature.
4. Calculate time-split IC and Rank IC by pair, direction, and regime.
5. Add one feature group at a time to the model identifier.
6. Compare the parent and candidate on identical windows and costs.
7. Keep the feature only if independent OOS evidence passes the repository promotion gates.

A technical indicator is a candidate input, not a trading rule and not evidence of alpha.
