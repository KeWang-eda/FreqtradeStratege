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

The pipeline remains research-only. The Freqtrade entry point is still the pair-local control because the model OOS and DSR/PBO gates have not passed.
