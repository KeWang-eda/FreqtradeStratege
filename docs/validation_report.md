# 本次验证结果（2026-10-17）

原始 commit：`22d6ee5254c899b262201277dca54c0f71a53c20`。环境沿用 Freqtrade 2026.7 / Python 3.13.13 / pandas 3.0.5 / NumPy 2.5.2 / scikit-learn 1.9.0 / XGBoost 3.4.1，完整依赖见 baseline/environment.freeze.txt。

| 检查 | 实际结果 |
| --- | --- |
| 修改前原测试 | 11 passed |
| 完整分层测试 | **115 passed**，33.47s；包含新增离线快照及指标回归测试，JUnit：`docs/baseline/acceptance/offline-pytest.xml`；原 96 项证据保留 |
| Ruff lint | All checks passed |
| Ruff format | 73 files already formatted |
| Git 空白错误 | 已暂存源码/配置/文档检查通过；排除验收目录原始 `.log`，保留终端输出及其原有哈希 |
| 原配置参数对照 | 去除注释后与冻结配置完全一致 |
| 原版特征/标签样本 | 80 根固定数据、三个 period、raw/volnorm 回归通过 |
| Freqtrade 策略发现 | 原生 list-strategies 能发现 MyStrategy |
| FreqAI 当前版本集成 | 实际数据厨房、BaseRegressionModel.train/predict、两个原模型通过 |
| 核心依赖隔离 | 导入 quant_strategy.api 后未加载任何 freqtrade 模块 |
| 本地行情独立研究 | BTC/ETH 的 Ridge、XGBoost 都成功完成三折训练、预测和审计 |
| XGBoost 工件重载 | artifact-check 通过，校验 28 个文件、6 个逐币对模型 |
| 原版/新版真实交易回测 | mihomo 代理 + 本地 BTC/ETH 数据，两周各 13 笔、三周各 25 笔 |
| 新旧真实交易/预测/信号 | 两个窗口完整交易、signals/rejected/exited、4/6 个逐窗口预测及训练 schema 对照通过 |
| 短/长窗口截断对照 | 原版/新版均通过，重叠区间各 13 笔，终点强平按规则排除 |
| 完全离线原生引擎回测 | 独立网络命名空间 + 真实元数据快照，BTC/ETH 两周 13 笔交易/26 订单，预测/信号/115 项结果字段与联网基线一致 |

NumPy 2.5 与当前 joblib 组合在反序列化数组时产生 261 条 DeprecationWarning，来自依赖库，测试及工件预测均通过。本次未升级或替换依赖。

本地研究样例结果位于 `/tmp/quant-refactor-research/ridge-smoke` 和 `/tmp/quant-refactor-research/xgboost-reviewed`。前者为初步 Ridge 冒烟运行；后者记录 XGBoost 三折、n_estimators=40 的完整研究工件，未评估最终 holdout。合成数据 E2E 另覆盖两个模型、两种标签和显式最终 holdout。

真实回测的原生结果 zip、日志、源码、输入指纹和完整机器可读报告已保存到 [baseline/acceptance/](baseline/acceptance/README.md)。之前超时的原因是未使用本机已运行的 mihomo；显式代理后框架的市场规则查询正常，行情及合约历史仍从本地文件读取。

上述证据覆盖指定代码契约、信息边界、研究流程及 BTC/ETH 两窗口的真实交易一致性。全部 72 个币对、其他历史窗口及第 21 节正式生产切换仍需按各自范围验证，未据研究结果切换生产模型。

后续网络专项进一步验证：独立研究在请求拦截下读取本地数据完成训练与比较；专用历史回测覆盖将 exchangeInfo 请求从 3 个减少到 1 个，交易/预测/信号保持一致。原生回测完全断网仍受必要元数据初始化限制，详细调用链、修复与运行命令见 [本地数据网络排查报告](local_data_network_audit.md)。

再后续的独立快照适配层已消除指定场景的最后一次市场元数据请求，原装 CLI 的行为保留。运行方式、快照真实性、失败检查和断网系统调用证据见[完全离线回测报告](offline_backtest_snapshot.md)。实盘联网类保持原样，未执行真实账户和订单验收。
