# 训练就绪修复与独立验收总汇总

**正式研究准入：BLOCKED，当前不允许启动正式 OOS 模型研究、候选模型优选或实盘。** 原生训练标签跨界已修复，真实训练与独立重算通过；Funding 历史结算时间表、全币训练范围和后续正式研究 Gate 仍不完整。工程正确性、开发训练成功、预测能力、交易盈利与生产准入是不同结论。

本文件是本轮**唯一的阅读入口**。下文所有 JSON、JUnit、日志与 Parquet 都是证据附件，不需要逐份阅读。证据根目录：[`acceptance/training_repair_20261018T010644Z/`](acceptance/training_repair_20261018T010644Z/)。旧报告没有删除；旧的 `0c31df8 / 298 passed` 和上一轮 `4ba4fe8 / 398 passed / FAIL` 均不冒充本轮结果。

## 1. 基线、范围与状态

执行日期：2026-10-18，时间均为 UTC。起始分支 `main`，HEAD 与远程 `origin/main` 均为 `4ba4fe83f46a0bd58b06f9765c3368eccd1b528f`，初始工作区干净；本轮未 reset、checkout、clean 或丢弃用户工作。测试针对该提交上的修复工作区执行，源码/测试逐文件 SHA 记录于 `test_context.json`。提交后的文档后继版本通过祖先关系与源码 SHA 核验，不假称测试发生在未来的提交上。

| 环境 | 本轮实际版本 |
| --- | --- |
| Python / Freqtrade | 3.13.13 / 2026.7；FreqAI 为该安装包的一部分，无单独版本 |
| CCXT / XGBoost | 4.5.75 / 3.4.1 |
| pandas / NumPy / scikit-learn | 3.0.5 / 2.5.2 / 1.9.0 |
| TA-Lib / technical / PyArrow | 0.7.1 / 1.7.0 / 25.0.1 |

本轮没有升级依赖或修改虚拟环境源码。起始全量测试实际重新执行：**398 passed / 0 failed / 0 skipped，56.75 秒**。原生旧拆分用当前真实 BTC/ETH 数据重新复现，各有 3 个训练标签接触或越过早停验证边界，合计 6 个；详见 `before_native_boundaries.json`。

| 必须分别报告的状态 | 结果 | 含义 |
| --- | --- | --- |
| 代码修复 | PASS，限已支持配置与已验收范围 | pre-fit purge、身份对齐、缓存、证据门禁、原生特征审计已落地；不表示未实现能力已完成 |
| 自动化测试 | 见第 5 节最终统计 | 包含真实训练、系统隔离回测与故障注入，跳过不算通过 |
| 真实端到端训练 | PASS，开发验证范围 | BTC/ETH/BNB、完整配置训练期、真实 XGBoost、全新隔离 userdir；不是正式 OOS |
| 数据治理 | PARTIAL；原生正式 Funding 评估 BLOCKED | 原始数据只读、缺口与指纹已检查；未知支付时间表没有被补零或宣称可信 |
| 独立工程验收 | PASS，三币真实工件范围 | 重新生成特征/标签、重算原切分与 purge、重拟合预处理器、重放模型预测 |
| 正式研究准入 | **BLOCKED** | 独立总 Gate 与 `formal-run` 均拒绝，不可用开发结果代替正式前置条件 |

| 六阶段 | 当前状态 | 本轮已验证内容 / 尚未满足的条件 |
| --- | --- | --- |
| P1 数据 | PASS，有范围 | 研究 OHLCV 样本治理与隔离通过；72 币 Funding 不在这一 PASS 的批准范围内 |
| P2 防泄漏 | PARTIAL | 全 72 币特征因果性通过、三币原生训练工程检查通过；未对全 72 币完成真实训练，历史 universe 证据另缺 |
| P3 切分与 Walk-Forward | BLOCKED | 三类切分基础设施真实数据测试通过；正式逐折训练/验证/holdout 解锁协议与独立 Gate 未完成 |
| P4 模型/交易效果 | BLOCKED | 指标非法输入与手算误差验证已修；正式基准、成本敏感性、不确定性与样本外效果未执行 |
| P5 正式实验治理 | BLOCKED | 开发/正式隔离、指纹与比较可比性通过；完整正式恢复、双引擎 lineage 等尚未验收 |
| P6 总验收 | **BLOCKED** | 独立聚合实际执行；必要资料与阶段未齐，正式准入 false |

## 2. 根因、修复位置与行为影响

### 2.1 原生训练边界：必须在所有拟合之前 purge

实际安装源码调用链是：

```text
FreqAI 截取外层历史训练区间并生成标签
→ BaseRegressionModel.train
→ DataKitchen.filter_features
→ make_train_test_datasets（按行、shuffle=false）
→ fit_labels
→ feature_pipeline.fit_transform
→ label_pipeline.fit_transform
→ validation transform
→ XGBoostRegressorES.fit / early stopping
```

