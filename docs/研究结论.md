# Layered framework research conclusion

## Status

The clean-room layered framework is implemented and locally exercised. It is not a promoted trading strategy. The entry point remains a causal-feature control; the model-driven selection pipeline is disabled.

## Implemented and verified

- Point-in-time local data pool.
- Causal 89-feature layer with technical allowlist.
- Future adverse-risk and signed utility labels.
- Chronological XGBoost training with validation-only early stopping.
- Same-timestamp candidate ranking.
- Fixed 2x portfolio risk budget.
- Stake, leverage, precision, fee, slippage, funding, and order-plan checks.
- Wallet metrics, DSR, CSCV PBO, lookahead analysis, and recursive analysis.
- Causal 4h/12h and mark-basis adapters remain research-only and are not in the entry point.

## Rejected evidence

All results below use local data, non-overlapping 8-hour decisions where applicable, fixed costs, funding, and a 15-pair universe unless noted otherwise.

| Experiment | Result | Decision |
|---|---:|---|
| Causal-feature control, one-year Freqtrade backtest | +5.52%, maximum drawdown 34.07% | Rejected |
| Model risk selection OOS wallet | -5.88%, DSR 0.4958, PBO 0.6286 | Rejected |
| Signed utility, forced Top-3 | -7.77%, Sharpe -3.087 | Rejected |
| Directional-return regression | -10.11% | Rejected |
| Positive-return classifier | -7.65% | Rejected |
| 4h/12h context extension | -10.49% | Rejected |
| Mark/futures basis extension | -10.25% | Rejected |
| Funding carry | -10.76%, Sharpe -3.12 | Rejected |
| Correct futures/spot basis | -15.54%, Sharpe -6.13 | Rejected |
| Cross-sectional 4h/12h/24h return ranking | All net means negative | Rejected |
| MA20 direction filter | -17.23% wallet metric result | Rejected |
| Short-only direction control | -2.18%, product below baseline | Rejected |
| Fixed 48-hour holding control | +1.73%, product below baseline | Rejected |

## Safety evidence

- Freqtrade lookahead analysis: no bias detected for the current control.
- Recursive analysis: startup 200 showed warmup drift; startup 999 was selected and short-window regression passed.
- The official parent EXP-184 is not equivalent to this clean-room branch. Its stored historical ZIP remains the parent evidence; a fresh one-year comparison was blocked by Binance HTTP 418 market initialization.

## Explicit exclusions

Open interest, liquidation history, long/short ratios, and order-flow data are excluded because no complete point-in-time history exists locally. Current API values must not be inserted into historical tests.

## Stop rule

Do not run another parameter, threshold, target-family, or lookback sweep on the current 89-feature price/funding family. The next experiment requires either:

1. A new historical information source with a causal timestamp contract.
2. A materially different market mechanism with a written hypothesis and independent OOS protocol.
3. A same-data parent comparison after the Binance rate-limit blocker is gone.

Until one of these conditions exists, do not connect the model pipeline to the entry point and do not start dry-run trading.
