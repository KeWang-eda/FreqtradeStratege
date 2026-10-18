# BTC/ETH/BNB 受控研究准备与 P3 基础设施汇总

本文件是本轮唯一阅读入口。它记录 2026-10-18 这一轮实际执行的代码、测试、真实开发训练和独立验收；旧报告和旧证据保留，不作为本轮结果。正式 OOS、候选模型优选、收益排名、生产模型更新和实盘仍被锁定。

## A. 本轮结论

| 范围 | 状态 | 依据 |
|---|---|---|
| 研究合同、配置绑定和代码实现 | PASS | 冻结合同、源码指纹校验、全量测试 |
| BTC/ETH/BNB 预测数据源质量 | PARTIAL | futures/mark 通过；Funding 历史支付证据缺失 |
| P3 Walk-Forward、purge、embargo、holdout 基础设施 | PASS（开发范围） | 3 折真实三币开发训练和独立重放 |
| 预测指标与基准准备 | PASS（接口/开发验证） | XGBoost、mean-train、zero 同折输出；未排名 |
| 交易成本评估 | BLOCKED | 滑点和历史 Funding 支付规则没有可信证据 |
| 独立工程验收 | PASS | `engineering_status=PASS`，违规数 0 |
| 正式研究准入 | **BLOCKED** | 总验收 `status=BLOCKED`，`formal_research_allowed=false` |

独立验收没有把开发结果升级成正式结果。正式研究需要 Funding 规则、point-in-time universe、未暴露的最终 holdout 和后续正式 P3–P6 证据。

## B. 基线与冻结合同

本轮开始时本地和远端均为 `main`、HEAD `caf2d8edf338a07e698b0d25025fd7495e39445f`；远端 `origin/main` 复核为同一提交。环境为 Python 3.13.13、Freqtrade 2026.7、CCXT 4.5.75、XGBoost 3.4.1、pandas 3.0.5、NumPy 2.5.2、scikit-learn 1.9.0。旧基线重新运行得到 534 passed；本轮最终全量套件为 729 passed，旧结果没有被复用。

冻结合同为 [btc_eth_bnb_v1.json](../configs/contracts/btc_eth_bnb_v1.json)，SHA-256 为 `86d0450af446b17a95bbffa84b88aebf674bf535b0454a15014a3cc61d16651a`。配置合并顺序固定为 `configs/base.yaml`、`configs/research.yaml`、`configs/experiments/btc_eth_bnb_controlled_v1.yaml`。生产默认配置没有改写：原来的 raw/Ridge 定义仍保留；独立受控配置明确绑定生产 `volnorm`、4h、horizon=3 和 `XGBoostRegressorES` 参数。

合同固定三币、4h、未来 3 根 K 线、ATR(14) volnorm 标签、严格 `label_end_time >= test_start` purge、3 折全局时间 Walk-Forward、3 根 K 线 embargo、最后 15% 全局时间 holdout。实际生产特征 schema 为 BTC 92 列、ETH 92 列、BNB 136 列。开发探针只使用最早 4380 个共同有效时间点；该前缀的保留块是基础设施 fixture，不是真正独立的最终 holdout。

全历史共同有效时间为 14,535 个；真实最后 15% 从 2025-10-17 04:00 UTC 开始，已与旧诊断/旧训练证据重叠。因此即使切分器正确，历史独立性也不能恢复，最终 holdout 仍然只能是 BLOCKED。

## C. 工作流 A：三币数据治理与 Funding

审计只读读取 9 个本地文件，文件在审计期间未被替换，也没有下载、补零、插值或修改原始行情。源集合指纹为 `c005a3a8178689cf8defd4f31c20dc89de4c5d8d4b8461dd07b00bd8604253f6`。

| 交易对 | futures | mark | funding | 预测准备 | 交易成本 |
|---|---:|---:|---:|---|---|
| BTC/USDT:USDT | 14,880，2020-01-01 00:00 至 2026-10-15 20:00，4h 连续 | 59,443，2020-01-01 至 2026-10-12 18:00，1h 连续 | 7,429，2020-01-01 至 2026-10-12 00:00，观测间隔 8h | PASS（仅 OHLCV 源质量） | BLOCKED |
| ETH/USDT:USDT | 14,880，同上 | 59,443，同上 | 7,429，同上 | PASS（仅 OHLCV 源质量） | BLOCKED |
| BNB/USDT:USDT | 14,638，2020-02-10 08:00 至 2026-10-15 20:00，4h 连续 | 59,443，2020-01-01 至 2026-10-12 18:00，1h 连续 | 7,308，2020-02-10 08:00 至 2026-10-12 00:00，观测间隔 8h | PASS（仅 OHLCV 源质量） | BLOCKED |