上游内部训练/早停验证拆分没有考虑标签未来跨度。只修改 `fit()` 会太晚，scaler、标签均值等已学习跨界行。采用独立本地适配层覆盖自定义模型的 `train()` 生命周期，复用原生过滤、拆分、pipeline、模型与 callbacks；在 `fit_labels` 和所有 pipeline 拟合前完成严格 purge。未修改 Freqtrade/CCXT 安装源码，没有全局猴子补丁。该生命周期及缓存合同校验实际安装实现 SHA；依赖升级必须重新审查。

`native_boundaries.py` 对未经 purge 的上游 splitter 的诊断仍会返回 FAIL，相应旧故障检出测试继续保留。正式就绪检查现在读取并独立重算实际修复训练产生的工件，不把原始 splitter 的已知缺陷改判为 PASS，也不只修改状态字符串来过门禁。

`src/quant_strategy/training/native_isolation.py` 与 `freqaimodels/XGBoostRegressorES.py` 保证：

- K 线 open 为原始时间，特征可用时间为 close；horizon=3 的标签在未来第 3 根 close 完成。`validation_start` 固定为原始首个验证样本可用时间。
- **`label_end_time >= validation_start` 一律剔除**；保留行严格满足 `<`。不移动验证起点，不把 `>=` 改为 `>`。
- X、y、权重与 metadata 同步按原身份筛选；保留索引，导出 pair/time/sample_id/原归属/最终归属/原因。未通过重置索引掩盖错位。
- Datasieve 原生会重建 RangeIndex，因此使用 `IdentityPreservingPipeline` 恢复可核验身份；原生 DI 过滤验证行的映射被保留。
- scaler、标签 pipeline、标签统计仅拟合保留训练行；验证集只 transform。复用 DataKitchen 的下一窗口不会继承上一窗口审计身份。
- 重复同一输入训练不能覆盖旧审计；路径由交易对、输入内容、训练合同决定，两 fresh userdir 的逻辑引用一致。
- 不支持的 shuffle/reverse、SVM/DBSCAN、noise、continual learning 等配置明确拒绝。`test_size=0` 真实训练通过；horizon=0 不符合当前未来目标契约，明确拒绝，不声称支持。

**必要影响已明确接受并测量：** purge 改变训练样本集合，因此模型与交易结果会变化；交易规则没有重写。标签公式、volnorm、4h/horizon3、特征列序、365 天训练期、7 天回测窗、test_size=0.2、XGBoost 超参数与早停规则均保持。开平仓、排名、同分排序、仓位、杠杆、止损、ROI 代码未改。

### 2.2 缓存隔离不能只改名字

生产配置唯一变更为 FreqAI identifier：

```text
mystrategy-4h-regression-72pair-corr-s1-v1
→ mystrategy-4h-regression-72pair-corr-s1-purged-v2
```

在 `super().__init__()` / DataDrawer 读旧模型和预测缓存前，核对实现/依赖、训练配置和历史输入 SHA。无标记旧缓存、损坏合同、孤立模型/预测、失败训练、旧 metadata 或输入变化均拒绝。不得把旧文件复制进新 identifier；不删除旧工件。生产 `fit_live_predictions_candles` 等未审查组合保持拒绝，而不是绕过检查。

### 2.3 特征、数据、指标与实验门禁

| 文件 | 根因与实际修复 |
| --- | --- |
| `validation/native_features.py`、`tools/audit_native_features.py` | 使用真实 DataKitchen 展开生产 schema，逐列来源与时间契约、未来扰动/截断、跨币与排名审计；未知 schema/动态 universe 不冒充通过 |
| `tools/audit_training_data.py` | 缺失/损坏源仍保留 pair/kind/timeframe/实际 datadir 与指纹；研究输入/配置读取前后核验；未知 Funding 继续隔离 |
| `validation/metrics.py` | 预测或真值含 NaN/Inf 时明确失败，修复原先静默过滤坏样本后报告“成功”的行为 |
| `validation/admission.py`、`cli.py` | 同 run_id、短时效收据、完整源码/依赖/原始数据/JUnit/工件校验；API 和 CLI 在创建正式输出前拒绝非法准入 |
| `experiments/runner.py` | 默认 development，正式与开发目录/状态隔离；比较前强制数据、标签、schema、折索引、成本及 scope 合同一致，工件缺失/变更拒绝排名 |
| `tools/accept_training_readiness.py` | 重建真实数据、研究与原生特征、真实训练工件，不接受手写六个 PASS；P0 FAIL 优先，不被缺证据降级；未实现的正式阶段保持 BLOCKED |
| `tools/audit_split_foundations.py` | 复用既有固定/扩展/滚动 splitter，真实开发前缀导出 purge/embargo/sample IDs；不训练、不解锁最终 holdout |
| `tools/run_native_training_probe.py` | 完整真实 FreqAI/XGBoost 开发训练与预测，隔离 userdir、输入/输出指纹和网络拒绝审计 |
| `tools/verify_native_training_acceptance.py` | 独立从原始行情重建特征/标签、原始切分、严格 purge、权重、pipeline 与预测；不信任训练流程声明的 PASS |

