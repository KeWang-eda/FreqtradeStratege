# Composition pipeline

`strategies/strategy_layer_pipeline.py` now provides a research-only composition boundary for one decision timestamp:

```text
candidate_frame
  -> selection_layer
  -> portfolio_layer
  -> risk_layer
  -> execution_layer
  -> StrategyRunResult
```

The pipeline requires model predictions to already exist in `candidate_frame`. It does not train a model, fetch future data, or submit orders.

## Required inputs

- `candidate_frame`: same-timestamp rows with pair, side, expected edge, predicted adverse risk, and execution cost.
- `account_equity`.
- `current_prices`.
- Optional portfolio and execution configurations.

## Evidence

The synthetic composition smoke passed with:

- Four candidates.
- Top-K selection.
- Side-exposure rejection.
- Two approved risk decisions.
- Two precision-aware order plans.
- Signed funding cost present in each order plan.

## Real-data run (EXP-259)

`scripts/run_composition_backtest.py` chains these modules on the real EXP-252 OOS predictions (2,309 decisions, 2024-08-17 → 2026-09-27, 15 pairs) and applies the same 8-hour wallet accounting as the EXP-254 research script.

| Metric | EXP-259 official path | EXP-254 research script (risk_penalty=0.5) |
|---|---:|---:|
| Wallet return | −27.49% | −29.35% |
| Wallet Sharpe | −1.487 | −1.566 |
| Wallet Calmar | −0.372 | −0.386 |
| Max relative drawdown | 38.00% | 39.32% |
| Decision periods | 2,309 | 2,309 |

Both paths reject the candidate with the same magnitude, so the module chain and the research script agree. Remaining gaps are explained by documented boundaries: per-side Top-3 selection versus a global Top-3 sort, the `minimum_net_edge = 0` gate, dropped NaN feature rows, and execution-precision rejections.

Findings from the run:

- Risk layer rejected 0 orders: no exchange liquidation prices exist locally, so liquidation distance is logged as unverified instead of silently assumed.
- Execution layer rejected 322 otherwise-approved orders on precision grounds (`quantity_step = 0.001`); BTC is unplaceable entirely at 100 USDT equity with 2x sizing, so it never appears in the order list.
- The rejected candidate stays rejected: no promotion and no entry connection.
- The runner reproduces identical metrics on re-run.

Evidence artifacts: `/tmp/exp259-composition/{metrics.json,wallet.csv,orders.csv}`.

The pipeline remains research-only. The Freqtrade entry point is still the pair-local control because the model OOS and DSR/PBO gates have not passed.
