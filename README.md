# Layered Vtech strategy framework

A clean-room framework for a Freqtrade futures strategy with independently testable layers for data pools, causal features, labels, risk models, cross-sectional selection, portfolio leverage, execution, and validation.

> Status: the causal-feature control is wired into the Freqtrade entry point and has been backtested. The model-driven cross-sectional pipeline is not promoted.

## Scope

This branch is a complete structural rewrite. It does not preserve or load the previous Vtech strategy classes. Previous strategy code and experiment records remain in Git history and on the historical `main` branch.

## Architecture

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

The same layer can be validated independently, but promotion always requires a combined parent-versus-candidate backtest.

## Repository layout

```text
FreqtradeStratege/
├── README.md
├── .gitattributes
├── .gitignore
├── configs/
│   ├── README.md
│   └── freqai/layered-vtech.example.json
├── docs/
│   ├── GIT仓库管理.md
│   ├── 策略框架.md
│   ├── 晋级门槛.md
│   ├── 实验记录模板.md
│   └── 收益报告模板.md
├── experiments/
│   ├── INDEX.md
│   └── README.md
└── strategies/
    ├── README.md
    ├── layered_vtech_strategy.py
    ├── technical_feature_adapter.py
    ├── strategy_layer_pipeline.py
    └── *_layer.py
```

## Technical feature source

The framework integrates [freqtrade/technical](https://github.com/freqtrade/technical) through an explicit allowlist adapter instead of importing the whole indicator catalogue.

| Item | Value |
|---|---|
| Adapter | `strategies/technical_feature_adapter.py` |
| Feature version | `technical-v1-causal` |
| Dependency pin | `requirements-framework.txt` (`technical==1.7.0`) |
| Documented boundary | [docs/技术特征适配.md](docs/技术特征适配.md) |
| Data pool boundary | [docs/数据池适配.md](docs/数据池适配.md) |
| Label boundary | [docs/标签层.md](docs/标签层.md) |
| Model boundary | [docs/模型层.md](docs/模型层.md) |
| Selection boundary | [docs/选股层.md](docs/选股层.md) |
| Portfolio and risk boundary | [docs/组合风控层.md](docs/组合风控层.md) |
| Execution boundary | [docs/执行层.md](docs/执行层.md) |
| Validation boundary | [docs/验证层.md](docs/验证层.md) |
| Parent comparison | [docs/父策略对照.md](docs/父策略对照.md) |
| Research conclusion | [docs/研究结论.md](docs/研究结论.md) |
| Logging standard | [docs/日志规范.md](docs/日志规范.md) |
| Layer audit | [docs/分层审计.md](docs/分层审计.md) |
| Composition pipeline | [docs/组合链路.md](docs/组合链路.md) |
| First candidate groups | Volatility, regime, momentum, trend, volume |
| Excluded | `chikou_span` (negative shift), deprecated `zema`, blind multi-timeframe merge, open interest without a point-in-time history |

A technical indicator is a candidate input. It is not a trading rule and not evidence of alpha until it passes time-split IC, correlation-cluster, stability, and out-of-sample checks.

## Layer contracts

| Module | Responsibility | Primary independent check |
|---|---|---|
| `data_pool_layer.py` | Point-in-time universe and data quality | Coverage, gaps, age, volume, minimum stake |
| `feature_layer.py` | Causal features | Leakage audit, IC, Rank IC, stability |
| `label_layer.py` | Future training targets | Label horizon and distribution |
| `model_layer.py` | Risk prediction | OOS ranking, error, calibration, early stopping |
| `selection_layer.py` | Same-timestamp candidate ranking | Precision@K, net edge, turnover |
| `portfolio_layer.py` | Weights, leverage, risk-budget stake | Target volatility, exposure, concentration |
| `risk_layer.py` | Approve, resize, or reject targets | Account risk, minimum stake, liquidation buffer |
| `execution_layer.py` | Exchange-ready order intent | Fees, funding, slippage, precision |
| `validation_layer.py` | Promotion evidence | DSR, PBO, purged validation, OOS gates |

## Leverage policy

The framework supports futures leverage explicitly. The initial shell uses a fixed 2x default and bounds it by the exchange limit.

```text
regime limit
    -> leverage callback
    -> risk budget
    -> stake = equity * risk / (leverage * stop distance)
    -> minimum stake and precision checks
    -> liquidation buffer
    -> order plan
```

A risk prediction is not automatically a profit probability. Dynamic leverage requires time-split calibration and independent validation before it can replace the fixed default.

## Development workflow

Create a branch for one layer or one experiment:

```bash
git switch -c experiment/EXP-001-data-pool
```

Record the parent commit, one changed variable, data snapshot, configuration, model identity, independent metrics, combined metrics, and the final decision.

Use explicit names:

- Modules, functions, and variables: `lower_snake_case`.
- Classes: `UpperCamelCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Experiment IDs: `EXP-XXX`.
- Branches: `experiment/EXP-XXX-name` or `fix/name`.

## Local checks

The skeleton can be checked without market data:

```bash
python -m compileall -q strategies
python -m py_compile strategies/*.py
```

The current shell intentionally produces no entry signals. Do not interpret a clean compile as a profitable strategy result.

## Promotion gates

A candidate must pass all of the following:

- Layer contract checks.
- Causal-data and no-lookahead checks.
- Parent and candidate use identical evaluation protocols.
- Wallet-level metrics are finite and reproducible.
- Independent time window confirms the result.
- Candidate wallet `Sharpe × Calmar` is strictly greater than the parent.
- `max_relative_drawdown < 30%`.
- Statistical validation covers multiple testing and temporal leakage.

## References

- [Freqtrade strategy quickstart](https://www.freqtrade.io/en/stable/strategy-101/)
- [Freqtrade backtesting](https://www.freqtrade.io/en/stable/backtesting/)
- [FreqAI configuration](https://www.freqtrade.io/en/stable/freqai-configuration/)
- [FreqAI feature engineering](https://www.freqtrade.io/en/stable/freqai-feature-engineering/)
- [Freqtrade leverage](https://www.freqtrade.io/en/stable/leverage/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide)
- [GitHub README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes)