三类文件均无重复或空时间戳，futures/mark 的内部间隔通过；Funding 文件的 8 小时观测间隔不等于历史支付日历。没有权威的逐币历史支付事件、规则变更和采集来源证明，因此 Funding 仍为 BLOCKED，未知费率不会被替换为零。BNB 的 mark 早于 futures 上市时间，未用于证明 BNB 历史合约成本。

当前 market snapshot 只提供当前响应及 onboard claims，不能证明历史 point-in-time 可交易 universe；研究范围只能表述为“当前指定三币在本地历史数据上的条件性研究”，不能排除幸存者偏差。

证据：[source_audit.json](acceptance/controlled_p3_20261018T111700Z/execution/source_audit.json)、[audit_controlled_sources.py](../tools/audit_controlled_sources.py)。

## D. 工作流 B：P3 切分、训练与 holdout 隔离

最终开发执行目录为 [execution](acceptance/controlled_p3_20261018T111700Z/execution)。它实际训练 3 折 × 3 币，共 9 个 XGBoost 折模型，同时生成 `mean_train` 和 `zero` 基准；预测共 13,770 行。每一折的外层测试为 1,530 行，三币各 510 行；每折 purge 为 9 行（三币各 3 行），训练、验证和测试样本身份无重叠，独立重放违规数为 0。访问审计共 40 个事件，重建也是 40 个，holdout 数值访问为 0。

开发折边界如下（时间是全局 UTC 边界）：

| 折 | 训练样本 | 测试样本 | purge | 训练结束 | 测试开始 | 测试结束 |
|---|---:|---:|---:|---|---|---|
| 0 | 6,561 | 1,530 | 9 | 2021-02-25 12:00 | 2021-02-26 04:00 | 2021-05-22 00:00 |
| 1 | 8,091 | 1,530 | 9 | 2021-05-21 12:00 | 2021-05-22 04:00 | 2021-08-15 00:00 |
| 2 | 9,621 | 1,530 | 9 | 2021-08-14 12:00 | 2021-08-15 04:00 | 2021-11-08 00:00 |

每个训练样本均重新验证 `label_end_time < test_start`；验证集内部再次执行原生切分和 purge，预处理器只使用保留训练 ID。`DevelopmentAccess` 拒绝 holdout/guard 的 fit、train、tune、predict 和 metrics 操作。模型、预处理器、预测、折计划、数据访问日志和输入指纹均独立保存；失败训练会保留失败状态。

真实最终 holdout 的身份仍被注册但没有 materialize 数值、没有生成指标。独立验收重新读取日期身份、重算计划、重算特征/标签前缀、重放模型和访问日志，结果为 `violations=0`。

## E. 工作流 C/D：预测指标、基准和交易成本

开发输出按折、按币和 pooled 计算 MAE、RMSE、方向准确率、Pearson/Spearman IC，并拒绝 NaN、Inf、缺失预测和样本 ID 错位。接口验证的 pooled 开发统计如下；这些数字不是正式 OOS，也没有用于挑选模型：

| 模型 | 样本 | MAE | RMSE | 方向准确率 | Spearman IC |
|---|---:|---:|---:|---:|---:|
| XGBoostRegressorES | 4,590 | 0.84104 | 1.15049 | 0.52723 | -0.01068 |
| mean_train | 4,590 | 0.84017 | 1.14695 | 0.52418 | -0.00828 |
| zero | 4,590 | 0.83837 | 1.14785 | 0.00000 | undefined（常数预测） |

成本合同来自实际安装的 Freqtrade 源码和当前配置：单边手续费 0.0005，预先声明 1x/2x 情景；成交、仓位和 Funding 语义已记录。滑点未知，历史 Funding 支付时间表未证明，所以交易评估为 BLOCKED；本轮没有宣称盈利、没有正式收益排名。

## F. 测试、网络审计和需求追踪

最终全量命令：

```bash
PYTHONPATH=src:. ../freqtrade/.venv/bin/python -m pytest -q \
  --basetemp=/tmp/quant-p3-final-suite-111700 \
  --junitxml=docs/acceptance/controlled_p3_20261018T111700Z/final_tests.xml
```

结果：退出码 0，729 passed、0 failed、0 skipped，耗时 196.09 秒。Ruff 对 `src tools tests` 通过，格式检查显示 125 files already formatted，`git diff --check` 通过。控制性 P3 单元/集成套件为 142 passed；原生边界、数据治理和特征因果性定向套件为 40 passed；三币治理/成本定向套件为 41 passed。测试回执由独立收集器重新计算，收集节点与实际 JUnit 完全一致，且显式清除 `PYTEST_ADDOPTS` 过滤影响。

