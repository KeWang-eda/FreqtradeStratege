# 离线回测体系：Phase 0–6 最终验收

执行日期：2026-10-17。**最终状态：PASS，范围限定为下表实际执行的研究流程与 BTC/ETH、BTC/ETH/BNB 原生回测。** 不是全 72 币、全历史或真实账户交易验收。本轮从 `main@5ce05d6684345c56902b4af85a32d5889b92ac7b` 的干净工作区开始，已确认起始 GitHub HEAD 相同；未重置工作区、下载行情或升级依赖。

## 阶段状态与准入

| 阶段 | 实际验收状态 | 实际执行及准入结论 | 详细验收表与证据 |
| --- | --- | --- | --- |
| Phase 0 基线 | PASS | 独立复现 115 passed / 0 failed / 0 skipped；冻结 216 份数据、58 个源码/配置文件和原快照，进入 Phase 1 | [基线](phase0_baseline.md)、[清单](phase0_inventory.json) |
| Phase 1 架构 | PASS | 缺/错快照、模式、版本、市场范围明确失败；原生校验和客户端释放保留；独立复核发现的 JSON bool/int 缺陷已修复，进入 Phase 2 | [审查](phase1_architecture_review.md)、[独立复核](adapter_independent_review.md) |
| Phase 2 测试/比较器 | PASS | 交易、订单、预测、指标、metadata、完整配置差异均有负测；最终全量包括所有补修，进入 Phase 3 | [矩阵](phase2_test_matrix.md)、[最终 JUnit](phase6_pytest.xml) |
| Phase 3 数据覆盖 | PASS | 全 72 币逐项有结论；56 币指定窗口原始数据严格就绪；BTC/ETH 最低范围通过准入，无补造；进入最低 Phase 4 | [覆盖](phase3_data_coverage.md)、[机器报告](phase3_data_coverage.json)、[逐文件表](phase3_pair_files.md) |
| Phase 4 原生离线 | PASS | 最低 BTC/ETH 两周和扩展 BTC/ETH/BNB 三周，空 userdir 重新训练，OS 网络隔离真实运行，与各自联网参考严格一致，进入 Phase 5 | [最低报告](phase4_offline_backtest.md)、[扩展报告](phase4_extension.md) |
| Phase 5 模式边界 | PASS | 本地 validate/dataset-build/run/compare 断网；普通原生回测仍请求元数据；LIVE/DRY_RUN 原生客户端和凭证处理边界保留，进入 Phase 6 | [模式矩阵](phase5_mode_isolation.md)、[研究工件](phase5_artifacts.tar.gz) |
| Phase 6 工程交付 | PASS | 冻结后 298 / 0 / 0，Lint/82 文件格式检查通过，输入/策略指纹、证据与文档核验通过 | 本报告、[完整测试](phase6_pytest.log)、[最终证据校验](phase6_evidence_validation.json) |

各阶段失败尝试原样保留并解释，不计为最终通过测试，也没有删除失败用例。系统级隔离实际执行，没有用 skip、HTTP mock 或缓存模型代替端到端验收。

## 根因、调用链与最小扩展点

普通回测的网络请求来自 **市场元数据初始化**：`freqtrade backtesting → Backtesting.__init__ → ExchangeResolver/Binance → Exchange.__init__ → reload_markets → _api_reload_markets → CCXT load_markets/fetch_markets → GET fapi/v1/exchangeInfo`。它用于市场身份、精度、限额、费用及合约校验，不是重新下载 K 线。`configs/backtest-local.json` 将 `fetchMarkets.types` 限为 linear 后仍有这一必要初始化请求。

指定版本没有可配置的本地市场规则加载器，也不能通过普通配置注册本项目 Exchange 子类。保留 `Backtesting(config, exchange=...)` 的注入入口，仅在独立 `SnapshotBinance` 中扩展 `_init_ccxt` 和 `_api_reload_markets`：真实 CCXT `set_markets()` 恢复经过校验的数据，随后仍执行原生 `validate=True` 和杠杆初始化。内部钩子固定依赖 Freqtrade 2026.7 / CCXT 4.5.75，未修改虚拟环境源码或全局类。

