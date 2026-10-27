# Freqtrade 历史回测完全离线：市场元数据快照方案与验收

> 本文保存首次实现与 115 项测试时点的验收记录。后续已加固严格类型、原始规则、原子发布、资源生命周期、网络审计及全部归档配置对照；当前 Phase 0–6 结果与准确命令以[分阶段最终报告](acceptance/final_report.md)和[操作手册](operations.md)为准。原始历史证据保留，不能把旧比较范围当作当前严格配置验收。

检查及实现日期：2026-10-17。起始工作区为 `main @ 3739472`，保留原有未提交修改。环境为 Python 3.13.13、Freqtrade 2026.7、CCXT 4.5.75、XGBoost 3.4.1。

**结论：已实现并实际验证“真实市场快照 + 本地历史行情 → 原生 Freqtrade/FreqAI 回测完全离线”。通过独立入口注入交易所实例，使用的仍是原生 `Backtesting.start()`。直接执行原装 `freqtrade backtesting` 仍会联网初始化市场，未给该命令偷偷替换行为。**

## 1. 根因、技术可行性与方案选择

原调用链已在[本地历史数据与 Binance 网络请求排查报告](local_data_network_audit.md)中验证：

```text
freqtrade backtesting
  → setup_optimize_configuration(..., RunMode.BACKTEST)
  → Backtesting(config)
  → ExchangeResolver.load_exchange(load_leverage_tiers=True)
  → Binance / Exchange.__init__(validate=True)
  → reload_markets → _load_async_markets → _api_reload_markets
  → CCXT async load_markets → fetch_markets
  → GET fapi.binance.com/fapi/v1/exchangeInfo
```

网络失败发生在读历史 K 线之前，最终因没有可用市场信息，`validate_stakecurrency()` 报 `Could not load markets`。该请求获取精度、数量/金额限制、合约大小等，并非重新下载行情。

本次检查了已安装源码的 `Exchange.__init__`、`_init_ccxt`、`reload_markets`、`validate_config`，`ExchangeResolver`，`Binance.additional_exchange_init/load_leverage_tiers`，`Backtesting.__init__/start`，以及 CCXT 的 `fetch_markets/parse_markets/set_markets/set_markets_from_exchange`。

| 方案 | 评估与结论 |
| --- | --- |
| 只设置配置、缓存目录或 `fetchMarkets.types` | 没有离线快照加载配置；初次 `reload_markets(force=True)` 会强制加载。范围覆盖只能把 3 个请求缩为 1 个，不能离线 |
| 原装 CLI 配置外部 exchange 插件 | 此版本 `ExchangeResolver` 只在框架导出模块内查找类，没有外部类路径配置，不采用 |
| 注入 exchange 实例到原生 `Backtesting` | 构造器明确接收 `exchange: Exchange \| None`，框架自身也复用此能力；采用 |
| 修改虚拟环境、运行时替换全局方法、关闭校验或模拟 HTTP 服务 | 不采用；会掩盖精度或规则缺失，且污染其他运行模式 |

最小扩展为仓库内的 `SnapshotBinance(Binance)`，只覆盖两个版本相关的内部钩子：`_api_reload_markets` 读取已校验快照，`_init_ccxt` 创建带拒绝 HTTP 传输方法的普通 CCXT 子类。没有修改框架文件、替换原类的方法或返回伪造 HTTP 响应。`Backtesting(..., exchange=...)` 是现有注入口，但两个内部钩子不是稳定插件 API，因此显式锁定版本，升级后必须重新审查和测试。

## 2. 实现与关键调用链

```text
显式 capture（联网）
  → 真实 CCXT Binance.fapiPublicGetExchangeInfo()
  → 保存完整响应、CCXT 解析的指定市场、规则来源和校验值

独立 backtesting 入口（离线）
  → 原生 Arguments / setup_optimize_configuration(BACKTEST)
  → 模式、交易所和静态交易对范围检查
  → load_snapshot：校验版本、时间、SHA256、原始响应与解析结果、杠杆档位
  → SnapshotBinance：先强制 dry_run=True，再执行原生构造和全部配置校验
      → _api_reload_markets → CCXT set_markets（仅内存数据，无 HTTP）
      → 原生 reload_markets 共享同步/异步市场信息
      → 原生 validate_config、fill_leverage_tiers、additional_exchange_init
  → Backtesting(config, exchange=实例).start()
  → 原生历史数据读取、FreqAI 训练/预测、撮合、统计及导出
```