独立验收器最后补修也有真实失败测试：移走首个验证样本后重新哈希工件，以及将训练状态改成“未完成”，旧验收器仍可能 PASS。现在强制最终验证集合等于原始验证集合、训练集合等于原训练减严格 purge、时间/跨度/标签模式与生产配置一致、完整 schema 来自实际重新展开结果。允许所有文件重新哈希也不能掩盖这些不变量。

修改的已有测试只纠正 fixture 和明确缓存迁移：训练 fixture 在裁剪训练区间后重新生成尾部标签；配置冻结仍逐项比对全部实际参数。旧参考归档、回归比较器及 `rtol=atol=1e-12` **没有修改**。新增测试清单与故障场景见第 6 节。没有删除文件或失败测试。

## 3. 数据、完整特征与真实训练证据

### 3.1 数据可用性

| 检查 | 本轮结果 |
| --- | --- |
| 文件盘点 | 72 币 × futures/mark/funding = 216 份，逐币原始文件 SHA 与覆盖见 `source_sample_audit/source_audit.json`、`historical_coverage.json` |
| 源契约 | 144 futures/mark PASS；72 Funding BLOCKED。文件存在或时间戳连续不证明权威支付时间表 |
| 研究数据 | BTC/ETH 各 14880 行，26 列，各 14853 有效样本，共 **29706** |
| 研究排除 | 共 54 行：每币 24 warm-up + 3 尾部标签；逐行原因在 `sample_exclusions.parquet` |
| 数据集 SHA-256 | `cb240c0c6d64ab8b37465a902e02c21c12952a7f371a5c5af4f4fe37ef94dd3d` |
| 旧 BTC/ETH 两周回测 | 2025-01-01 至 01-15；实际 startup=2290 根，需要从 2023-12-16 08:00 预热 |
| 全币覆盖限制 | 上述区间 futures 完整 70/72；RENDER 缺 1338 根，SUN 缺 1501 根；逐段清单在 `data_governance_summary.json` |
| 研究文件与原始行情修改 | 0；没有下载、补造 K 线或把未知 Funding 填零 |

不设全局“缺失率必须为 0”。所有缺口必须被发现并按契约拒绝或隔离，不能产生错误有效样本。旧 coverage 工具报告的 56 个 raw-ready 结合了观测 funding cadence，**不是**权威 Funding 准入。原文件缺采集时间，仍记录 `captured_at=null`，不把审计时间冒充采集时间。

市场规则快照是采集时的真实规则，不是历史时点规则证明；不能据当前规则推断历史合约上市、杠杆或付款时间表。静态 72 币 universe 的工程因果性通过也不能证明无幸存者偏差。

### 3.2 原生完整 schema 审计

实际配置为 4h，周期 6/14/24，shift1，相关交易对 BTC/ETH。BTC/ETH 本身相关币去重后各 **92 列**，其余 70 币各 **136 列**；这是配置真实展开结果，不是硬编码断言。来源、公式、可用时间和测试结果逐列保存在 `native_features/native_features.json`。

使用全 72 币共同可用的 **600 根：2025-06-05 00:00 至 2025-09-12 20:00**，cutoffs=200/400/580。每币执行自身未来扰动、相关币未来扰动、未来截断：**648 项检查，0 差异**；`rtol=atol=0`，缺失 mask 同样必须一致。这不是全币最新区间或全部历史检查；ZIL 覆盖限制了共同窗口。

原生真实展开、shift/rolling、跨币及当前排名调用均动态验证；植入 future shift、全区间统计、相关币未来信息及未来全局排名，测试能识别。当前没有启用额外周期，辅助多周期测试确认只合并已收盘 informative candle。动态 PairList/未知 schema/不可用排名 snapshot 明确阻断。合法标签有意观察未来，不把标签变化误报为特征泄漏。

### 3.3 受控真实训练与边界前后对照

最终三币 probe 使用原生产超参数、真实本地数据与原生 resolver/DataKitchen/序列化/预测链路；没有用 mock、旧模型或旧预测缓存冒充训练。365 天训练范围：**2025-10-08 00:00 至 2026-10-08 00:00（右开）**；后续 48 根只用于开发预测接口验证。

| 交易对 | 特征 | 过滤前行数 | 尾部过滤 | 严格 purge | 保留训练 | 原始验证 | 预测 / ready |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC | 92 | 2190 | 3 | 3 | 1746 | 438 | 48 / 48 |
| ETH | 92 | 2190 | 3 | 3 | 1746 | 438 | 48 / 48 |
| BNB | 136 | 2190 | 3 | 3 | 1746 | 438 | 48 / 48 |

