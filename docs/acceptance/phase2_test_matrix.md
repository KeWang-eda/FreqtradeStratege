# Phase 2：测试矩阵与回归比较器

状态：**PASS（先期全量后，经独立复核补修再验）**。先期全量结果 **217 passed、0 failed、0 skipped，44.71s**，见[JUnit](phase2_pytest.xml)和[日志](phase2_pytest.log)。之后独立复核发现快照 bool/int 校验与归档配置比较两个阻断缺口，重新打开本阶段并修复；补修相关 **104 passed、0 failed、0 skipped，23.49s**，见[补修 JUnit](phase2_independent_review_pytest.xml)。最终全量统计以 Phase 6 为准，不将先期 217 项说成包含后补用例。

| 验收项 | 命令/检查 | 预期 | 实际 | 证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 全量及负向矩阵 | pytest 全量和补修相关集 | 实际执行、无意外 skip | 217/0/0；补修 104/0/0 | phase2_pytest.xml、phase2_independent_review_pytest.xml | PASS |
| 严格配置对照 | 唯一 native `_config.json`，训练/模型/特征/交易所/transport 均比较 | 同结果但不同配置必须失败 | 新增六项负向用例通过 | test_freqtrade_regression_report.py、补修 JUnit | PASS |
| 原生交易回归 | 新缓存 + netns + strace + 严格比较 | 无网络且结果一致 | 13 交易、26 订单、4 预测，配置/数值一致 | 补修真实集成用例；Phase 4 完整工件 | PASS |
| 原生运行边界 | 核心校验和普通类实现对照 | 无全局替换 | 未修改原生类，模式拒绝先于客户端 | Phase 1 / 补修测试 | PASS |

代码变更：补齐测试、比较器、严格 JSON 类型判断与不支持市场覆盖的预检；新增工件/本报告，无删除文件。满足 Phase 3 准入，未解决的数据覆盖和历史规则时点风险留待 Phase 3；实际账户/订单仍未验收。

## 矩阵

| 主题 | 覆盖内容 | 用例所在文件 / 实际结果 |
| --- | --- | --- |
| 文件/JSON | 缺失、空、损坏、重复键、非对象 envelope、未知/缺字段、schema 类型 | `test_snapshot_contract.py` + 原离线测试，通过 |
| 真实性/完整性 | envelope/raw 哈希、篡改 normalized、缺 PRICE/LOT/MARKET_LOT/NOTIONAL、重复 raw symbol/filter、异常数值 | 同上，通过；不会让 CCXT 的 fallback 代替真实缺失规则 |
| 范围/时间 | 缺/重复 pair、版本、交易所、过期/未来/naive/无效/倒置时间、错误 JSON 原始类型 | 同上，通过 |
| 原生档位 | 缺/空档位、非法上限/杠杆、原文件哈希不匹配 | 同上，通过 |
| 采集失败 | 超时/API 异常、不完整响应、写入/fsync/link 故障、已有文件/悬空符号链接、并发发布不覆盖 | 同上，通过；本组通过本地重放真实响应做故障注入，**不算新联网采集验收** |
| 突然终止 | 在临时文件写入中实际 SIGKILL 子进程；最终文件不存在，遗留临时文件无法校验 | 同上，通过；未删除或自动采用未完成临时文件 |
| 模式/配置 | LIVE、DRY_RUN、HYPEROPT、其他交易所/cross、动态 PairList、重复/模式 pair、TLS/市场范围覆盖；预检时未创建客户端 | `test_offline_lifecycle.py`，通过 |
| 生命周期 | 原生构造失败、引擎构造失败、start 失败、重复 close、已有运行事件循环、强制/重复刷新 | 同上，通过；同步/异步客户端和 loop 清理，原异常传播 |
| 审计 | HTTP、正/反向 DNS、connect/sendto/sendmsg、任意子进程、shell、git fetch；捕获拒绝异常仍失败；安装失败也留失败报告 | `test_network_audit_boundary.py`，通过 |
| 普通交易隔离 | 原生 Binance/Exchange 和全局同步/异步 CCXT 方法保持原实现，FreqAI live/dry-run 下载分支保留 | 既有测试继续通过；不声称实际账户/订单已验收 |
| 比较器负向 | 交易对/方向/时间/价格/退出理由、嵌套订单 fee、缺/额外字段、bool/数值、三个信号导出、预测值、schema/标签/统计/额外 metadata、缺/额外工件、指标 | `test_freqtrade_regression_report.py`，全部能发现差异或明确拒绝无效输入 |
| 非有限值 | JSON 指标/metadata 的 NaN/Inf 明确拒绝；帧无限值失败；帧成对 NaN 缺失掩码允许，但单边 NaN 失败 | 同上，通过；不填零 |
| 真实集成 | 空 userdir、本地 BTC/ETH、原生 FreqAI 重训、内核网络命名空间、strace、HTTP/socket 审计、完整结果比较 | 本轮实际通过，未 skip；13 笔交易、26 订单、4 个预测文件与历史联网参考一致 |

