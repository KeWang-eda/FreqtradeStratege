# Layer audit and logging evidence

## Root cause of the random-like backtest

The current Freqtrade entry point is a pair-local control, not the model-driven layered pipeline.

Evidence:

- `LayeredVtechStrategy.MODEL_IDENTIFIER` is `not-used-control-feature-only`.
- `populate_indicators()` calls `build_vtech_model_features()` and computes `net_long_edge` and `net_short_edge` from pair-local momentum and ATR risk proxy.
- The entry point does not import or call `XGBoostRiskModel`.
- The entry point does not call `rank_cross_sectional_candidates()`.
- The entry point does not read `dp.current_whitelist()` or compare other pairs.
- Freqtrade therefore receives independent signals per pair and fills available slots according to its normal backtesting order. There is no Top-K cross-sectional decision in this path.

The strategy log proved this directly. The 3-pair logging smoke emitted one `strategy_indicators_ready` event per pair with hundreds of pair-local long and short signals, but no selection event and `model_identifier=not-used-control-feature-only`.

This is not a small parameter problem. It is a pipeline identity problem: the backtest called a control rule while the research goal described a model-ranked strategy.

## Layer contract findings

| Severity | Layer | Finding | Evidence | Decision |
|---|---|---|---|---|
| P0 | Strategy/model | Model is not connected to the entry point. | No XGBoost import/call; model identifier explicitly says not used. | Keep entry as control; do not call it model backtest. |
| P0 | Strategy/selection | Cross-sectional ranking is not connected. | No whitelist-wide data or selection-layer call in strategy entry. | Do not interpret pair-local fills as Top-K selection. |
| P0 | Pipeline | `LayeredStrategyPipeline.run()` is fail-closed `NotImplementedError`. | Direct source inspection. | Keep disabled until adapters and OOS evidence exist. |
| P1 | Configuration | The research config sets `max_open_trades=5`, while the strategy class says 3. | Freqtrade resolver log overrides class value from config. | Every acceptance run must pass `--max-open-trades 3` or use a corrected research config. |
| P1 | Portfolio | `max_side_exposure` is validated but not enforced. | `build_position_targets()` sorts and truncates only by net edge. | Fix before production composition. |
| P1 | Execution | `ExecutionConfiguration.funding_rate` is not consumed by `OrderPlan`. | `create_order_plan()` records fee/slippage only. | Fix before claiming execution parity. |
| P1 | Risk | `liquidation_buffer` is carried and validated but no exchange-specific liquidation distance is calculated. | `apply_position_risk_limits()` has no liquidation-price input or calculation. | Keep as declared boundary, not a completed liquidation check. |
| P1 | Contracts | The pipeline's result object exists, but no implementation produces it. | `strategy_layer_pipeline.py`. | Do not close the pipeline task as complete. |

## Required repair order

1. Keep the current pair-local entry explicitly named and measured as a control.
2. Build a causal panel adapter that produces same-timestamp model predictions for all pairs.
3. Connect model predictions to selection as the actual `expected_edge`; do not use momentum as a hidden substitute.
4. Enforce side exposure, exchange precision, funding, and liquidation inputs in the composition path.
5. Re-run the two-year OOS and DSR/PBO gates.
6. Only after those gates pass, create a separate strategy entry for staging and dry-run.

## Logging contract

The logging batch uses Python standard logging so Freqtrade's native handlers and `--logfile` remain authoritative. Every public layer boundary has failure capture that records the function, exception type, error code, message, and traceback before re-raising. INFO/DEBUG events measure layer input/output counts; WARNING events record fail-closed rejection; ERROR records unexpected exceptions.