验证起点均为 **2026-07-26 16:00**。每币被 purge 的 open：07-26 00:00、04:00、08:00；标签完成分别为 07-26 16:00、20:00、07-27 00:00。第一条恰等于边界，也被剔除。所有保留训练边界违规、身份重叠、X/y/权重错位及 purge 行进入 fit 次数均为 **0**。

逐行 ID/原归属/最终归属/原因：`published_training_audit/{BTC,ETH,BNB}/purged_samples.csv` 与 `sample_assignments.parquet`；汇总 `training_boundary_summary.json`。pipeline fit IDs、均值/缩放统计、标签统计与 SHA 在对应 `audit.json`。

独立程序从原始 OHLCV 重新计算完整生产特征/标签；按配置重建原拆分、原权重和 purge；加载真实序列化 pipeline 并只用保留训练行重新拟合，逐值精确比对训练及验证转换结果；加载真实模型精确重放全部预测。不是读取 PASS 字符串或仅检查退出码。只加载本机可信 pickle 工件，不用于加载不可信第三方文件。

### 3.4 网络隔离及交易回归

三币 probe 在 `unshare -Urn` 下运行，同时 `strace -f -e trace=network` 与 Python deny-all 审计：HTTP、DNS/外部 socket 操作及外部 connect/send 均为 **0**。strace 存在 urllib3 导入时的 IPv6 `::1` socket/bind 能力探测，namespace 内 bind 返回 EADDRNOTAVAIL；没有 connect/send。这里不声称完全没有创建 socket。证据：`network_summary.json`、`native_training_network.strace` 与训练 `network.json`。

全量测试另外运行 BTC/ETH 两周的完整原生离线回测，每次新 userdir、`--cache none`，包含真实训练、预测、信号、撮合与导出。

| 对照 | 交易 / 订单 | 预测文件 | 结论 |
| --- | --- | --- | --- |
| 冻结旧模型重放 vs 旧可信联网参考 | 13/13，26/26 | 4 | PASS；仅证明原离线适配器兼容旧训练器 |
| 修复后 fresh A vs fresh B | 14/14，28/28 | 4 | PASS；交易、订单、signals/rejected/exited、指标、配置、schema 与逐窗预测严格比较 |
| 旧模型 vs 修复后模型 | 13→14，26→28 | 有真实差异 | **预期差异，比较器真实 FAIL**；保留差异，不把旧泄漏模型当成正确性金标准 |

分别见 `legacy_online_regression.json`、`corrected_backtest_regression.json`、`old_vs_corrected_behavior_change.json`。旧模型由 Git 冻结源码 SHA 隔离加载，仅用于历史 fixture；生产入口没有恢复旧训练器。当前修复模型尚无“重新联网训练参考”，新/新重训一致性不能冒充新联网/离线完全等价。

## 4. 独立准入门禁与剩余阻断

收据验证同 run_id、实际 JUnit testcase/nodeid、退出码、24 小时时效、UTC、完整代码/测试 SHA、依赖、Git 祖先、配置、原始输入及工件内容。24 小时是防环境漂移的工程政策，不是历史行情保质期。SHA 提供本地完整性，不是交易所签名或不可伪造证明。

`formal-run --readiness` 与正式 API 均在创建正式工件前验门禁，FAIL/BLOCKED/必要 PARTIAL、缺证据、过期、篡改或错轮证据均拒绝，CLI exit=2。开发 run 默认记录 `development`，诊断 holdout 记录 `development_diagnostic`，不记为正式成绩。软件不能阻止用户绕过所有代码自行训练；它能明确命令、目录、工件 scope 与验收边界。

| 阻断项 | 类型与影响 | 解除条件 / 允许的下一步 |
| --- | --- | --- |
| 72 币历史 Funding 支付时间表 | 外部数据证据；不能证明所有历史支付事件完整 | 补权威历史 schedule/来源及生效区间，逐币核验；不得臆定所有时期均 8h |
| 历史 point-in-time universe | 外部/研究设计证据；静态集合可能有幸存者偏差 | 补上市/退市及历史可选集合依据，或预先限定研究范围并声明偏差；不擅自改生产选币 |
| RENDER/SUN 旧窗口预热不足 | 数据范围 | 补可信原始文件或显式排除不能满足窗口的研究范围；本轮没有自动下载或缩短要求 |
| 三币开发训练覆盖 | 验收范围 | 按数据 Gate 选择更多完整币种验证；不把 3/72 宣称为 72/72 |
| 正式 P3–P5 与 P6 注册 | 尚未完成的工程/研究协议 | 依次实施正式分折/holdout 治理、样本外基准/成本/不确定性、正式实验 lineage；程序目前禁止手填 PASS 解锁 |
| 新训练器联网参考 | 兼容性证据未覆盖 | 如需要该结论，独立生成修复后同数据同配置联网参考，再严格对照；不修改旧基线 |
| 依赖升级或未审查配置 | 兼容范围 | 当前 2026.7/4.5.75 适配与实际源码 SHA 之外必须重新审查；不静默兼容 |