专用入口链路为 `offline_backtest.main → 原生 Arguments/setup_optimize_configuration → BACKTEST 预检 → load_snapshot → SnapshotBinance → Backtesting.start`。原生历史数据加载、`populate_indicators → self.freqai.start → 本地数据厨房 → XGBoostRegressorES.train/predict`、信号和交易模拟保持原路径。同步/异步子类的 HTTP 传输拒绝请求；重复/强制刷新只恢复已验证快照，任何快照错误都不回退到网络。

| 请求/任务 | 本轮行为 | 是否可避免 |
| --- | --- | --- |
| 独立研究训练、CV、预测评估、比较 | 本地文件，不导入 Freqtrade/CCXT | 已完全避免 |
| 历史 futures、mark、funding 加载 | 原生读取 `data/`，216 文件 SHA 未变 | 无重复下载请求 |
| 普通原生回测市场初始化 | 拒绝网络条件下真实发起一次 fapi 请求并 exit 2 | 普通入口保留原生必要行为 |
| 显式离线回测市场初始化 | 验证真实快照，执行原生规则校验，无 HTTP/DNS/外部连接 | 已完全避免 |
| 显式 capture / 扩展联网参考 | 真实公开元数据请求，记录审计；不下载 K 线 | 属于明确联网任务 |
| LIVE / DRY_RUN | 原生交易所和凭证处理路径；未注入离线类 | 保留原能力，未实际账户/订单验收 |

## 实际回测与网络证据

所有区间按 UTC，起点包含、终点不包含；配置顺序均为 `config.json → configs/backtest-local.json → configs/environment/freqtrade-mihomo.json`，固定本轮真实策略/数据。离线加载同一代理 overlay 只为了严格配置对照，不会连接代理。全新 userdir 与 `--cache none` 同时使用，未把旧 FreqAI 模型作为重训结果。

| 项目 | BTC/ETH 最低范围 | BTC/ETH/BNB 扩展范围 |
| --- | ---: | ---: |
| 时间范围 | 20250101–20250115 | 20250101–20250122 |
| 联网参考来源 | 既有真实联网归档，本轮未冒充重跑 | 本轮真实联网新训 |
| 离线完整训练次数 | 4 | 9 |
| 离线 metadata / 预测文件数 | 4 / 4 | 9 / 9 |
| 各模型原生特征数 | BTC/ETH 各 92 | BTC/ETH 各 92、BNB 136 |
| 交易 / 订单，两侧相同 | 13 / 26 | 29 / 58 |
| 总盈亏 USDT，两侧相同 | -7.72891548 | -25.447139770000007 |
| 最终余额 USDT，两侧相同 | 992.27108452 | 974.55286023 |
| 最大账户回撤，两侧相同 | 0.019077787162898503 | 0.03503975726890054 |
| 离线 HTTP / Python DNS/socket 事件 | 0 / 0 | 0 / 0 |
| 离线系统调用 connect/send | 0 | 0 |
| 严格回归 differences | [] | [] |

BNB 特征数来自真实原生 metadata，由原有相关币展开产生；没有把 92 列作为所有币的硬编码规则。模型/预测数量、训练日志、schema 和完整工件都核查，退出码为 0 仅是其中一项条件。

系统隔离为 `unshare --user --map-root-user --net`，同时执行 `strace -f -e trace=network` 和 Python deny-all 审计。离线唯一 IP socket 活动是 aiohttp 导入时失败的 `bind(::1)` 能力探测，没有连接/发送。研究 tarfile provenance 中失败的 `/var/run/nscd/socket → ENOENT` 已独立复现为本地用户名查询，不是 DNS/IP；成功 nscd、其他 Unix 或 IP 活动仍会使审计失败。

最低证据：[网络 JSON](phase4_backtest_network.json)、[系统调用](phase4_backtest_network.strace)、[回归](phase4_regression.json)、[离线归档](phase4_artifacts.tar.gz)、[参考脱敏副本](phase4_reference_artifacts.tar.gz)、[发布后严格重放](phase4_published_replay.json)。扩展证据：[双侧 summary](phase4_extension_summary.json)、[离线网络 JSON](phase4_extension_offline_network.json)、[系统调用](phase4_extension_offline_network.strace)、[回归](phase4_extension_regression.json)、[双侧归档](phase4_extension_artifacts.tar.gz)、[真实三币快照](phase4_extension_snapshot.json)。

