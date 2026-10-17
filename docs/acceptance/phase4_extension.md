# Phase 4 扩展：BTC/ETH/BNB 三周原生回测

状态：**PASS（BTC/ETH/BNB 三周扩展范围）**。本轮真正离线训练与严格原始工件对照于 **2026-10-17 13:15:07 UTC** 完成。此范围与最低 BTC/ETH 两周验收独立保存，不覆盖最低快照、参考归档或结果。

准入来自 [最低 Phase 4 summary](phase4_summary.json) 的 PASS 和 [三周数据覆盖](phase3_extension_coverage.json)：BTC/ETH/BNB 的 futures、mark、funding 共 9 个文件均满足真实训练、预热、相关特征和历史模拟范围。SOL 的全历史 funding 频率变更仍需付款时刻表确认，因此选择已通过保守原始数据审计的 BNB；没有修改策略币种默认列表，只在本次命令显式指定三个交易对。

## 设计与执行边界

[扩展 runner](../../tools/run_offline_extension.py) 复用最低验收 runner 的系统隔离、网络审计和发布工具。两个前置 gate、行情 SHA256 与配置 SHA256 都在任何采集之前检查。显式 capture 仅获取真实生产 `fapi/v1/exchangeInfo`；正常联网原生回测仅允许该元数据请求通过现有 loopback 代理。离线入口使用 network namespace、strace 和 deny-all Python 审计，仍要求完全没有 HTTP、DNS、connect 或 send 操作。

两次回测加载相同顺序的 `config.json` → `configs/backtest-local.json` → `configs/environment/freqtrade-mihomo.json`，使用相同三个交易对、`20250101-20250122`、`--cache none`、`--export signals` 和两个独立空 userdir。365 天训练、7 天窗口、预测跨度、特征、XGBoost 参数、止损、杠杆与交易规则均保留默认配置，不为加速验收修改。

原始交易、嵌套订单、signals/rejected/exited、逐窗口预测、全部模型 metadata、指标和完整导出配置必须先严格比较，再发布路径脱敏副本。数值容差为原有 `rtol=atol=1e-12`；交易/订单、模型 metadata 和配置保持精确比较。只沿用主比较器已经说明的两个墙钟指标排除和路径规范化，不增加排除项。

## 保留的失败尝试

| 尝试 | 实际结果 | 证据 | 后续处理 |
| --- | --- | --- | --- |
| capture attempt 1 | 真实生产 fapi 请求失败，未产生快照，online/offline/比较均未执行；BLOCKED | [summary](phase4_extension_attempt1_summary.json)、[完整日志](phase4_extension_attempt1_capture.log)、[实际命令](phase4_extension_attempt1_capture_command.json) | 保留原始日志和 SHA 清单；只做一次同代理、同生产 endpoint 重试 |
| attempt 2 初始验收 | 真实三币快照采集成功，fresh online 原生完整回测成功；新 runner 错将正常 proxy TLS sendto 与 asyncio 本地 socketpair 唤醒视作意外网络操作，主动 FAIL，offline 未执行 | [失败 summary](phase4_extension_attempt2_summary.json)、[联网日志](phase4_extension_attempt2_online.log)、[Python 审计](phase4_extension_attempt2_online_network.json)、[系统调用](phase4_extension_attempt2_online_network.strace) | 修正独占验收工具的 FD 分类，未修改共享网络审计、交易代码、快照或规则；重验原始 online 工件后继续执行尚为空的 offline userdir |

新 FD 分类仅允许已观察到连接 `127.0.0.1:7890` 的描述符上的 `sendto(NULL)`，以及已经由 `socketpair(AF_UNIX)` 创建的描述符上的本地 `sendto(NULL)`。未知描述符、显式发送目的地、额外连接、外部连接与其他发送形式都拒绝。此判断只用于正常联网参考；离线断网验收仍保持零 connect/send 的原标准。

[独占负向测试](../../tests/unit/test_offline_extension.py) 实际 **25 passed、0 failed、0 skipped，0.23s**，见 [JUnit](phase4_extension_runner_pytest.xml)。包含上述 FD 正反探针、两个 gate 的错误范围和数据篡改、普通联网审计的组件/参数/HTTP/socket/退出状态。Ruff lint 与格式检查已执行通过。

本次 continuation 使用的是 attempt 2 刚刚从空 userdir 真实训练完成的联网参考，原始日志、预测与归档未改写；没有把历史模型缓存冒充新联网训练。offline userdir 在续跑时仍只有空 `results` 目录，所有离线模型和预测都重新生成。生产源码指纹从续跑前冻结至离线结束；历史行情与 base/local 配置还须匹配更早的 Phase 3 SHA256 gate。该指纹起点区别会记录在最终 summary，不宣称存在未记录的更早源文件指纹。

## 运行命令

在仓库根目录，将 `PYTHON` 指向已安装指定依赖的解释器，`EXTENSION_OUTPUT` 指向新的空输出目录：

```bash
PYTHONPATH=src:. "$PYTHON" -m tools.run_offline_extension --help
PYTHONPATH=src:. "$PYTHON" -m tools.run_offline_extension \
  --minimum-summary docs/acceptance/phase4_summary.json \
  --coverage docs/acceptance/phase3_extension_coverage.json \
  --output "$EXTENSION_OUTPUT"

PYTHONPATH=src:. "$PYTHON" -m pytest -q tests/unit/test_offline_extension.py \
  --junitxml="$EXTENSION_OUTPUT/extension_runner_pytest.xml"
```

