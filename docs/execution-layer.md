# Execution layer

The execution layer converts approved risk decisions into explicit order plans.

## Checks

- Order type is `market` or `limit`.
- Quantity is floored to the exchange quantity step.
- Orders that floor to zero are rejected.
- Minimum stake is checked after precision rounding.
- Fee and slippage are recorded explicitly.
- Expected funding cost is recorded with long/short sign.
- Funding rate input is validated as finite before an order plan is created.
- Long and short side identity is preserved.
- Every plan receives a timestamped client order tag.

## Smoke evidence

- `20 USDT × 2x / BTC 50000 / quantity step 0.001` floors to zero and is correctly rejected.
- The same order with quantity step `0.0001` produces a 20 USDT effective stake.
- Fee and slippage are both recorded.
- Long and short order plans preserve their side.

This layer does not submit orders. It creates the same explicit order intent that a future backtest, dry-run, or live adapter must consume.

## Holding-period audit

The current control's opposite-signal exit was compared with a fixed 48-hour maximum holding period on the same 15-pair, 1h, one-year backtest. The 48-hour control produced `+1.73%` wallet return and `25.65%` maximum relative drawdown, below the 30% drawdown ceiling. Its wallet Sharpe × Calmar was `0.00253`, below the baseline control's `0.01121`, so the holding-period variant was rejected. It is evidence that early exits contribute to losses, not a promotion candidate.

A short-only control was also tested by disabling long entries only. It produced `-2.18%` wallet return, `17.46%` maximum relative drawdown, and product `0.00114`, below the two-sided baseline. Direction-side removal is therefore rejected.