最低范围另于 **13:21 UTC** 使用最终覆盖文件独立重新验收：全新 userdir 再训练 4 次，13 交易/26 订单/4 预测、全部特征 92、零网络和严格回归再次通过。[最终准入 summary](phase4_revalidation/phase4_summary.json)记录的 gate SHA 与公开最终报告一致；[新回归](phase4_revalidation/phase4_regression.json)、[网络 JSON](phase4_revalidation/phase4_backtest_network.json)、[strace](phase4_revalidation/phase4_backtest_network.strace)及[发布重放](phase4_revalidation/phase4_published_replay.json)为最终权威最低证据。原因是 C 在首次最低回测之后重新生成了覆盖报告，旧输入未单独留存，最终 manifest 首次检查准确发现哈希不一致；[失败记录](phase6_evidence_first_attempt.json)与旧工件全部保留，不编造脱敏映射或改旧哈希。

最终最低验收还单独保留 [gate 原字节副本](phase4_revalidation/phase4_coverage_input.json)，[provenance](phase4_revalidation/coverage_provenance.json)核实原文件、副本及实际运行 summary 的三方 SHA 完全一致。日后重生成覆盖报告须使用新输出目录，不覆盖历史验收的输入副本。

主线程还从公开扩展归档解出两侧工件，独立重新执行比较器，仍为 29/58、9 份预测、`differences=[]`，见[扩展发布后重放](phase4_extension_published_replay.json)。这一步校验发布副本，未重新训练或冒充额外原生 E2E。

交易/嵌套订单、全部 metadata、有效配置精确对照；预测、信号和结果指标保持 `rtol=atol=1e-12`。仅排除进程实际运行起止字段 `backtest_run_start_ts/end_ts`。metadata 路径先验证相对模型目录，仅规范独立 userdir 根；config_files 仅规范 checkout 根，保留实际顺序。不排除 proxy、timeout、训练参数或未知字段；JSON 非有限值拒绝，帧 NaN 必须两侧同位置，不填零。

## Phase 6 验收表与测试统计

实际 Python 3.13.13，Freqtrade 2026.7，CCXT 4.5.75，pandas 3.0.5，NumPy 2.5.2，XGBoost 3.4.1，pytest 9.1.1，Ruff 0.15.22；完整冻结见 [Phase 0](phase0_inventory.json)。

| 验收项 | 执行命令或方式 | 预期 | 实际 | 证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 全量测试 | `PYTHONPATH=src:. "$FREQTRADE_PYTHON" -m pytest -q --junitxml=...`，独立 basetemp | 无失败/意外 skip | **298 passed / 0 failed / 0 skipped，50.49s** | [JUnit](phase6_pytest.xml)、[日志](phase6_pytest.log) | PASS |
| Lint | `ruff check src tests tools` 及根目录兼容入口 | 无违规 | All checks passed | [Lint](phase6_ruff.log) | PASS |
| 格式 | 同文件范围 `ruff format --check` | 全部已格式化 | 82 files already formatted | [格式](phase6_format.log) | PASS |
| 策略/配置/历史证据 | `git diff --exit-code 5ce05d6 -- ...` + 冻结 SHA | 无未经批准变化 | 原交易策略/特征/标签/模型/configs、历史证据无变化 | [diff](phase6_protected_diff.log)、[指纹](phase6_integrity.json) | PASS |
| 数据未修改 | 对比 216 个输入 SHA | 不覆盖/更新行情 | 216 检查、0 变化 | [指纹](phase6_integrity.json) | PASS |
| 命令入口 | 专用模块 `backtesting --help` | 模式、版本、年龄、原生参数明确 | 帮助记录已生成 | [help](phase6_cli_help.txt) | PASS |
| 证据完整/脱敏 | 文件与归档成员 SHA、文本/ZIP 扫描 | 无意外缺件、无本机私有根 | 核验通过 | [最终校验](phase6_evidence_validation.json) | PASS |
| diff 空白 | `git diff --check`，原始 log/XML 单独保留 | 源码/配置/文档干净 | 无错误 | [检查](phase6_diff_check.log) | PASS |

类型检查 **N/A**：项目未配置 mypy/pyright，不记作类型检查通过。867 条依赖弃用 warning 保留，主要是 joblib 与 NumPy 2.5 的旧 shape 操作；没有屏蔽 warning 或升级依赖。