**当前允许继续工程修复与开发诊断，不允许跳到正式 OOS/选模型。** 不要求 Sharpe>1、准确率>60% 或模型盈利；业务标准必须在查看正式最终测试结果之前冻结。本轮没有新增正式收益或盈利结论。

## 5. 实际命令、结果和复现方式

最终全量测试统计及每条命令的退出码见 `execution_summary.json`、`test_run.json`、真实 `final_tests.xml`；各次失败日志完整保留，不能把不同运行次数相加成测试总数。最终完整测试为 **534 passed / 0 failed / 0 skipped，143.33 秒**；923 条依赖警告保留。Lint 与格式检查覆盖生产代码、模型、工具、测试和根入口；类型检查器/CI workflow 本仓库未配置，不算“类型检查通过”。

| 本轮执行 | 退出码 / 实际结果 | 证据 |
| --- | --- | --- |
| 起始完整 pytest | 0；398/0/0 | `quant-repair-baseline.log/xml` |
| 边界修复、指标、门禁与比较器红测 | 1；真实复现后修复 | `native-isolation-red-20261018.log`、`quant-repair-metrics-red.*`、`admission-red-20261018.log`、`comparability-red-20261018.log` |
| 独立验收补修前红测 | 1；3 failed | `quant-repair-independent-binding-red.log/xml`；包括移动验证起点与未完成状态误通过；timeframe 场景原先因不同原因失败 |
| FAIL 优先级红测 | 1；2 failed / 5 passed | `native-feature-status-red-20261018.log` |
| 补修后独立验收 + Gate 定向 | 0；35/0/0 | `quant-repair-independent-binding-final.log/xml` |
| 最终完整 pytest | 0；534/0/0 | `quant-repair-final-suite-v4.log`、`final_tests.xml`、`test_run.json` |
| 三币真实训练（OS namespace + strace） | 0；3 次真实训练、144 行预测 | `quant-repair-native-final-v4.log`、`native_training/training_run.json` |
| 独立训练工件重算 | 0；三币 PASS，Funding 仍 BLOCKED | `native_training_independent.json` |
| 独立六阶段总 Gate | **2；BLOCKED** | `final_gate/readiness.json`，不是失败测试的退出码 |
| 正式 CLI 使用该 Gate | **2；拒绝，正式输出未创建** | `formal_admission_check.json` |
| Ruff / format | 0；111 文件格式通过 | `quant-repair-lint-final-v4.log`、`quant-repair-format-final-v4.log` |

整仓 `ruff check .` 额外扫描到了历史证据脚本 `docs/acceptance/phase4_extension_continue.py` 的旧导入顺序/格式问题。未改写历史证据来获得绿色；它不在生产/工具/测试检查范围。诊断失败日志保留。旧模型 `MomentumRidgeRegressor.py` 的未使用导入与格式已清理，没有改变 Ridge 参数、训练或预测行为。

### 从仓库根目录重现

前置条件：相同依赖、真实本地 `data/`、真实元数据快照，以及允许 `unshare -Urn`、可用 `strace`。Git 不包含大体积原始行情/模型；空 clone 没有这些前置资料时必须 BLOCKED，不能把 skip 算通过。`PYTHON` 按实际环境设置，下列为本机实际解释器的相对路径。

```bash
export PYTHONPATH=src:.
PYTHON=../freqtrade/.venv/bin/python
RUN=docs/acceptance/training_repair_$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$RUN"

# 只读源数据/研究样本审计，不自动下载。
"$PYTHON" tools/audit_training_data.py --output "$RUN/source_sample_audit" \
  --config config.json --research-config configs/base.yaml configs/environment/local.yaml
"$PYTHON" tools/audit_native_features.py -c config.json --bars 600 \
  --output "$RUN/native_features"
"$PYTHON" tools/audit_split_foundations.py \
  -c configs/base.yaml -c configs/environment/local.yaml \
  --output "$RUN/development_split_foundations.json"

# 完整真实开发训练；必须用新目录，不能复用旧缓存。
unshare -Urn strace -f -e trace=network -o "$RUN/native_training_network.strace" \
  env PYTHONPATH=src:. "$PYTHON" tools/run_native_training_probe.py \
  --output "$RUN/native_training"
"$PYTHON" tools/verify_native_training_acceptance.py \
  --run "$RUN/native_training" --output "$RUN/native_training_independent.json"
```

全量测试收据必须捕获**实际 subprocess 返回值**与实际 JUnit，而不是手写 exit=0。保持源码、依赖、原始文件不变，接着执行：