## 比较政策与修复

旧比较器只挑四个 metadata 字段，额外模型信息的变化可能漏过。现在比较所有模型 metadata 的键和值、未知和额外字段；验证 feature/label 列表及标签统计结构。原先精确比较的 metadata 仍然精确比较，嵌套交易/订单也增加精确检查；没有放宽为“接近即可”。预测及信号 DataFrame、回测指标仍使用原有 `rtol=atol=1e-12`。

只排除原有的两个结果字段 `backtest_run_start_ts`、`backtest_run_end_ts`，理由是进程真实执行时间不同，和历史决策无关。全部历史时间边界、交易参数、钱包/回撤/盈亏和嵌套指标仍比较。

独立复核补齐 `_config.json` 后，不豁免 HTTP timeout、proxy 或整个 exchange 配置。受验离线命令加载与参考相同的 mihomo overlay，以获得相同配置；离线客户端不使用该代理，namespace 仍断网。`config_files` 仅规范化项目绝对根，保留完整相对路径和合并来源顺序。先期 `phase2_native_regression.json` 来自补修前版本，未比较归档配置，保留作历史证据，不能作为最终严格配置验收；最终证据使用 Phase 4。

`metadata.data_path` **没有被删除或忽略**：先验证它与工件所属模型相对目录一致，再规范化独立 userdir 的绝对根前缀。两次重训按要求使用不同运行根目录，这个前缀必然不同；模型相对目录、模型文件名及其余 metadata 仍须一致，错误后缀会失败。该路径过去整个不在比较范围内，本次覆盖更严格，而不是为使交易差异通过而排除字段。政策也写入每份新回归 JSON。

新增严格标签统计验证时，一项负向 fixture 只换了标签列表而没同步统计键，比较器直接拒绝无效模型 metadata，原测试却仅期待差异报告，因此出现 **1 failed / 75 passed**。已保留[失败日志](phase2_contract_failed_attempt.log)/[JUnit](phase2_contract_failed_attempt.xml)，并将该 fixture 改为“内部一致但与基线不同的标签”，继续验证比较器能够报告真实标签差异；没有放宽校验。

## 复现与本轮证据

```bash
PYTHONPATH=src "$FREQTRADE_PYTHON" -m pytest -q \
  --basetemp=/tmp/quant-phase2-final-pytest-20261017 \
  --junitxml=docs/acceptance/phase2_pytest.xml
"$FREQTRADE_PYTHON" -m ruff check src tests tools
"$FREQTRADE_PYTHON" -m ruff format --check src tests tools
```

`--basetemp` 仅供可丢弃测试目录，pytest 会清理它；不得指向真实 data、models 或既有工件。

真实回测用例重新生成的[网络审计](phase2_native_network.json)、[系统调用](phase2_native_network.strace)、[完整回归 JSON](phase2_native_regression.json)已保存。Python 请求/DNS/socket 事件均为 0，完成标志为 true、拒绝数为 0；strace 没有 connect/sendto/sendmsg/sendmmsg，仍保留 aiohttp 的本地 IPv6 bind 探测。参考是已冻结的联网运行，本轮没有将其冒充重新联网运行。

Lint/格式：[检查](phase2_ruff.log)、[格式](phase2_format.log)。777 条 warning 来自依赖 joblib/NumPy，没有屏蔽。原始失败 XML 中含 pytest 终端的行末空格，和原始日志一起保留；源码/配置/文档空白检查单独运行，不能通过改写测试证据来消除空格。

本阶段不声称已完成 72 个币种或其他区间的交易验收；系统隔离前置条件不满足的环境将明确 skip，该环境不能称为通过。本机本轮 217 项中没有 skip。
