# Experiments

This directory stores small, reviewable experiment records. It does not store full K-line datasets, runtime logs, SQLite databases, model caches, or backtest ZIP files.

Each experiment must use:

```text
experiments/EXP-XXX/
├── README.md
├── manifest.yaml
├── metrics.json
├── commands.txt
└── SHA256SUMS
```

The parent commit, one major variable, data snapshot, configuration, FreqAI identifier, and metric definitions are mandatory. An experiment can be `proposed`, `running`, `promoted`, `rejected`, or `blocked`.

The `main` branch contains promoted strategy versions only. Research branches must not be treated as production evidence.
