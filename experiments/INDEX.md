# Experiment index

This branch starts a new strategy framework. Historical EXP-000 and EXP-184 records were intentionally removed from this refactor branch; they remain available on `main` and in Git history.

## Framework baseline

| Item | Value |
|---|---|
| Branch | `refactor/layered-v1` |
| Framework version | `0.1.0-skeleton` |
| Strategy entry point | `strategies/layered_vtech_strategy.py` |
| Current status | Architecture only; no performance claim |
| Promotion status | Not eligible |

## First planned experiments

| Experiment | Layer | Question | Status |
|---|---|---|---|
| EXP-001 | Data pool | Can a point-in-time liquid universe be built without lookahead? | Proposed |
| EXP-002 | Feature | Which causal features pass multi-window IC and cluster checks? | Proposed |
| EXP-003 | Model | Does risk prediction improve OOS risk ranking? | Proposed |
| EXP-004 | Selection | Does same-timestamp Top-K net edge beat the rule baseline? | Proposed |
| EXP-005 | Portfolio | Does risk-budgeted leverage preserve account risk? | Proposed |
| EXP-006 | Execution | Do fees, funding, slippage, and precision change the edge? | Proposed |
| EXP-007 | Validation | Does the candidate survive purged validation and promotion gates? | Proposed |

## Rules

Each experiment starts from the latest framework commit, changes one layer or one parameter family, and records its parent commit, data snapshot, configuration, metrics, and decision. A layer result never becomes a production result without combined validation.