```bash
# RUN 传入脚本，收据在测试之前绑定代码，之后记录真实退出码。
"$PYTHON" - "$RUN" <<'PY'
import json, os, subprocess, sys
from pathlib import Path
from quant_strategy.infrastructure.experiment_store import file_hash
from quant_strategy.validation.admission import new_receipt_context
root = Path(sys.argv[1])
context = new_receipt_context(root.name)
command = [sys.executable, "-m", "pytest", "-q",
           "--junitxml=" + str(root / "final_tests.xml")]
with (root / "pytest.log").open("w") as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                            env={**os.environ, "PYTHONPATH": "src:."})
receipt = {**context, "command": command, "exit_code": result.returncode,
           "junit": "final_tests.xml", "junit_sha256": file_hash(root / "final_tests.xml")}
(root / "test_run.json").write_text(json.dumps(receipt, indent=2))
raise SystemExit(result.returncode)
PY

"$PYTHON" tools/accept_training_readiness.py --evidence "$RUN" \
  --test-run "$RUN/test_run.json" --output "$RUN/final_gate"
# 当前预期返回 2 / BLOCKED，不允许把它改写成 PASS。

"$PYTHON" -m quant_strategy.cli formal-run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  --readiness "$RUN/final_gate/readiness.json" \
  --output "$RUN/formal" --experiment-id denied
# 当前预期返回 2，正式目录不应创建。

../freqtrade/.venv/bin/ruff check src tests tools freqaimodels \
  MyStrategy.py _quant_strategy_bootstrap.py feature.py model.py test_my_strategy.py
../freqtrade/.venv/bin/ruff format --check src tests tools freqaimodels \
  MyStrategy.py _quant_strategy_bootstrap.py feature.py model.py test_my_strategy.py
```

`pytest -q tests/integration/test_offline_freqtrade.py` 会执行文中的真实新/新断网回测与旧在线参考重放；新 userdir、原配置合并次序、`--cache none`、导出及 namespace 参数由测试保存。日常开发训练可直接使用上面的 probe；正式研究只能走 `formal-run`，当前拒绝是正确行为。

公开日志只脱敏本机用户名、工作目录与解释器路径，不改测试数值、异常或判定；原始与公开版本的 SHA 对照见 `log_publication.json`。机器可读的真实测试映射见 `requirements_test_traceability.json`，交付时的源码、原始输入和 Gate 工件复核见 `delivery_integrity.json`。

运行期完整训练工件在 `native_training/userdir/models/`，本地保留的回测归档在 `retained_backtests/models/`。二者遵循现有 `.gitignore`，**不会提交模型、缓存、可能含完整运行配置的归档或大体积原始行情**。公开的审计样本、SHA 和比较报告已保存；换机器复核须提供相同真实输入并重跑，不能凭公开 JSON 声称已重放模型。尝试期间源码发生变化的 run、旧 520 测试、绑定补修前工件均保留在 attempt/pre_* 附件中，不能作为最后源码的最终通过凭证。

## 6. 需求—测试追踪矩阵

下表中的路径相对于仓库；参数化测试包括各故障 case。最终 JUnit 含真实 nodeid，可核验实际执行。测试故障只修改内存、临时副本或隔离输出；spy 观察拟合边界不替代真实训练。