Phase 0 的 115 项是起始独立复验；Phase 2 的 217 项、补修 104 项和最终收集前的 291 项均为各时点结果，不能相加冒充最终测试数。291 项运行在 collection 后补入 7 项扩展审计负测，所以又从冻结代码完整执行 298 项，JUnit 明确包含扩展 25 项。[中间 JUnit](phase6_intermediate_pytest.xml)保留，不作为最终验收。

研究 E2E：真实 BTC/ETH 共 29706 样本、26 个研究特征；Ridge/XGBoost 各 3 folds、各 18934 预测行，validate/dataset-build/run/compare 均在系统隔离中通过，HTTP/DNS/外部连接为 0。研究与原生 schema 不同，未据研究指标替换生产模型。[研究 summary](phase5_summary.json)可追溯全部命令和输出。普通回测的 1 个被拒 HTTP 为模式隔离测试的预期，不计作离线运行的网络事件。

## 代码差异与关键决策

| 新增/修改范围 | 目的 |
| --- | --- |
| `market_snapshot.py` | 严格 schema、JSON 类型、真实 raw/normalized 复核、关键 filter/杠杆/版本/时效验证，原子且拒绝覆盖发布 |
| `offline_backtest.py` | 模式/配置前置拒绝、原生依赖注入、同步/异步传输守卫、异常资源释放、类型标注及 CLI help |
| `experiment_store.py` | 仅收紧 provenance 的只读 Git 调用，禁外部 diff/textconv/fsmonitor；不改研究计算 |
| `audit_local_network.py` | 扩大 HTTP/DNS/socket/进程审计，拒绝事件即使被任务捕获也使整次审计失败 |
| `verify_freqtrade_regression.py` | 全 metadata/配置、嵌套交易/订单、缺件/额外件与非有限值校验，保持原容差 |
| 新增 `audit_historical_coverage.py` | 逐币文件质量、预热、付款时刻表与标签边界只读审计，输出机器报告 |
| 新增 `run_offline_acceptance.py`、`run_offline_extension.py` | 编排真实系统隔离、空缓存训练、联网对照、证据发布；不注入普通交易 |
| 新增/补齐单元、集成、回归测试 | 文件中断、失败关闭、模式隔离、清理与比较器负向测试 |
| README、operations、分阶段文档/工件 | 可复制入口、快照运维、阶段状态、失败记录及证据索引 |

没有删除文件。完整文件清单见 [变更清单](phase6_changes.txt)。58 个冻结源码/配置文件中只有快照、离线适配器和上述 Git provenance 三个允许文件发生变化，其余策略、标签、特征、模型、排名、仓位、杠杆、风险参数及配置均保持原字节；另以真实原生结果回归验证。未修改凭证、系统网络、全局代理、TLS 校验或虚拟环境包源码。

快照 SHA-256 证明完整性，不是 Binance 签名；来源为真实公开响应及该版原生杠杆 JSON。未知 envelope 字段明确拒绝，原始交易所扩展字段保留。生产默认时效 30 天；冻结验收明确使用长时效以复现固定输入，不能当作生产默认。升级 Freqtrade/CCXT 必须重审两个内部钩子、原生校验/精度/档位/清理，并重新执行完整负测及系统隔离回归，不能只放宽版本常量。

## 数据范围、失败尝试与未覆盖风险

72 个交易对的 216 个文件均存在，但仅 56 个币在最低区间具备严格原始数据条件，最初 BTC/ETH 快照只覆盖两币；扩展真实快照新增 BNB，不代表已有所有币的可信规则。

16 币资金费率付款时刻表需历史确认：AXS、BSV、CAKE、ENJ、IOST、KAVA、ONT、RENDER、RLC、SKL、SOL、SUN、TRB、XTZ、ZIL、ZRX。时刻变化不直接等同漏下载，不能填入零 funding。按原生计算的 2290 根 startup/训练预热，RENDER 缺 1338 根、SUN 缺 1501 根早期 4h 行情；8 币在 2025 年中停止覆盖，不能推广到 2026 年。逐币不可用日期见 [覆盖表](phase3_pair_files.md)。未自动补齐或下载任何行情。

当前采集的市场规则不证明 2025 年精度、限额或杠杆档位的历史真实性；本轮证明相同规则输入下在线/离线交易语义一致。全 72 币交易、更长区间、其他交易所/模式、其他机器/依赖版本、真实账户认证和订单、长期 dry-run **未验证**，不属于本次 PASS 的外推结论。Python 审计不是对恶意 C 扩展的通用沙箱，系统级隔离及 strace 才提供进程级验收证据。