真实开发训练命令使用 `unshare -Urn` 和 `strace -f -e trace=network`，退出码 0。Python 网络审计的 HTTP、socket、DNS 列表均为空，允许的进程事件只有固定的本地 Git provenance 查询，拒绝事件数为 0；系统调用记录保存为 [system_network.strace](acceptance/controlled_p3_20261018T111700Z/system_network.strace)。

需求—测试追踪摘要：

| ID | 要求 | 负向故障注入/验证 | 本轮结果 |
|---|---|---|---|
| DATA-001 | 三币源文件只读、时间连续、指纹绑定 | 缺文件、重复、NaN、负价、间隔缺口、读中替换 | 通过；Funding 证据另行 BLOCKED |
| LEAK-001 | 未来扰动不能改变当前生产特征 | future shift、全样本统计、跨币未来排名、截断 | 通过，92/92/136 schema |
| SPLIT-001 | 全局时间切分且标签边界严格 purge | 等于/超过边界、跨币拆分、重叠 ID、holdout 访问 | 通过，违规 0 |
| MODEL-001 | 预测指标拒绝非法输入并与基准同折 | NaN/Inf、缺失预测、错位 ID、不可比标签 | 通过；未排名 |
| EXP-001 | 工件、输入、代码、环境和回执可追溯 | 重哈希篡改、额外/缺失工件、旧目录复用、过滤测试回执 | 通过 |
| GATE-001 | 独立验收 fail-closed | 伪造 PASS、Funding/holdout/成本缺证据 | 通过拒绝；总状态 BLOCKED |

定向测试和红测的原始日志、JUnit、真实模型工件和访问日志位于上述执行目录；旧的中止/源码漂移尝试位于 `controlled_p3_20261018T022949Z` 和 `controlled_p3_20261018T111500Z`，均明确保留且不计入最终通过统计。

## G. 独立验收、改动与后续准入

独立命令：

```bash
PYTHONPATH=src:. ../freqtrade/.venv/bin/python tools/accept_training_readiness.py \
  --controlled \
  --evidence docs/acceptance/controlled_p3_20261018T111700Z/execution \
  --test-run docs/acceptance/controlled_p3_20261018T111700Z/test_run.json \
  --output docs/acceptance/controlled_p3_20261018T111700Z/independent
```

退出码为 2，含义是工程验收通过但正式研究阻断。原始结果见 [acceptance.json](acceptance/controlled_p3_20261018T111700Z/independent/acceptance.json)：`engineering_status=PASS`、`status=BLOCKED`、`formal_research_allowed=false`、`violations=0`。验收器重新计算了源文件和合同绑定、完整测试节点、全局切分、标签结束时间、预处理器 fit ID、模型预测、指标、40 条访问事件和工件指纹，没有只读取人工状态字符串。

主要代码与测试变更：

- 新增 `src/quant_strategy/research/` 下合同、数据治理、native panel、split、fold training、evaluation、costs 和 controlled 验收模块。
- 新增三币研究配置、冻结合同和合同生成工具。
- 新增 `prepare_controlled_research.py`、`accept_controlled_research.py`、`audit_controlled_sources.py`；正式入口对受控合同 fail-closed，普通生产入口未被改成离线模式。
- 新增合同、切分、holdout、指标、治理、回执和真实折训练测试；迁移旧的真实 fixture 到共同早期窗口，避免把真实历史尾部当作调试数据。
- `verify_complete_test_execution` 固定无外部 `PYTEST_ADDOPTS` 的全量收集环境；独立验收绑定证据父目录、冻结输入 SHA 和 source audit 顶层字段。

未改变生产策略的交易逻辑、标签公式、特征含义、模型参数、风险控制或生产默认配置。未提交、未 push；当前工作区保留上述代码、测试、配置和本轮证据目录。大型模型/数据工件只留在本地证据目录，不应提交到 Git。

解除正式研究锁定前必须完成：

1. 获取 BTC/ETH/BNB 逐币、逐历史时期的权威 Funding 支付事件及规则变更证据，并把支付时间与费率观测对齐。
2. 获取 point-in-time listing/delisting/contract-status universe 证据，或明确接受幸存者偏差并修改研究问题。
3. 重新建立完全未暴露的最终 holdout；当前最后 15% 已被历史诊断/训练访问，不能通过改目录名恢复独立性。
4. 在上述条件通过后，另行完成正式 P3–P6 的折级效果、交易成本、实验 lineage 和最终 Gate；开发指标不得升级为正式 OOS 结论。