| ID / 硬性要求 | 对应测试文件 :: 测试名 | 故意制造的失败场景 / 实际判定 |
| --- | --- | --- |
| DATA-001 时间、价格与来源合法 | `tests/unit/test_training_data_contracts.py`、`test_sample_governance.py` | 乱序/重复/错网格/NaN/Inf/负数量/缺口/零样本检测，既有测试重跑 |
| DATA-002 原始只读、输入指纹 | `tests/integration/test_dataset_governance.py`；`tests/unit/test_source_inventory_failure_paths.py::test_corrupt_source_keeps_actual_path_hash_and_is_not_modified` | 读取间变更、坏 Feather、改 schema；拒绝且源未写入 |
| DATA-003 缺 Funding 不得补零 | `tests/unit/test_training_data_contracts.py`、`test_historical_coverage.py` 中 funding schedule/缺付款事件用例 | 观测频率不能证明权威 schedule；真实 72 币仍 BLOCKED |
| DATA-004 缺文件保留真实身份 | `tests/unit/test_source_inventory_failure_paths.py::test_missing_source_keeps_kind_timeframe_and_quarantine`、`test_external_datadir_source_identity_is_actual_input_not_default_data` | 缺文件、外部 datadir 不得错记默认路径 |
| BOUND-001 严格 `<` 边界 | `tests/unit/test_native_isolation.py::test_equality_greater_and_less_than_boundary` | `==` / `>` 剔除；`<` 合法保留 |
| BOUND-002 无验证仍可训练 | 同文件 `test_no_validation_still_tracks_training`；`tests/integration/test_native_purged_training.py::test_actual_real_btc_training_and_prediction` | test_size=0 与 0.2 均真实训练；不支持 horizon0 时明确拒绝 |
| ALIGN-001 X/y/权重身份 | `tests/unit/test_native_isolation.py::test_weight_and_metadata_alignment`、`test_misaligned_labels_or_weights_fail`、`test_post_purge_faults_are_not_repaired_into_a_pass` | 倒序 y/weights、回插 purge 行、跨界行，必须失败 |
| ALIGN-002 错时空输入 | 同文件 `test_bad_time_or_identity_fails` | missing_date/duplicate_date/gap/duplicate_index/empty，明确失败 |
| FIT-001 purge 在任何 fit 前 | `tests/integration/test_native_purged_training.py::test_actual_preprocessing_and_early_stopping_exclude_all_purged_rows`、`test_native_split_corruption_fails_before_any_fit` | 真 pipeline/XGB；注入错位时不得进入任何 fit |
| FIT-002 验证不学习训练统计 | 同文件 `test_validation_extremes_never_fit_training_scaler` | 验证值改成 1e9，训练 scaler 不受影响 |
| FIT-003 连续窗口身份 | 同文件 `test_actual_reused_datakitchen_keeps_distinct_window_fit_identities` | 复用 DK 不继承上窗 fit IDs |
| CACHE-001 拒绝旧/不兼容缓存 | `tests/unit/test_native_isolation.py::test_unmarked_old_cache_and_changed_contract_fail`、`test_cache_cannot_reuse_predictions_after_source_file_change`、`test_valid_cache_root_does_not_bless_invalid_artifacts` | 无 marker、损坏/重复键、改数据、旧 metadata、孤立预测均拒绝 |
| CACHE-002 不覆盖证据 | `tests/integration/test_native_purged_training.py::test_repeated_input_cannot_overwrite_audit_or_refit`、`test_failed_real_model_fit_keeps_failed_artifact` | 重复训练拒绝；注入 fit 异常保留失败工件 |
| LEAK-001 完整真实 schema | `tests/leakage/test_native_feature_causality.py::test_actual_native_expansion_schema_and_all_feature_contracts`、`test_actual_btc_eth_bnb_files_full_native_features_are_causal` | 真实展开；未知/缺列不能通过；另执行全 72 币 648 检查 |
| LEAK-002 扰动/截断检出泄漏 | 同文件 `test_actual_pipeline_known_schema_future_faults_are_detected` | future_shift/whole_sample/correlated_future 注入，检测器拒绝 |
| LEAK-003 标签与特征区分 | 同文件 `test_features_unchanged_but_future_label_changes_are_expected` | 未来变化允许改变标签，不能改变当时特征 |
| LEAK-004 排名与动态集合 | 同文件 `test_actual_snapshot_and_native_strategy_ranking_ignore_future_predictions`、`test_future_global_dynamic_ranking_is_detected`、`test_dynamic_universe_is_explicitly_blocked` | 真排名前缀不变；未来全局排名被检出；不支持动态集合 BLOCKED |
| LEAK-005 informative/预热 | 同文件 `test_native_informative_timeframe_merges_only_closed_candles`、`test_unobserved_warmup_is_blocked_not_assumed_causal` | 未收盘数据、无有效可比较前缀不得伪通过 |
| LEAK-006 审计输入不变 | 同文件 `test_audit_input_fingerprints_reject_in_run_replacement`、`test_real_native_audit_cli_binds_run_identity_and_immutable_inputs` | 运行时换输入必须拒绝 |
| SPLIT-001 三协议与 purge/embargo | `tests/integration/test_real_split_foundations.py::test_three_real_data_split_protocols_have_disjoint_traceable_sample_ids`、`test_insufficient_real_history_cannot_shrink_requested_development_prefix` | 真开发前缀分折；要求过长历史不得自动缩窗；不冒称正式多折训练 |
| METRIC-001 不过滤坏样本 | `tests/unit/test_metric_input_integrity.py::test_nonfinite_metric_input_is_an_error_not_a_filtered_success`、`test_prediction_metrics_match_hand_calculation_without_sample_filtering` | NaN/Inf 拒绝；MAE=1、RMSE=√(5/3)、n=3 手算通过 |
| EXP-001 正式/开发隔离 | `tests/unit/test_admission_integrity.py::test_direct_formal_api_cannot_bypass_admission`、`test_default_research_artifacts_are_explicitly_development` | 绕 CLI 仍拒绝正式；诊断 holdout 不记 formal |
| EXP-002 不可比拒绝排名 | `tests/unit/test_experiment_comparability.py::test_changed_comparison_contract_is_rejected`、`test_different_labels_refuse_direct_comparison`、`test_different_fold_indexes_refuse_direct_comparison` | 改数据/标签/folds/cost/scope 必须拒绝；仅模型不同的可比正例通过 |
| EXP-003 工件与合同双验 | 同文件 `test_manifest_cannot_remove_required_artifact_from_inventory`、`test_modified_fold_with_updated_artifact_hash_still_fails_contract` | 移除 manifest 项或改折后更新单 SHA 仍拒绝 |
| GATE-001 六 PASS 不解锁 | `tests/unit/test_admission_integrity.py::test_six_pass_strings_with_counts_and_one_hash_cannot_grant_admission`；`tests/unit/test_training_readiness_gate.py::test_engineering_gate_does_not_grant_profitability_or_live_admission` | 人工 PASS/未实现后续 validator registry 不能正式准入 |
| GATE-002 同轮/时效/源码/环境 | `tests/unit/test_admission_integrity.py::test_receipt_context_rejects_mixed_stale_or_changed_context`、`test_document_only_descendant_preserves_receipt_code_identity` | 错轮、未来/过期、非 UTC、改源码/依赖/未知 commit 均拒绝 |
| GATE-003 真 JUnit/失败优先 | 同文件 `test_junit_uses_actual_results_and_exact_identity`；`tests/unit/test_training_readiness_gate.py::test_recomputed_feature_failure_dominates_missing_sources_and_partial_scope` | hidden failure、错 class、漏 case、skip、FAIL+缺资料均不放行 |
| GATE-004 CLI 稳定 exit2 | `tests/unit/test_admission_integrity.py::test_formal_cli_malformed_readiness_has_stable_exit_two`；`tests/integration/test_formal_training_admission.py` | FAIL/BLOCKED/PARTIAL/损坏证据，训练前拒绝且不创建输出 |
| VERIFY-001 独立实物重算 | `tests/integration/test_independent_native_acceptance.py::test_real_native_training_has_independently_recomputed_safe_boundaries` | fixture 真训练，raw 重建、pipeline 重拟合、预测重放通过 |
| VERIFY-002 重新哈希仍拒错 | 同文件 `test_independent_verifier_rejects_self_consistently_rehashed_faults` | boundary/xy/weight/fit_ids/schema/prediction/timestamp 七类篡改必须因具体不变量失败 |
| VERIFY-003 不准移动验证起点 | 同文件 `test_independent_verifier_binds_audit_to_original_split_and_configuration` | 移验证起点、改 timeframe/horizon、未完成训练、改记录边界、少安全训练行、双方共同缩 schema，全部拒绝 |
| REG-001 冻结语义与必要迁移 | `tests/regression/test_frozen_baseline.py`、`tests/integration/test_strategy_adapter.py::test_installed_freqai_train_predict_lifecycle` | 逐项参数/特征/标签/交易规则保护，identifier 唯一明确迁移 |
| REG-002 真实断网完整回测 | `tests/integration/test_offline_freqtrade.py::test_corrected_native_backtest_is_reproducible_in_fresh_disconnected_userdirs`、`test_native_backtest_in_disconnected_namespace_matches_online_reference` | 新/新真实重训严格比较与旧/旧冻结参考分别通过，不混用结论 |