保留的原生检查包括时间周期、stake currency、订单类型、交易模式/保证金模式、pricing、FreqAI 配置和 startup candles；策略载入后的 `validate_config_consistency()` 仍执行。新增测试以无效 `7h` 周期确认原生校验没有被绕过。

原生回测原本就设置 `dry_run=True`。注入实例先于回测引擎构造，所以适配层在构造交易所前设置同样的值，避免进入真实账户初始化分支。**dry_run 标志不等于 `RunMode.DRY_RUN`**：适配层只接受 `RunMode.BACKTEST`，LIVE、DRY_RUN、HYPEROPT 都在客户端创建前拒绝。

同步及异步 CCXT 子类只覆盖 `fetch()`：意外的 HTTP 调用直接抛 `OfflineNetworkError`，不会回退到真实传输。强制或定时市场刷新也只读内存中的同一份已校验快照。网络诊断工具里的 requests/aiohttp 拦截仅用于测试观察与拒绝请求，不参与运行时市场加载。

## 3. 快照内容、真实性和失败策略

仓库中的[真实验收快照](baseline/acceptance/binance-usdt-market-snapshot.json)于 **2026-10-17 12:04:06 UTC** 通过本机 mihomo 获取，来源为真实公共 HTTPS 接口，无密钥、无签名请求。快照只授权 BTC/ETH 两个市场用于本次验收，完整原始响应中的其他市场不会被自动启用。

| 字段 | 内容 / 校验 |
| --- | --- |
| `schema_version`、`exchange`、`market_type` | schema 1、binance、linear-usdt-perpetual |
| `source` | 真实 `https://fapi.binance.com/fapi/v1/exchangeInfo`，GET，未认证 |
| `request_started_at`、`acquired_at` | 带时区的请求开始和获取完成时间；拒绝时间倒置、未来异常时间和过期快照 |
| `versions` | Freqtrade 2026.7、CCXT 4.5.75，严格匹配当前环境和适配器支持版本 |
| `pairs` | 明确的适用交易对；必须覆盖实际白名单和 FreqAI `include_corr_pairlist` |
| `raw_response`、`raw_sha256` | 完整真实响应，包括交易规则 filters、rateLimits、serverTime 等 |
| `normalized` | CCXT 解析后的完整市场字段、precision、limits、contractSize、币种和精度模式 |
| `leverage_rules` | 该版本原生回测使用的 `binance_leverage_tiers.json` 来源、整个文件 SHA256 及适用交易对原始档位 |
| `sha256` | 除本字段外全部 JSON 的规范化 SHA256，覆盖描述字段和所有载荷 |

每次加载都用相同版本的真实 CCXT parser 重新解析原始响应，与快照中的 normalized 对照；杠杆档位与本机原生文件逐项和哈希对照。不推算或补齐任何缺失交易规则。

`exchangeInfo` **不提供实际账户的杠杆档位**。本实现没有声称从该响应取得档位，而是完整保留 Freqtrade 原生历史回测的内置档位来源，没有私自调用账户接口、更换档位或伪造数据。

快照默认最长 30 天。复现实验可以显式指定正数 `--snapshot-max-age-days`；不会自动更新或忽略校验。文件缺失、JSON 损坏/重复键、哈希错误、解析规则不一致、版本不符、缺交易对、档位变化或超期都明确失败，CLI 对快照错误返回 2。capture 拒绝覆盖现有文件，刷新时应使用新文件名。

验收快照的规范化载荷 SHA256：`c085efcfe8e2c3f62e39fb5e983e601fc89fd20d7c45893e0ade640092ac5bc2`。这是 JSON 载荷的哈希，与整个格式化文件的 `sha256sum` 不同。SHA256 用于完整性校验，不是交易所数字签名；快照文件必须来自可信采集流程。

## 4. 修改文件与策略不变量

