# Git repository management

## Scope

This repository contains one new layered Vtech strategy framework. Historical strategy files, historical configurations, and historical experiment records remain in Git history and on the original `main` branch; they are not part of this refactor branch.

## Branches

```text
main
└── refactor/layered-v1
```

- `main` is the historical repository line.
- `refactor/layered-v1` is the new framework line.
- Future work uses `experiment/EXP-XXX-layer-name` or `fix/description`.
- Do not merge a framework skeleton as a performance promotion.

## Framework files

- `strategies/*_layer.py`: independent layer contracts and structural validation.
- `strategies/strategy_layer_pipeline.py`: combined-pipeline boundary; it fails closed until adapters exist.
- `strategies/layered_vtech_strategy.py`: the only new Freqtrade entry point.
- `configs/freqai/layered-vtech.example.json`: sanitized configuration template.
- `experiments/INDEX.md`: planned layer experiments.

## Naming

Use Google Python Style and explicit domain names:

- Modules, functions, and variables: `lower_snake_case`.
- Classes: `UpperCamelCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Public names must describe their domain operation. Use `calculate_risk_bounded_stake`, not `calc`.
- Use `Layer` for layer contracts, `Snapshot` for point-in-time inputs, `Prediction` for model outputs, `Decision` for approvals, and `Plan` for executable intent.
- Use `EXP-XXX` for experiments and keep the experiment ID in branch names, manifests, metrics, and commit messages.

## Experiment rules

Every experiment records:

- Parent commit.
- One changed layer or variable family.
- Data snapshot and time range.
- Configuration and model identifier.
- Independent layer metrics.
- Combined parent-versus-candidate metrics.
- Artifact hashes and decision.

A contract can pass independently while the combined strategy fails. Both results must be recorded.

## Git hygiene

Do not commit:

- Secrets or private configuration.
- Market data, logs, SQLite databases, model caches, or generated backtest archives.
- Claims of performance that cannot be reproduced from a recorded commit and protocol.

## Commit prefixes

```text
docs: update framework documentation
feat: add a layer adapter
refactor: change structure without intended behavior change
fix: correct a framework defect
test: add contract validation
exp: record an experiment result
promote: promote a verified candidate
```

One commit should express one reason for change.