## 7. Git 交付与下一步

本轮变更包括上文生产训练适配层、完整原生特征审计、独立验收工具、数据与准入补修及对应测试；旧模型另仅导入/格式清理。没有删除原始行情、历史证据、旧参考或测试，也没有修改密钥、TLS、全局网络配置、交易规则或模型超参数。

代码修复已创建提交 **`4355815`**（28 个文件，3874 行新增、130 行删除）；本汇总、README 与证据另作独立文档提交。提交前核对 `git diff`、未跟踪/暂存范围、密钥/个人路径、大文件和输入指纹：216 个原始文件、全部已测源码未变化；未发现非空凭据，未纳入模型、缓存或原始行情。

源码/测试/工具/配置/阅读文档的 diff check 返回 0；全部证据附件一起检查返回 2，仅因失败测试日志/XML 保留的 pytest 行尾空格，详见 `static_and_diff_checks.json`。没有为“全绿”改写失败证据。最终文档提交号与普通 push 状态由交付消息及 Git 历史确认；测试执行基线始终是本文件记录的 `4ba4fe8` 修复工作区，不把提交日期或 HEAD 倒写进旧日志。代码提交后再次校验收据祖先关系与源码指纹通过，正式 CLI 仍以 exit=2 拒绝，未创建正式输出。

后续顺序：先补 Funding 和历史 universe 的可信证据、确定完整可用研究范围；在此基础上实现并验收正式分折/holdout 准入；再开展按冻结标准的样本外基准与交易成本评估；最后验收正式实验 lineage。当前不建议直接开始正式 OOS、挑选候选赢家或实盘下单。

实现依据为当前安装的 Freqtrade `BaseRegressionModel.py`、`data_kitchen.py`、`data_drawer.py`，以及 Datasieve `pipeline.py` 的实际源码；实现合同记录相应 SHA。验证原则参考 sklearn 的 [数据泄漏与 train-only preprocessing](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)、pytest 的 [JUnit XML](https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files) 及 [FreqAI 配置说明](https://www.freqtrade.io/en/stable/freqai-configuration/)。外部文档不代替本轮真实执行证据。