| 文件 | 本次增量 |
| --- | --- |
| [market_snapshot.py](../quant/execution/market_snapshot.py) | 显式采集、真实解析、范围/版本/时效/完整性校验，原生杠杆规则指纹 |
| [offline_backtest.py](../quant/execution/offline_backtest.py) | 历史回测专用 Binance/CCXT 子类和原生引擎注入入口 |
| [audit_local_network.py](../tools/audit_local_network.py) | 诊断分发增加 offline-backtest；拒绝用该分支执行 capture |
| [verify_freqtrade_regression.py](../tools/verify_freqtrade_regression.py) | 在完整交易/订单、信号、预测和 schema 对比之外增加全部结果字段和指标对照 |
| [test_offline_freqtrade.py](../tests/integration/test_offline_freqtrade.py) | 18 项真实快照、失败条件、模式隔离、原生校验和完全断网集成测试 |
| [test_freqtrade_regression_report.py](../tests/integration/test_freqtrade_regression_report.py) | 新增指标变化必须导致回归失败的测试 |
| [证据目录](baseline/acceptance/)及本报告、README、运行/验收文档 | 保存真实快照、网络审计、系统调用、结果和复现工件；旧证据保留 |

`config.json`、`MyStrategy.py`、`quant/models/freqai/`、原有策略适配器、features、labels 和 portfolio 源码没有修改。4h、startup=100、预测跨度 3、volnorm、92 列原生特征、BTC/ETH 相关特征、交易对排名及稳定同分顺序、单仓、开平仓、min(2,max_leverage)、stoploss=-1、ROI=999 和 trailing 设置保持不变。

## 5. 真实验证结果与证据

### 5.1 隔离环境中的完整原生回测

实际启动路径使用 `unshare --user --map-root-user --net` 创建独立网络命名空间，没有可用的外部网络，同时加上 `strace -f -e trace=network` 与 Python HTTP/DNS/socket 全拒绝审计。BTC/ETH 使用独立空 userdir，UTC `2025-01-01 → 2025-01-15`，`--cache none --export signals`。

结果：退出码 0，重新训练 2 个时间窗口 × 2 个交易对，每个模型 92 个特征。HTTP 请求 **0**，DNS/IP connect/sendto 审计事件 **0**，拒绝操作 **0**。系统调用记录没有 `connect/sendto/sendmsg/sendmmsg`；aiohttp 导入时的 IPv6 支持探测创建了本地 socket 并尝试绑定 `::1`，返回 `EADDRNOTAVAIL`，未连接外部目标、未发送数据。

| 对照项 | 原联网基线 | 本次完全离线 | 结果 |
| --- | --- | --- | --- |
| 交易 | 13 | 13 | 完整记录一致 |
| 订单 | 26 | 26 | 嵌套订单字段一致 |
| 总盈亏 USDT | -7.72891548 | -7.72891548 | 一致 |
| 最终余额 USDT | 992.27108452 | 992.27108452 | 一致 |
| Sharpe | -2.4156875909722673 | -2.4156875909722673 | 一致 |
| 最大账户回撤 | 0.019077787162898503 | 0.019077787162898503 | 一致 |
| 逐窗口预测 | 4 文件，每个 42 行 | 同左 | 数据及文件 SHA256 全部一致 |
| signals/rejected/exited | 所有导出 DataFrame | 同左 | 一致 |
| 训练 schema 和标签统计 | 4 个模型，92 特征 | 同左 | 一致 |
| 结果配置及指标 | 115 个顶层字段及全部嵌套值 | 同左 | 一致，容差 1e-12 |

对比只排除两项实际执行起止时间戳 `backtest_run_start_ts/end_ts`；历史时间边界、钱包统计、参数及其他指标均比较。归档文件名和 zip 哈希可以因执行时间不同而变化，验收没有依赖退出码或归档哈希相同。

证据：[离线网络审计](baseline/acceptance/offline-network.json)、[系统调用记录](baseline/acceptance/offline-network.strace)、[原生日志](baseline/acceptance/offline-backtest.log)、[结果 ZIP](baseline/acceptance/offline-backtest.zip)、[完整回归报告](baseline/acceptance/offline-regression.json)。

