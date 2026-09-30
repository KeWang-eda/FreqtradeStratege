# Logging standard

The framework uses Python's standard `logging` package.[38] It does not add Loguru or structlog because Freqtrade already owns standard logging handlers, log files, console verbosity, and process lifecycle.

## Run modes

Set `LAYERED_RUN_MODE` before training or an offline experiment:

```text
training
backtest
validation
dry_run
live
```

Freqtrade runs can use its native `--logfile` and `-v`/`-vv` options. The framework events are emitted through named loggers below `layered_vtech`, so they flow into the same Freqtrade log file.

## Levels

| Level | Use |
|---|---|
| `DEBUG` | Per-layer counts, feature dimensions, signal counts, ranking counts, order-plan values. |
| `INFO` | Model fit completion, data-pool snapshots, strategy indicator summaries, run milestones. |
| `WARNING` | Fail-closed rejection, unavailable optional data, minimum-stake rejection, risk-limit rejection. |
| `ERROR` | Any uncaught layer exception, contract violation, model failure, pipeline not implemented. |
| `CRITICAL` | Reserved for a process-safety failure that must stop the run. |

`log_layer_event()` emits JSON payloads containing `event`, `run_mode`, `level`, and event-specific fields. `log_failures()` catches every uncaught exception at a public layer boundary, records `error_code`, function, exception type, message, and traceback, then re-raises the original exception. It never converts an error into a successful result.

## Layer evidence

Each layer reports enough information to answer both questions: “did it run?” and “what did it change?”

- Data pool: timestamp, pair count, timeframe.
- Features: row count, feature count, feature version, technical-candidate switch.
- Labels: row count, candidate count, horizon, label version.
- Model: identifier, pair, feature count, train/validation rows, best iteration, best score.
- Selection: candidate rows, timestamp count, selected rows, Top-K, risk penalty.
- Portfolio: selected count, long/short count, leverage, total stake.
- Risk: rejection reason, pair, side, requested and allowed leverage.
- Execution: rejection reason, stake, leverage, fee, slippage, order tag.
- Strategy: pair, rows, feature version, model identifier, long/short entry and exit counts.
- Validation: experiment, decision, reason, Sharpe, Calmar, drawdown, DSR, and PBO.

## Commands

```bash
LAYERED_RUN_MODE=training .venv/bin/python train.py
LAYERED_RUN_MODE=backtest freqtrade backtesting ... --logfile user_data/logs/layered-backtest.log -vv
LAYERED_RUN_MODE=dry_run freqtrade trade ... --logfile user_data/logs/layered-dry-run.log -v
LAYERED_RUN_MODE=live freqtrade trade ... --logfile user_data/logs/layered-live.log -v
```

The example configuration uses `user_data/logs/layered-vtech.log`; deployment configurations can override the path with Freqtrade's native `--logfile` option.

## Sources

[38] https://docs.python.org/3/library/logging.html
[39] https://docs.python.org/3/howto/logging-cookbook.html
[40] https://www.freqtrade.io/en/stable/commands/backtesting
