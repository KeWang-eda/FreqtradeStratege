# Phase 3：历史数据质量与多币种覆盖审计

阶段状态：**PASS（只读数据预检）**。本轮重新审计 72 个交易对、216 个真实 Feather 文件；所有交易对都有明确结论，BTC/ETH `20250101-20250115` 达到完整数据、相关币对、标签边界及可信快照准入条件。**此状态不代表 72 币已全部回测通过**；完整原生训练、交易与联网对照由 Phase 4 验收。

执行时间、依赖版本、输入配置和 SHA 均记录在 [机器报告](phase3_data_coverage.json)。本次环境为 Freqtrade 2026.7 / CCXT 4.5.75 / pandas 3.0.5 / NumPy 2.5.2 / PyArrow 25.0.1。没有修改、重写或下载行情。

## 验收表

| 验收项 | 执行命令或检查方式 | 预期 | 实际 | 证据 | 状态 |
|---|---|---|---|---|---|
| 交易对与依赖枚举 | 下方全量审计命令；原生 config 合并、StrategyResolver | 白名单与相关币对均覆盖 | 72 个交易对，BTC/ETH 相关币对；include_timeframes 为 4h | [JSON](phase3_data_coverage.json) | PASS |
| 文件存在与真正可用分离 | 原始 Feather 读取；不调用 fill/reindex | 检出缺文件、训练预热及规则范围问题 | 216/216 存在；56 币 raw 条件通过，只有 BTC/ETH 在冻结快照范围 | [逐币/逐文件表](phase3_pair_files.md) | PASS |
| schema、UTC、排序、重复、有限值及 OHLC 边界 | 工具 `inspect_file()` | 真实原始行有效，缺失不填造 | 全文件 UTC、排序正确；0 重复、0 非有限值、0 非法 OHLC/负成交量；全部 4h/mark 文件内部 0 缺行 | [JSON](phase3_data_coverage.json) | PASS |
| 训练预热与区间 | 原生 DataProvider.get_required_startup | 从实际策略/配置求值 | startup 100；365 天训练；4h 合计 2290 根；起始要求 2023-12-16 08:00 UTC | [JSON requirements](phase3_data_coverage.json) | PASS |
| 标签与相关币对时间对齐 | 实际 `set_freqai_targets()`；原生 FreqAI 窗口切分 | `shift(-horizon)` 对应真实时间，训练尾部标签缺失 | 当前 horizon=3；合格 4h 文件无偏移；训练窗口各 2190 行、2187 有限标签、末 3 标签保持缺失，越界标签 0；BTC/ETH corr 对齐无缺行 | [JSON 每币 labels/alignment](phase3_data_coverage.json) | PASS |
| funding 语义 | 观测真实事件间隔；与 mark 时间内连接一致性 | 不把 1h 文件名解释为每小时付款 | BTC/ETH 8h 事件；最低窗口各 42 条 funding 事件均存在对应 mark。16 币变频需核实，不补造事件 | [JSON funding cadence](phase3_data_coverage.json) | PASS |
| 原始文件保护 | SHA 与 Phase 0 逐文件比较；读取前后 SHA 比较 | 数据未变 | 216/216 与 Phase 0 一致；读取期间变化 0 | [JSON summary](phase3_data_coverage.json) | PASS |
| 最低范围准入 | 真实 6 文件与快照校验；`unshare -Urn` 加 Python DNS/connect/sendto 拒绝审计 | BTC/ETH 既定窗口可用，无网络依赖 | 退出 0，minimum_scope_ready=true，观测网络操作 0 | [最低范围](phase3_minimum_coverage.json)、[审计](phase3_minimum_network_audit.json) | PASS |
| 扩展范围准入 | 下方 BTC/ETH/BNB 三周命令 | raw 条件独立于快照范围 | 3 币/9 文件 raw 全通过；BNB 未进入现冻结快照，退出 1 明确阻止离线准入 | [扩展 JSON](phase3_extension_coverage.json) | PASS |
| 错误发现能力 | `pytest tests/unit/test_historical_coverage.py` | 故意缺文件、错位、非法行情失败关闭 | 30 passed / 0 failed / 0 skipped；真实配置指向缺数据目录或非法时区后 gate=false，未创建/下载行情 | [JUnit](phase3_pytest.xml)、[日志](phase3_pytest.log) | PASS |
| Lint 与格式 | `ruff check` / `ruff format --check`（本阶段两个 Python 文件） | 无错误 | 均退出 0 | [Lint](phase3_ruff.log)、[格式](phase3_format.log) | PASS |

