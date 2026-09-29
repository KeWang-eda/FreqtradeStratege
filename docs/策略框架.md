# Strategy framework

This branch defines the new architecture only. It intentionally does not preserve the historical strategy implementation.

## Runtime flow

```text
data_pool_layer
    -> feature_layer
    -> label_layer / model_layer
    -> selection_layer
    -> portfolio_layer
    -> risk_layer
    -> execution_layer
    -> validation_layer
```

## Contracts

Every layer has a typed value object and a protocol boundary. Values carry a timestamp and version identity where the layer needs them. Invalid values raise immediately; the combined pipeline fails closed until adapters exist.

## Layer ownership

- Data pool owns point-in-time tradability.
- Feature layer owns causal feature construction.
- Label layer owns future training targets only.
- Model layer owns predictions and model identity.
- Selection layer owns same-timestamp ranking.
- Portfolio layer owns target weights, leverage, and risk-budget stake.
- Risk layer owns approval, resizing, and rejection.
- Execution layer owns precision and explicit costs.
- Validation layer owns evidence and promotion decisions.

## Independent work

Workers can develop one module independently. A worker must not edit the production entry point, another layer, or shared experiment configuration without an integration task. Independent layer metrics are necessary but insufficient; the combined pipeline must reproduce the parent-versus-candidate result before promotion.
