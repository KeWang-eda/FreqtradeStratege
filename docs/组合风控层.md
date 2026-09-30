# Portfolio and risk layer

The first control group is deliberately fixed at 2x leverage and a 2% account-risk budget. Dynamic leverage is not enabled.

## Sizing

```text
per_position_risk = total_risk_budget / selected_slots
stake = equity × per_position_risk / (leverage × stop_distance)
```

The portfolio layer creates targets. The risk layer then applies exchange maximum leverage, minimum stake, maximum stake, and liquidation-buffer checks. Side exposure is now enforced during candidate selection; a candidate is rejected when adding its leveraged gross weight would exceed `max_side_exposure`.

When the composition pipeline receives the exchange-calculated liquidation price and current price, the risk layer rejects a stop price on the liquidation side. If liquidation data is absent, the pipeline continues only as a research composition and emits `liquidation_distance_unverified`; it does not claim live liquidation safety.

## Real-data smoke

Using the 54-asset local 1h selection chain:

- Selected candidates at the latest timestamp: 6.
- Approved portfolio slots: 3.
- Leverage: 2x.
- Equity: 100 USDT.
- Risk budget: 2%.
- Total approved stake: 6.6667 USDT.
- Minimum stake and exchange leverage checks: passed.

This is a sizing-control smoke, not a strategy PnL result. Execution costs, order precision, funding, and full wallet backtesting remain later gates.