## 真实覆盖结论与缺口

全量审计使用半开窗口 `[2025-01-01 00:00, 2025-01-15 00:00)`；4h 历史要求 `[2023-12-16 08:00, 2025-01-15 00:00)`，2374 行。mark 仅要求回测窗口，336 行；funding 按真实事件计数，不按存储键推测付款次数。所有 72 币的起止时间、行数、重复、间隔、SHA、窗口缺口和单独 metadata 结论列在 [完整覆盖表](phase3_pair_files.md)，不是只列成功币种。

行情预热确实不足的文件：

| 交易对 / 文件 | 缺失区间（UTC，停止不含） | 缺 4h 行数 | 结论 |
|---|---|---:|---|
| RENDER / `data/futures/RENDER_USDT_USDT-4h-futures.feather` | 2023-12-16 08:00 至 2024-07-26 08:00 | 1338 | 不能按本窗口和原 365 天训练参数完整回测 |
| SUN / `data/futures/SUN_USDT_USDT-4h-futures.feather` | 2023-12-16 08:00 至 2024-08-22 12:00 | 1501 | 同上 |

这些文件可能受真实上市时间限制；不能承诺下载可补足，更不能制造上市前行情。若需要纳入，须选取本地历史满足原训练窗口的更晚回测范围，并另做验收；本任务不改训练时长或擅自下载。

有 16 币的全历史 funding 观测付款间隔变化，保守标记 `funding_schedule_requires_verification`：AXS、BSV、CAKE、ENJ、IOST、KAVA、ONT、RENDER、RLC、SKL、SOL、SUN、TRB、XTZ、ZIL、ZRX。这**不等于已证实缺付款数据**，但缺少历史付款时刻表时无法独立证明事件完整性，所以不把它们计入 strict raw-ready。JSON 保存全历史间隔分布、观测变化时间、所选窗口分布；RENDER/SUN 为大量 4h 加一次 8h，明确待核实而非断言缺一笔付款。

XMR、XRP、XTZ、YFI、ZEC、ZEN、ZIL、ZRX 的 4h 文件在 2025 年结束，**不影响 2025 年 1 月所选窗口**，但不可把数据覆盖扩展至 2026 年；精确最后日期见逐文件表。其余文件也有不同起点，完整共同范围须重新跑工具，不应按全局最早/最晚时间推断每币可用。

冻结市场快照只覆盖 BTC/ETH。其余 70 币属于 metadata 范围未覆盖，即使 raw 条件通过也不能直接使用此快照。快照于 `2026-10-17T12:04:06.169588+00:00` 从真实 Binance 响应采集，记录的当前精度、限额和原生杠杆规则**不代表 2025 年历史真实规则**；校验通过证明工件完整、版本及规则来源一致，不证明过去市场规则相同。

## 代码变更与设计决策

- 新增 `tools/audit_historical_coverage.py`：只读审计，原生合并配置和 StrategyResolver 解析策略，通过 DataProvider 动态计算所需预热；没有 Exchange 实例、下载器或模型目录创建。读取原始数据而非框架填补后的数据，保存按币及按文件 JSON/Markdown。
- 新增 `tests/unit/test_historical_coverage.py`：30 项测试，包含缺失/空/损坏文件、错 schema、非 UTC/NaT、重复/乱序/错位时间、NaN/Inf、价格/成交量、真实标签窗口、checksum、读取期间变化、变频 funding 和完整审计负向路径。非法时区明确作为逐文件失败保留，相关币对对齐不再尝试比较无效索引。小型人工帧明确只用于单元测试，验收覆盖报告全部来自真实 Feather。
- 新增本阶段文档和 `phase3_*` 工件；没有删除文件，没有修改策略、模型、默认配置、原始行情或已有证据。
- 工具退出码：`0` 所请求交易范围连同快照完整；`1` 审计完成但有数据或 metadata 阻断；`2` 配置、工件或执行无法完成。全 72 币命令退出 `1` 是正确发现限制，不能改报为全币通过。
- 原生 `Backtesting.load_bt_data()` / mark 默认可能填 K 线；funding 使用 `fill_up_missing=False`；`combine_funding_and_mark()` 在没有 fallback 时按真实时间内连接。审计只暴露原始缺口，保留框架和交易语义。本配置没有 `futures_funding_rate` fallback。
- 标签使用完整历史前缀中的真实策略回调，训练前缀严格止于各训练终点；未创建 FreqAI 模型或预测缓存。审计结果不冒充模型训练与逐窗口预测验收。