原联网基线使用之前已验证的 `network-after` 运行，其[审计](baseline/acceptance/network-after.json)仅有 1 个真实 fapi 请求。[原联网参考工件](baseline/acceptance/native-online-reference.tar.gz)和[本次离线工件](baseline/acceptance/native-offline-artifacts.tar.gz)保存原生 ZIP、4 个预测文件及对应 metadata，支持脱离临时目录再次对比。

已从这两份归档解包再次完成对比，结果为通过，见[归档复验报告](baseline/acceptance/offline-regression-archived.json)。

### 5.2 测试命令和范围

```bash
/home/wangke/project/freqtrade/.venv/bin/python -m pytest -q \
  --junitxml=docs/baseline/acceptance/offline-pytest.xml
/home/wangke/project/freqtrade/.venv/bin/ruff check \
  quant tests tools MyStrategy.py  \
  verify_no_lookahead.py
/home/wangke/project/freqtrade/.venv/bin/ruff format --check \
  quant tests tools MyStrategy.py  \
  verify_no_lookahead.py
git diff --cached --check -- . ':!docs/baseline/acceptance/*.log'
```

实际：**115 passed，33.47 秒，无跳过**；[JUnit](baseline/acceptance/offline-pytest.xml)。新增 19 项测试，覆盖缺失/损坏快照子进程返回 2 且零网络事件，哈希/原始响应/解析规则/版本/交易所/档位/过期错误，重复 JSON 键、缺交易对、非回测模式拒绝、原生周期校验、强制刷新不联网，以及完整网络命名空间回测与联网参考的逐项对比。Ruff lint 通过，73 个 Python 文件格式检查通过。

空白检查覆盖已暂存源码、配置与文档；原始终端日志含框架输出的行末空格，为保留日志及既有哈希，检查时只排除验收目录的 `.log` 文件，没有改写这些证据。

261 条 warning 来自当前 joblib 与 NumPy 2.5 的数组形状弃用提示；没有升级依赖。缺少真实数据、unshare/strace 或命名空间权限的其他环境会明确 skip 完整集成用例，不能据此声称离线回测已验收；本机该用例实际执行通过。

三类验收明确区分：独立研究本地训练/验证/比较在原有和本次测试中通过；原生回测经本适配入口完全断网通过；普通实盘/模拟交易类和联网方法保持原样且模式隔离测试通过，但没有执行真实账户/订单验收。

## 6. 运行方式

### 6.1 显式联网采集新快照

在仓库根目录执行，输出到已存在的目录。该命令只请求市场元数据，不请求历史 K 线；不覆盖已有快照。

```bash
cd /home/wangke/project/FreqtradeStratege
quant_python=/home/wangke/project/freqtrade/.venv/bin/python
market_snapshot=/tmp/binance-usdt-markets-$(date -u +%Y%m%dT%H%M%SZ).json
PYTHONPATH=. "$quant_python" -m quant.execution.offline_backtest capture \
  --snapshot "$market_snapshot" \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --proxy http://127.0.0.1:7890
```

可直连的环境可省略 `--proxy`。没有改变 TLS 校验或系统代理。更多交易对须显式列入 `--pairs`，同时包含相关特征依赖交易对；真实响应或原生杠杆文件没有对应规则时失败。

### 6.2 完全离线调用原生回测引擎

可使用上一步的 `market_snapshot`，或在有效期内使用已提交的真实验收快照：

```bash
cd /home/wangke/project/FreqtradeStratege
quant_python=/home/wangke/project/freqtrade/.venv/bin/python
market_snapshot="$PWD/docs/baseline/acceptance/binance-usdt-market-snapshot.json"
offline_run=$(mktemp -d /tmp/quant-offline-run.XXXXXX)
mkdir -p "$offline_run/results"

PYTHONPATH=. "$quant_python" -m quant.execution.offline_backtest backtesting \
  --snapshot "$market_snapshot" -- \
  -c "$PWD/config.json" -c "$PWD/configs/backtest-local.json" \
  --userdir "$offline_run" --datadir "$PWD/data" \
  --strategy-path "$PWD" --freqaimodel-path "$PWD/quant/models/freqai" \
  --strategy MyStrategy --timerange 20250101-20250115 \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --cache none --export signals --backtest-directory "$offline_run/results"
```

