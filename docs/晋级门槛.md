# Promotion gates

The new framework is not eligible for promotion until every gate passes.

## Contract gates

- Every layer has a typed input and output contract.
- Timestamps are timezone-aware and aligned.
- Version identity is recorded for data, features, labels, and models.
- Invalid inputs fail closed.

## Data and model gates

- No lookahead or label leakage.
- Point-in-time universe construction.
- Feature coverage and feature count are stable.
- OOS model metrics are reported by time window, direction, and pair.
- Probability outputs are calibrated on earlier data only.

## Portfolio and execution gates

- Leverage is bounded by the exchange limit and the framework limit.
- Stake is sized from account risk, leverage, and stop distance.
- Minimum stake and precision are prechecked.
- Liquidation buffer is explicit.
- Fees, funding, spread, and slippage are included.
- Backtest and dry-run use the same signal timing assumptions.

## Promotion gates

The candidate must satisfy all conditions:

```text
candidate wallet Sharpe × wallet Calmar
    > parent wallet Sharpe × parent wallet Calmar

candidate max_relative_drawdown < 30%
```

The independent window must reproduce the direction of the result. A candidate with missing, non-finite, or non-reproducible metrics is blocked.

Statistical validation must be added before production promotion:

- Purged validation with an embargo at least as large as the maximum feature lookback.
- Deflated Sharpe Ratio or an equivalent multiple-testing correction.
- Probability of Backtest Overfitting or an equivalent selection-bias diagnostic.

A layer can pass its independent gate and still fail the combined gate. The combined gate is authoritative.
