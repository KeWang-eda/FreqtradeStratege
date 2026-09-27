# EXP-000 smoke 报告

- 分支：`experiment/EXP-000-baseline`
- 代码提交：`7d6236a`
- 策略：`VtechCryptoFreqAILeverageL2`
- 数据来源：本地 `experience10/user_data/data`
- 回测区间：`20240701-20240801`
- 运行方式：Freqtrade backtesting，`--cache none`
- 原始日志：`/tmp/exp000-smoke/run.log`
- 原始结果目录：`/tmp/exp000-smoke/`

## 结果

| 指标 | 数值 |
|---|---:|
| 交易数 | 275 |
| 结算收益 | 29.637 USDT |
| 收益率 | 29.64% |
| Wallet Sharpe | 4.67 |
| Wallet Calmar | 130.79 |
| 最大相对回撤 | 14.59% |
| 最大绝对回撤 | 20.36 USDT |
| 胜率 | 52.4% |
| 平均持仓 | 8:01:00 |

## 链路验证

- `py_compile`：通过。
- JSON 配置解析：通过。
- 隔离 userdir 策略加载：通过。
- FreqAI 训练/预测：通过。
- 回测退出码：0。
- 本轮未发现阻塞性 `ERROR` 或 `Traceback`。

## 决策

这是一个月 smoke，只证明迁移后的策略、配置、数据路径和 FreqAI 链路能够运行。
它不是样本外晋级证据，也没有替代父策略控制组。

结论：`smoke_passed`，EXP-000 仍为 `running`，不创建 `promote(EXP-000)`，不合并 `main`。
