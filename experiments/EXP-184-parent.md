# EXP-184：正式生产父策略迁移报告

- 状态：`promoted`，已合并 `main`
- 主合并提交：`e32bc44adc950499b4f9c127edfb9d440e71f146`
- 策略：`VtechCryptoFreqAIRiskL20TimeEfficiency36Enabled`
- 分支：`experiment/EXP-184-formal-parent`
- 原始迁移提交：`be37a3d exp(EXP-184): import formal parent strategy chain`
- 重构提交：`ced545f refactor(EXP-184): make parent chain deployable`
- 来源：`experience61` 与 `/home/wangke/note/Vtech多空与FreqAI调优记录.md`

## 1. 为什么迁移 EXP184

`experience61` 是当前最新实验归档，但最新的 EXP235–EXP241 都是只读研究/审计，报告明确写着不训练、不换 identifier、不改生产。

`OOS-190-REPORT.md` 明确记录：当前生产父版本仍为 Experiment 184。Experiment 190 只有条件晋级，早期窗口乘积低于父184，不能替换父版本。因此本次迁移的是正式父策略 EXP184，不是把最新研究文件误当成生产策略。

## 2. 迁移范围

按真实 import 继承链迁移：

```text
VtechCryptoFreqAIRiskL20TimeEfficiency36Enabled
  -> VtechCryptoFreqAIRiskL20TimeEfficiency48Enabled
  -> VtechCryptoFreqAIRiskL20TimeEfficiency48
  -> VtechCryptoFreqAIRiskL20DynamicROI100
  -> VtechCryptoFreqAIRiskL20VolumeShock
  -> VtechCryptoFreqAIRiskL20DynamicROI10
  -> VtechCryptoFreqAIRiskL20RecentDropPenaltyP050
  -> VtechCryptoFreqAIRiskL20RecentDropReturnActivated
  -> VtechCryptoFreqAIRiskL20DirectionBudgetGrid
  -> VtechCryptoFreqAIRiskL20BudgetROI30Grid
  -> VtechCryptoFreqAIRiskL20BudgetGrid
  -> VtechCryptoFreqAIRisk
  -> util.py
```

另保留仓库已有的 `XGBoostRegressorES`，配置通过官方支持的 `freqaimodel_path` 指向 `strategies/freqaimodels`。

不迁移：K线、FreqAI 模型、预测缓存、日志、SQLite、回测 ZIP 和未晋级实验叶子。

## 3. 行为不变重构

`ced545f` 只做部署与可读性重构：

- 给 EXP184 36h/48h stale 回调补充类型注解和 docstring；
- 将动态 ROI 中的运行时 `__import__("numpy")`、`__import__("pandas")` 改为普通模块导入；
- 整理 VolumeShock 的第三方导入顺序；
- 配置显式加入 `datadir: user_data/data`；
- 配置显式加入 `freqaimodel_path: strategies/freqaimodels`；
- 配置日志改为 `user_data/logs/exp184-*.log`；
- 未改变交易条件、风险参数、FreqAI identifier 或退出标签。

## 4. FreqAI 与运行口径

| 项目 | 值 |
|---|---|
| timeframe | 1h |
| 训练窗口 | 365 天 |
| 滚动预测窗口 | 30 天 |
| label_period_candles | 8 |
| include_shifted_candles | 2 |
| 最大持仓 | 3 |
| 杠杆 | 20x |
| 手续费 | 0.05% |
| stale 时间门 | 36h |
| stale 收益门 | 0.002 |
| 生产 identifier | `vtech-exp184-time36-enabled-main-volume` |
| 模型类 | `XGBoostRegressorES` |

## 5. 真实 smoke 验证

命令使用仓库策略、隔离 `/tmp` userdir、只读本地模型和真实 Freqtrade backtesting：

```bash
/home/wangke/project/freqtrade/.venv/bin/freqtrade backtesting \
  --userdir /tmp/exp184-runtime/user_data \
  --strategy-path /home/wangke/project/FreqtradeStratege/strategies \
  --config configs/freqai/EXP-184-production.json \
  --strategy VtechCryptoFreqAIRiskL20TimeEfficiency36Enabled \
  --datadir /tmp/exp184-runtime/user_data/data \
  --timerange 20260920-20260924 \
  --pairs BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \
  --backtest-directory /tmp/exp184-runtime/user_data/backtest_results \
  --cache none --export none
```

结果：

- 退出码：0；
- FreqAI 自定义模型解析成功；
- 策略加载成功；
- 真实回测覆盖 3 天；
- 交易数：4；
- 结果：-0.140 USDT；
- closed-trades Sharpe：-3.29；
- closed-trades Calmar：-270.84；
- 最大相对回撤：0.33%；
- 运行期没有模型加载错误、ERROR 或 Traceback。

该 smoke 只证明仓库代码、配置、模型解析和交易链路可运行，不作为 EXP184 的长窗口晋级收益证据。

## 6. 历史长窗口证据

历史正式父策略的同口径 control184long 记录在 `experience61/OOS-190-REPORT.md`：

| 指标 | 父184 control184long |
|---|---:|
| 交易数 | 34,624 |
| 收益 USDT | 30,307,186.25 |
| Wallet Sharpe | 6.107000 |
| Wallet Calmar | 15,964,166.0 |
| Wallet Sharpe × Calmar | 97,493,162 |
| 最大相对回撤 | 19.4681% |
| 时间范围 | 2022-07-03~2026-09-01 |

这些数字是原始 experience 归档证据，不冒充本次 3 天 smoke 的结果；本次迁移也没有把 ZIP 加入 Git。

## 7. 模型交付

模型不进入 Git：

```text
/home/wangke/project/freqtrade/user_data/models/vtech-exp184-time36-enabled-main-volume
```

- 约 17.7 MiB；
- 1531 个文件；
- 765 个 metadata 文件；
- Git 不跟踪；
- 远端部署必须单独复制到 `user_data/models/vtech-exp184-time36-enabled-main-volume/`；
- 复制后必须检查 metadata 的训练机路径和远端 userdir。

## 8. 旁线实验边界

- EXP190：条件晋级，不能替换 EXP184；
- EXP205/208/214：RB010 条件候选，未进入主线；
- EXP235–EXP241：特征/标签/Rank IC/框架审计，明确未换 identifier、未改生产；
- 以上内容只保留在 `experience61` 原始归档，不进入本次生产策略提交。
