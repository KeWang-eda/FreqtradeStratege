# 本次验证结果（2026-10-17）

原始 commit：`22d6ee5254c899b262201277dca54c0f71a53c20`。环境沿用 Freqtrade 2026.7 / Python 3.13.13 / pandas 3.0.5 / NumPy 2.5.2 / scikit-learn 1.9.0 / XGBoost 3.4.1，完整依赖见 baseline/environment.freeze.txt。

| 检查 | 实际结果 |
| --- | --- |
| 修改前原测试 | 11 passed |
| 完整分层测试 | **86 passed**，5.80s；JUnit：`/tmp/quant-refactor-tests.xml` |
| Ruff lint | All checks passed |
| Ruff format | 66 files already formatted |
| Git 空白错误 | `git diff --check` 通过 |
| 原配置参数对照 | 去除注释后与冻结配置完全一致 |
| 原版特征/标签样本 | 80 根固定数据、三个 period、raw/volnorm 回归通过 |
| Freqtrade 策略发现 | 原生 list-strategies 能发现 MyStrategy |
| FreqAI 当前版本集成 | 实际数据厨房、BaseRegressionModel.train/predict、两个原模型通过 |
| 核心依赖隔离 | 导入 quant_strategy.api 后未加载任何 freqtrade 模块 |
| 本地行情独立研究 | BTC/ETH 的 Ridge、XGBoost 都成功完成三折训练、预测和审计 |
| XGBoost 工件重载 | artifact-check 通过，校验 28 个文件、6 个逐币对模型 |
| 原版真实交易回测 | Binance 市场接口请求超时，退出码 2，**待验收** |
| 新旧真实交易/截断对照 | 因缺少原版回测结果，**待验收** |

NumPy 2.5 与当前 joblib 组合在反序列化数组时产生 151 条 DeprecationWarning，来自依赖库，测试及工件预测均通过。本次未升级或替换依赖。

本地研究样例结果位于 `/tmp/quant-refactor-research/ridge-smoke` 和 `/tmp/quant-refactor-research/xgboost-reviewed`。前者为初步 Ridge 冒烟运行；后者记录 XGBoost 三折、n_estimators=40 的完整研究工件，未评估最终 holdout。合成数据 E2E 另覆盖两个模型、两种标签和显式最终 holdout。

上述证据证明指定代码契约、信息边界与研究流程可以运行。真实 Freqtrade 交易一致性及第 21 节完整生产验收仍须在 Binance 连接可用时完成，未据研究结果切换生产模型。
