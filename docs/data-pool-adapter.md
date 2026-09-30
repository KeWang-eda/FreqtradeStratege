# PIT data pool

The data-pool layer reads local Freqtrade feather files at one closed-candle decision timestamp.

## Inputs

- `*-1h-futures.feather` OHLCV files.
- Matching `*-1h-funding_rate.feather` files.
- Optional exchange market metadata for minimum stake.

## Rules

- Rows after `decision_timestamp` are excluded.
- Duplicate timestamps keep the latest row.
- Average quote volume uses `close × volume` over the configured trailing bar window.
- Funding uses the latest known funding candle `open` value.
- Minimum stake remains optional because it comes from exchange metadata, not OHLCV.
- The output is a sorted `DataPoolSnapshot` with explicit timestamp identity.

## Verified local input

The current local data directory contains 54 1h futures files and 54 matching funding files. A real validation run built 54 assets at the latest available BTC timestamp and at an earlier historical timestamp.

The loader is an input boundary only. It does not choose a signal, calculate a model feature, place an order, or claim that the pool is economically optimal.