首次实现曾混用 Feather 微秒整数时间和 Timedelta 纳秒，导致整点被误报。已保留 [失败工件](phase3_initial_failed.json)，修正为显式 `as_unit("ns")`；增加 ns/us/ms 三种真实 datetime 分辨率测试。后续报告由修正版本重新生成，没有删除失败记录。

检查依据为当前安装 Freqtrade 2026.7 的源码：`freqtrade/data/dataprovider.py` 中 `historic_ohlcv/get_required_startup`；`freqtrade/optimize/backtesting.py` 中 `load_bt_data/_load_bt_data_detail`；`freqtrade/freqai/freqai_interface.py` 中 `start_backtesting`；`freqtrade/freqai/data_kitchen.py` 中 `split_timerange/slice_dataframe`；`freqtrade/exchange/exchange.py` 中 `combine_funding_and_mark`。升级后须重新核对这些边界。

## 可复制命令

在仓库根目录，激活已安装项目依赖、Freqtrade 2026.7 / CCXT 4.5.75 的环境后执行。原配置 `datadir` 必须指向实际本地 `data/`；本机路径不写入新公开报告。数据审计不要求旧 userdir 或模型缓存。

```bash
PYTHONPATH=src python tools/audit_historical_coverage.py \
  --config config.json --config configs/backtest-local.json \
  --timerange 20250101-20250115 \
  --output docs/acceptance/phase3_data_coverage.json \
  --markdown docs/acceptance/phase3_pair_files.md
# 预期退出 1：72 币限制如上；报告仍完整写出。

PYTHONPATH=src unshare -Urn python tools/audit_historical_coverage.py \
  --config config.json --config configs/backtest-local.json \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --timerange 20250101-20250115 \
  --output docs/acceptance/phase3_minimum_coverage.json
# 预期退出 0；unshare 前提是操作系统允许非特权用户网络命名空间。

PYTHONPATH=src python tools/audit_historical_coverage.py \
  --config config.json --config configs/backtest-local.json \
  --pairs BTC/USDT:USDT ETH/USDT:USDT BNB/USDT:USDT \
  --timerange 20250101-20250122 \
  --output docs/acceptance/phase3_extension_coverage.json \
  --markdown docs/acceptance/phase3_extension_pairs.md
# 预期退出 1：三币 raw=true，当前冻结快照尚未覆盖 BNB。

python -m pytest tests/unit/test_historical_coverage.py -q \
  --junitxml=docs/acceptance/phase3_pytest.xml
python -m ruff check tools/audit_historical_coverage.py tests/unit/test_historical_coverage.py
python -m ruff format --check tools/audit_historical_coverage.py tests/unit/test_historical_coverage.py
```

以上命令本轮真实执行，输出记录见验收表。最低范围另加 `sys.addaudithook` 拒绝并记录 Python DNS/connect/sendto 调用，观测 0 次；这只是数据审计的记录，HTTP 与系统调用层的完整原生回测审计由 Phase 4 提供。

## 测试统计与下一阶段准入

本阶段定向测试 **30 passed / 0 failed / 0 skipped**；Lint/格式通过。数据审计最低范围在操作系统网络命名空间内退出 0，Python 网络操作 0。交易数、订单数、模型数及预测文件数：**本阶段未运行回测，不适用，不能记为 0 笔交易验收**。完整交易对照和指标差异由 Phase 4 记录。

允许 Phase 4 首先以 **BTC/ETH、20250101-20250115** 和冻结可信快照进入完全离线验收。`phase3_data_coverage.json` 顶层 `minimum_scope_ready=true`，`minimum_scope` 同时声明交易对与 timerange，消费端必须核对范围。扩展 **BTC/ETH/BNB、20250101-20250122** 的三币 raw 数据已预检通过；需最低验收完成并显式获取覆盖三币的真实快照后另行验收。全 72 币暂不具备统一离线回测准入条件，不能把最低范围结果推广。