开发/验收中真实出现并保留的失败：只读 Git provenance 被初版进程守卫误拒；标签负测 fixture 不一致；pandas us/ns 单位审计错误；研究 nscd 本地失败探测误分类；扩展首次真实采集超时；扩展第二次在线 TLS/AF_UNIX FD 分类过严；发布回放双方根路径脱敏不对称。各阶段文档解释修复和重验，没有删用例、伪造行情、放宽数值容差或省略配置来掩盖失败。

最终 manifest 首次失败还发现覆盖报告在首次 Phase 4 后重生成、旧 gate 未留存的证据缺口；已完整重新执行最低范围端到端验收解决。它不是训练/交易失败，也不应被隐藏为通过或解释成路径脱敏。后续覆盖审计输出应使用独立文件名；每次验收保留对应 JSON 与 SHA，避免同一路径含义随重新生成变化。

文档链接检查初版把 Python 代码块中的 `helpers["make_run"](root)` 误认成 Markdown 链接，失败记录保留为 [link scan attempt](phase6_linkscan_failed_attempt.json)；按 Markdown 语法排除代码块与行内代码后再检查，没有虚构 `root` 目标文件或改写复现实例。

扩展最终离线运行重新建立空 userdir。在线参考来自第二次尝试实际成功的新训练，继续时仅修正独立审计器的 FD 分类并核验该原始日志/输入；没有把在线模型复制给离线。原始结果先严格比较，再仅脱敏本机路径，完整 raw/published SHA 随 summary 发布。早期 [脱敏清单](phase6_evidence_redaction.json)记录的是当时副本 SHA；后续补文档的最终 SHA 以 [最终证据清单](phase6_evidence_validation.json)为准。旧 `docs/baseline/acceptance/` 保留原样。

## 从干净目录复现与下一步

在仓库根目录激活已经安装指定版本的环境，再设置解释器；数据不随 Git 分发，需要原有真实 `data/`。命令均使用新输出目录，不覆盖既有模型或证据。

```bash
export FREQTRADE_PYTHON="$(command -v python)"
export PYTHONPATH=src:.
acceptance_run=$(mktemp -d)
"$FREQTRADE_PYTHON" -m pytest -q --junitxml="$acceptance_run/tests.xml"
"$FREQTRADE_PYTHON" tools/audit_historical_coverage.py \
  --config config.json --timerange 20250101-20250115 \
  --output "$acceptance_run/coverage.json" --markdown "$acceptance_run/coverage.md"
# 全币种审计返回 1 表示已生成报告但范围不全；不要解释成全部可回测。
"$FREQTRADE_PYTHON" tools/run_offline_acceptance.py phase4 \
  --coverage "$acceptance_run/coverage.json" --output "$acceptance_run"
"$FREQTRADE_PYTHON" tools/run_offline_acceptance.py phase5 --output "$acceptance_run"
```

最低冻结验收不需要代理在线。新元数据采集和扩展联网验收必须显式执行；日常离线回测命令、生产新快照采集、完整 Lint/格式命令及两侧工件重放见 [操作手册](../operations.md)、[最低回测报告](phase4_offline_backtest.md)、[扩展报告](phase4_extension.md)。系统需允许 unprivileged user/network namespace，且已安装 strace；不具备时只能记录 BLOCKED/未验收，不能退回 mock 宣称 PASS。

无隐式迁移：普通 `freqtrade backtesting/trade` 不改用快照；只有显式专用入口离线。建议先保留本轮最小可信范围，再独立确认 16 币历史 funding 时刻表和早期数据可得性；经明确授权补数据/采集更广范围真实快照后，按同样空缓存、OS 隔离及严格对照扩大验收。无需通过改变策略来处理数据不足。

资料：[Freqtrade backtesting](https://www.freqtrade.io/en/stable/backtesting/)、实际安装版本 Exchange/Binance/Backtesting 与 CCXT parse_market/set_markets 源码、[Binance USDT-M Exchange Information](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/Exchange-Information)、[Python audit events](https://docs.python.org/3/library/audit_events.html)、Linux unshare(1)/strace(1)。