默认命令从全新的运行目录开始，重新真实采集快照并重新训练联网与离线两份模型。已有同前缀结果会明确拒绝覆盖；复现时不要将真实 data、models 或旧验收工件目录用作可清理的临时目录。

## 实际验收

| 验收项 | 执行或检查方式 | 预期结果 | 实际结果 | 证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 最低与数据准入 | runner 验证两个机器 gate、scope、timerange、行情及配置 SHA | 完整数据与已通过最低验收 | BTC/ETH/BNB 三周 raw ready；9 个文件保持原 SHA | [coverage](phase3_extension_coverage.json)、[summary](phase4_extension_summary.json) | PASS |
| 真实市场规则 | 显式 capture，当前 Freqtrade/CCXT 真实解析 | 新的三币生产快照，不能使用二币快照补造 BNB | 2026-10-17 13:08:12 UTC 真实采集成功；原始与规范化规则、原生档位均校验通过 | [快照](phase4_extension_snapshot.json)、[capture](phase4_extension_capture.log) | PASS |
| 新联网参考 | metadata-only Python 审计 + strace，原生完整回测 | 仅 fapi metadata 与现有 proxy transport | 1 次真实 fapi HTTP、1 次 proxy connect、4 次 proxy TLS send、1 次本地 AF_UNIX 唤醒，0 未解释操作 | [Python](phase4_extension_online_network.json)、[syscalls](phase4_extension_online_network.strace)、[完整日志](phase4_extension_online.log) | PASS |
| 系统完全断网 | `unshare --user --map-root-user --net` + strace + deny-all | 原生回测完整成功且无外部请求 | 退出 0、HTTP/DNS/socket 审计事件 0、connect/send 系统调用 0；保留 1 次 socket 创建与 1 次本地 IPv6 bind 探测 | [Python](phase4_extension_offline_network.json)、[syscalls](phase4_extension_offline_network.strace)、[完整日志](phase4_extension_offline.log) | PASS |
| 确实重新训练 | 检查空 userdir、训练完成日志、metadata、预测导出 | 每个历史窗口真实训练、预测 | 联网与离线各 9 次训练、9 份 metadata、9 个预测文件；每币 3 个窗口；每份预测 42 行，共 378 行 | [summary.training](phase4_extension_summary.json)、[完整工件](phase4_extension_artifacts.tar.gz) | PASS |
| 特征 schema | 完整逐列/顺序比较 metadata | 相同代码与配置应得到相同 schema | BTC/ETH 每模型 92 列、BNB 每模型 136 列；逐窗口完全一致，未硬编码特征数 | [regression](phase4_extension_regression.json) | PASS |
| 交易与模型严格对照 | 原始工件上主比较器 `compare_runs(online, offline)` | 交易/订单/信号/预测/metadata/指标/配置全部等价 | 29 笔交易、58 个订单；9 份预测、全部信号和模型 metadata；115 个结果指标字段、32 个配置字段通过；`differences=[]` | [回归 JSON](phase4_extension_regression.json)、[summary](phase4_extension_summary.json) | PASS |
| 发布完整性与隐私 | 逐文件与 tar member 对照 hash ledger，扫描公开文本及 ZIP JSON/Python | 发布副本可追溯且无私有根路径 | 最终 ledger 的 57 项、attempt 1 的 3 项、attempt 2 的 29 项全部 SHA256 一致；公开文本没有本机私有 home 根路径 | [检查结果](phase4_extension_publication_verification.json)、各 summary.publication | PASS |

联网与离线最终余额均为 **974.55286023 USDT**，总绝对收益均为 **-25.447139770000007 USDT**，账户最大回撤均为 **0.03503975726890054**，Sharpe 均为 **-4.802197587176136**。这些数值仅说明两条执行链路相同；本次验收不评价策略盈利能力。

快照完整文件 SHA256 为 `b752da90fbf65a4d24c4a5eaaddf6c7c122acd799afbe1042ef2f9e6edbf86d2`，规范化 envelope 载荷 SHA256 为 `80cdce1c464648ccad5297d0eb7c4fd27ea0ed49c5d88a71e433bd00297c6617`，原始响应 SHA256 为 `c6b3f75bdc99982a33a2c4f94ec24af7e7dae5e130be58f50f407cdcc5ab9f7a`。这些分别校验不同载荷，并非交易所数字签名。市场版本为 Freqtrade **2026.7**、CCXT **4.5.75**；完整环境见最终 summary。

代码变更：仅新增扩展 runner 与独占测试文件；新增本报告、扩展工件和两次真实失败记录，没有删除文件。第一版 runner 的在线系统调用判断错误已经修复并有 25 项正负测试，本次成功对照没有修改比较器容差、交易策略、模型或共享网络审计。默认 fresh runner 在 capture 前写入源码与行情 manifest；本轮成功 continuation 的源码指纹范围如前述从续跑前开始，准确标注在 summary 的 `protected_source_check_scope`。

下一阶段准入：扩展本身已通过，可纳入主 Agent 的最终工程检查与全量测试；这里的 25 项工具测试与两次真实原生运行分别计数，不冒充全仓库测试结果。仍未验收 72 币全范围、其他历史区间、不同框架版本或真实账户/订单。SOL 等变频 funding 尚未核实的币种保持数据覆盖限制，不自动补零、不下载或补造行情。

参考：[Freqtrade 回测](https://www.freqtrade.io/en/stable/backtesting/)、[Binance USDT-M exchangeInfo](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/Exchange-Information)、[strace](https://man7.org/linux/man-pages/man1/strace.1.html)、[unshare](https://man7.org/linux/man-pages/man1/unshare.1.html)。快照规则记录于采集时，不能解释为 2025 年历史时点的真实市场规则。
