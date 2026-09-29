# Strategies directory

This directory is a clean-room strategy framework. Previous strategy entry points were removed from this refactor branch; they remain available in Git history and on the historical `main` branch.

## Entry point

- `layered_vtech_strategy.py`: new fail-closed Freqtrade shell.

The shell keeps a fixed 2x leverage default, but emits no entries until the layer adapters are implemented.

## Layer modules

```text
data_pool_layer.py
feature_layer.py
label_layer.py
model_layer.py
selection_layer.py
portfolio_layer.py
risk_layer.py
execution_layer.py
validation_layer.py
technical_feature_adapter.py
feature_diagnostics.py
strategy_layer_pipeline.py
```

Each module owns one contract. It must not reach into another layer's private state, place orders, or silently change experiment parameters.

## Naming

- Modules and functions: `lower_snake_case`.
- Classes: `UpperCamelCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Use complete domain names such as `calculate_risk_bounded_stake`.
- Do not use legacy aliases, one-letter domain variables, or hidden global state.

See `../docs/策略框架.md` for the full boundary and validation rules.