`--` 前是快照入口选项，后是原生回测参数。配置合并仍是原生配置 → 历史回测覆盖 → CLI；离线命令不需要 mihomo 配置。`--cache none` 只禁用交易结果缓存，使用新 userdir 才能确保 FreqAI 重新训练。

要重现本次的内核隔离与审计，使用新的 `offline_run`，将上述执行命令换为：

```bash
unshare --user --map-root-user --net \
  strace -f -e trace=network -o "$offline_run/network.strace" \
  env PYTHONPATH=. "$quant_python" tools/audit_local_network.py \
  --policy deny-all --report "$offline_run/network.json" \
  offline-backtest backtesting --snapshot "$market_snapshot" -- \
  -c "$PWD/config.json" -c "$PWD/configs/backtest-local.json" \
  --userdir "$offline_run" --datadir "$PWD/data" \
  --strategy-path "$PWD" --freqaimodel-path "$PWD/quant/models/freqai" \
  --strategy MyStrategy --timerange 20250101-20250115 \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --cache none --export signals --backtest-directory "$offline_run/results"
```

最简重复验收命令为 `"$quant_python" -m pytest tests/integration/test_offline_freqtrade.py -q`，会自行创建全新缓存、隔离网络和对照参考。保留旧快照复现实验时需显式设置适当的 `--snapshot-max-age-days`；该测试使用 36500 天容限，仅为了长期验证冻结参考，不是生产默认时效。

从持久工件再次运行完整结果对比：

```bash
comparison_run=$(mktemp -d /tmp/quant-offline-compare.XXXXXX)
mkdir -p "$comparison_run/online" "$comparison_run/offline"
tar -xzf docs/baseline/acceptance/native-online-reference.tar.gz -C "$comparison_run/online"
tar -xzf docs/baseline/acceptance/native-offline-artifacts.tar.gz -C "$comparison_run/offline"
PYTHONPATH=. "$quant_python" tools/verify_freqtrade_regression.py \
  "$comparison_run/online" "$comparison_run/offline" --report "$comparison_run/regression.json"
```

这些参考工件含 joblib 信号导出，只应读取本仓库内可信的本地产物。

### 6.3 研究与正常交易

研究继续使用原有 `quant.cli validate/dataset-build/run/compare`，无需导入离线交易所适配层，命令见[原报告](local_data_network_audit.md#6-运行方式)。实盘和模拟交易继续使用原装 `freqtrade trade`；不配置、不注入本快照类，也不运行网络诊断拦截器。

## 7. 剩余风险和适用边界

1. 本适配器严格支持 Freqtrade 2026.7 / CCXT 4.5.75、Binance USDT 永续、isolated、StaticPairList。其他版本、交易所和运行模式不在支持范围，不能自动放宽版本检查。
2. 当前快照和交易一致性验收只覆盖 BTC/ETH、两周窗口。原有联网原版/新版三周回归证据仍保留，但没有把它算作本次三周离线验收，也没有声称 72 个交易对全部断网通过。
3. 当前快照记录采集时规则，并不证明其规则等于 2025 年历史时点的规则；这一限制也存在于原生联网启动后回放历史。不能为退市市场、历史变更或缺规则市场自行补值。
4. 原生内置杠杆档位并非本次从账户接口核验的实时规则。保留该来源是为了保持原生回测语义；版本或文件变化会要求重新采集、验证。
5. 本地 K 线、mark、funding_rate 的范围仍须覆盖训练预热及回测日期。完整 365 天训练所需 startup 仍由 FreqAI 计算；适配器不会补下载或填造缺失数据。原报告记录了部分币对数据截断、晚开市等限制。
6. CCXT 客户端拒绝网络请求不等于给任意新增策略代码建立了系统级沙箱。当前策略已在内核网络隔离下完整运行；未来若策略/插件自行使用其他网络库，应继续在命名空间与审计器下验收。
7. 未更改全局网络、TLS、账户接口或策略行为；“普通联网类未被修改”及分支测试不替代实盘账户/订单端到端验收。

参考：[Freqtrade Backtesting](https://www.freqtrade.io/en/stable/backtesting/)、[CCXT Manual / markets](https://docs.ccxt.com/)、[Binance USDT-M exchangeInfo](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/Exchange-Information)。接口可行性与结果以本机指定版本源码和以上实际测试证据为准。
