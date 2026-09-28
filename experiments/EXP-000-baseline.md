# EXP-000：当前 L=2 FreqAI 控制基线迁移

- 分支：`experiment/EXP-000-baseline`
- 父提交：`753f5ce`
- 来源：`/home/wangke/project/freqtrade/user_data/strategies`
- 主记录：`/home/wangke/note/Vtech多空与FreqAI调优记录.md`
- 目标策略：`VtechCryptoFreqAILeverageL2`
- 状态：`promoted baseline`

## 迁移范围

只迁移当前 L=2 控制链运行所需的小型源码和脱敏配置：

- Vtech 基础多空策略。
- FreqAI 风险策略。
- L=2 杠杆包装类。
- 公共 `util.py`。
- 自定义 `XGBoostRegressorES`。
- L=2 FreqAI 配置和参数覆盖文件。

不迁移：K 线、日志、SQLite、回测 ZIP、完整 `user_data/models`、历史备份和其他实验叶子策略。

## 当前验证

- Python 编译：通过。
- 配置 JSON 解析：通过。
- 隔离 userdir 的 `freqtrade list-strategies`：通过，`VtechCryptoFreqAILeverageL2` 为 `OK`。
- 完整真实回测：通过（786 天，6713 笔，932.55997 USDT）。
- 历史结果复用：禁止。基础策略/杠杆/公共模块与 `experience10` 的 SHA256 不完全一致，历史长窗口结果不能直接作为当前分支晋级证据。
- 晋级状态：已晋级并进入 `main`，tag 为 `promoted/EXP-000`。

## 晋级条件

必须在本仓库路径下完成真实冒烟和父控制口径回测，并生成收益报告。
只有 Wallet Sharpe × Wallet Calmar 高于父策略且 `max_relative_drawdown < 30%`，才允许 `promote(EXP-000)`。
