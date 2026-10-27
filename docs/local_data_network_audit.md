# 本地历史数据与 Binance 网络请求排查报告

> 后续进展：本文保留首次排查及原装 CLI 的结论。已新增独立快照适配入口，实现并验证原生回测引擎完全离线，详见[市场元数据快照方案与验收](offline_backtest_snapshot.md)。这不改变原装 `freqtrade backtesting` 的联网初始化行为。

检查日期：2026-10-17。检查对象为本机 `/home/wangke/project/FreqtradeStratege`，分支 `main`，提交 `3739472`（重构），包含检查开始时已有的未提交修改；未切换远程版本，也未重置工作区。

环境：Python 3.13.13、Freqtrade 2026.7、CCXT 4.5.75、pandas 3.0.5、XGBoost 3.4.1。以下结论来自当前代码、已安装框架源码、请求拦截及实际运行。

**结论：没有发现历史回测重复下载 K 线。超时发生在交易所初始化的市场元数据查询。已消除当前 USDT 合约回测中无关的现货、币本位市场查询，保留必要的 U 本位市场规则查询；策略及模型代码未改动。**

## 1. 根因

### 1.1 请求由 Freqtrade 初始化触发

实际调用链为：

```text
freqtrade backtesting
  → commands.optimize_commands.start_backtesting()
  → Backtesting(config).__init__()
  → ExchangeResolver.load_exchange(..., load_leverage_tiers=True)
  → Binance / Exchange.__init__()
  → reload_markets(True, load_leverage_tiers=False)
  → _load_async_markets() → _api_reload_markets()
  → CCXT async load_markets() → Binance.fetch_markets()
  → GET exchangeInfo
```

这一步先于 `Backtesting.load_bt_data()`，此时还没有开始读取本地回测 K 线，也没有开始 FreqAI 模型训练。

市场信息包含交易对映射、合约大小、价格/数量精度和下单限制。本地 OHLCV 文件并不提供这些规则。当前 Freqtrade 版本仍依赖真实市场信息完成配置校验和后续交易计算。

历史超时的异常链为 `CCXT RequestTimeout → Freqtrade TemporaryError → reload_markets 重试失败`。`reload_markets()` 记录异常后，市场表仍为空，随后 `validate_stakecurrency()` 抛出 `OperationalException: Could not load markets, therefore cannot start`，使回测退出。此前的真实超时退出码为 2，原始日志保存在 [backtest-retry.log](baseline/backtest-retry.log)。

### 1.2 查询范围超过当前回测所需

当前配置为 Binance、`futures`、`isolated`、USDT 结算，白名单全部为 `BASE/USDT:USDT`。但是 CCXT 默认市场加载范围包含 spot、linear、inverse；默认的 `defaultType=swap` 并不等价于只加载线性合约市场。

请求拦截实际记录到：

| 修改前请求 | 当前回测是否需要 |
| --- | --- |
| `GET https://api.binance.com/api/v3/exchangeInfo` | 不需要现货市场信息 |
| `GET https://fapi.binance.com/fapi/v1/exchangeInfo` | 需要 U 本位合约市场信息 |
| `GET https://dapi.binance.com/dapi/v1/exchangeInfo` | 不需要币本位市场信息 |

因此，之前被现货接口超时阻塞确实有可避免的部分。但保留的 `fapi` 请求仍可能因网络故障失败，不能把本次修复称为“原生 Freqtrade 已完全离线”。

## 2. 证据

### 2.1 本地配置和文件

- 原生配置：[config.json](../config.json)，`datadir=/home/wangke/project/FreqtradeStratege/data`、`dataformat_ohlcv=feather`、`timeframe=4h`、`StaticPairList`，实际模型为 `XGBoostRegressorES`。
- 研究配置：[base.yaml](../configs/base.yaml)、[local.yaml](../configs/environment/local.yaml)、[research.yaml](../configs/research.yaml)。local 环境明确映射 BTC/ETH 的本地 Feather 文件，没有交易所数据源配置。
- 配置按多个 `-c` 的顺序合并，后者覆盖前者；`--datadir` 显式指定数据根目录，`--pairs` 将本次回测限制为 BTC/ETH。没有通过 `trade` 命令伪装成历史回测。

实际读取并检查了白名单 72 个交易对的三类文件：

| 文件模式 | 文件数 | 检查结果 |
| --- | --- | --- |
| `data/futures/BASE_USDT_USDT-4h-futures.feather` | 72 | 可读取；字段、UTC、时间顺序、重复时间、价格范围和有限数值检查通过 |
| `data/futures/BASE_USDT_USDT-1h-mark.feather` | 72 | 可读取；OHLCV 字段、时区、时间顺序和重复时间检查通过 |
| `data/futures/BASE_USDT_USDT-1h-funding_rate.feather` | 72 | 可读取；字段、时区、时间顺序和重复时间检查通过；资金费率未按正价格规则校验 |

路径映射示例：`BTC/USDT:USDT → futures/BTC_USDT_USDT-4h-futures.feather`。完整逐文件行数和起止时间见 [network-data-inventory.json](baseline/acceptance/network-data-inventory.json)。文件存在不等于覆盖全部回测日期，详见第 7 节。

### 2.2 独立研究调用链

```text
cli.py / api.py
  → load_config()
  → market_data.loader.load_ohlcv(Path)
  → pandas.read_feather / read_parquet / read_csv
  → build_dataset()
  → TimeSeriesSplitter
  → StandaloneBackend.run_training()
  → 训练折预处理、Ridge / XGBoost、predict、指标及工件
```

[loader.py](../quant/market_data/loader.py) 把路径转换为本地 `Path` 后读取，没有下载或交易所客户端分支。[runner.py](../quant/experiments/runner.py) 只调用这些本地加载器；[trainer.py](../quant/training/trainer.py) 接收已构造的数据集和切分，不访问市场接口。`compare` 读取已保存的 JSON 报告。

在 HTTP、TCP/UDP 和 DNS 的 Python 进程级拦截下，使用真实本地 BTC/ETH 文件运行 `validate`、`dataset-build`、Ridge 三折训练、XGBoost 三折训练和 `compare` 均成功。各报告的 `http_requests=[]`、`socket_events=[]`，也没有导入 `freqtrade` 或 `ccxt`。数据集共 29,706 条样本、26 个研究特征；XGBoost 使用现有研究配置的 500 轮上限及内部早停设置。

证据：[配置检查](baseline/acceptance/network-research-validate.json)、[数据集](baseline/acceptance/network-research-dataset.json)、[Ridge](baseline/acceptance/network-research-ridge.json)、[XGBoost](baseline/acceptance/network-research-xgboost.json)、[模型比较](baseline/acceptance/network-research-compare.json)。

### 2.3 Freqtrade / FreqAI 的本地读取路径

已安装源码中的关键位置：

- [Backtesting.__init__](../../freqtrade/freqtrade/optimize/backtesting.py)：先初始化交易所，再载入策略和回测数据。
- [Exchange](../../freqtrade/freqtrade/exchange/exchange.py)：`__init__`、`reload_markets`、`_api_reload_markets`、`validate_stakecurrency` 构成初始化请求及失败链。
- [CCXT Binance](../../freqtrade/.venv/lib/python3.13/site-packages/ccxt/binance.py)：`fetch_markets` 按 `options.fetchMarkets.types` 分别调用 spot、linear、inverse 的 `exchangeInfo`。
- `Backtesting.load_bt_data → history.load_data → load_pair_history → IDataHandler.ohlcv_load → FeatherDataHandler._load_dataframe → pandas.read_feather`，读取本地 K 线。
- `Backtesting._load_bt_data_detail` 同样从本地加载 mark 和 funding_rate。Binance 的模拟/回测杠杆档位由该版本内置 `binance_leverage_tiers.json` 提供。

仓库 [populate_indicators()](../quant/execution/freqtrade_strategy.py) 调用 [FreqAIBackendAdapter.start()](../quant/backends/freqai.py)，后者只转交 `strategy.freqai.start(dataframe, metadata, strategy)`。

框架根据 **DataProvider.runmode** 分支：历史回测进入 `IFreqaiModel.start_backtesting`；相关币对和其他周期的特征数据由 `DataProvider.get_pair_dataframe → historic_ohlcv → load_pair_history` 从磁盘读取。两个 [自定义模型](../quant/models/freqai/) 的 fit/predict 消费已准备好的特征与标签，没有行情下载代码。

`IStrategy.load_freqAI_model()` 中确实存在 `download_all_data_for_training()`，但仅在 `RunMode.DRY_RUN/LIVE` 下调用；历史回测不调用。`config.json` 中的 `dry_run=true` 不会把 `freqtrade backtesting` 的实际 runmode 变成模拟交易。

修复后的真实回测日志显示，FreqAI 将预热需求增加到 2,290 根 4h K 线，从本地读取 2023-12-16 08:00 UTC 起的数据，以支持 2025-01 的回测。仅允许市场元数据 HTTP 请求时，完整训练、预测和交易回放成功；所有 K 线、标记价格、资金费率等 HTTP 请求均不在允许列表中，实测没有触发。

## 3. 请求分类

| 场景 / 请求 | 本次结论 | 处理 |
| --- | --- | --- |
| 研究数据集、训练、交叉验证、预测评估和比较 | 不需要 Binance | 保持本地加载器；新增断网拦截回归测试 |
| 历史回测 K 线及相关币对历史 | 本次没有下载请求 | 保持本地 `--datadir`，不自动补数据 |
| 历史 mark / funding_rate | 本次全部读本地 | 不用零费率或虚假价格替代缺失文件 |
| 现货和币本位 `exchangeInfo` | 对当前 USDT 合约回测不必要 | 在专用回测配置中排除 |
| U 本位 `fapi exchangeInfo` | 当前框架初始化必要，失败仍会阻塞 | 保留真实响应；当前使用现有 mihomo |
| 显式下载、增量更新 | 需要获取行情 | 使用独立的 `freqtrade download-data` 任务，与本地消费分开 |
| 实盘 / 模拟交易最新行情、订单簿、FreqAI 自动准备训练历史 | 正常联网工作流的一部分 | 原路径保留，不套用诊断拦截器 |
| 实盘账户、仓位和订单接口 | 实盘必要 | 未禁用、未调用，也未以回测成功代替实盘验收 |

## 4. 修复内容与代码差异

本次没有修改研究核心、策略回调、标签、指标、排名、交易参数或 FreqAI 模型实现。

| 文件 | 本次修改 | 作用 |
| --- | --- | --- |
| [configs/backtest-local.json](../configs/backtest-local.json) | 新增一个原生回测覆盖配置 | 仅将 `exchange.ccxt_config.options.fetchMarkets.types` 限制为 `["linear"]` |
| [tools/audit_local_network.py](../tools/audit_local_network.py) | 新增独立诊断工具 | 记录 HTTP 与 socket/DNS；支持全拒绝或仅允许真实市场元数据经本机代理 |
| [tests/integration/test_local_data_network.py](../tests/integration/test_local_data_network.py) | 新增 8 项回归测试 | 验证研究断网、三种本地格式、覆盖配置只改变市场加载范围，以及框架 live/dry-run 下载分支仍保留 |
| 本报告及 [证据目录](baseline/acceptance/) | 保存 JSON、日志和真实回测归档 | 明确每个结论的适用范围及复现方法 |
| [operations.md](operations.md)、[README](../README.md) | 更新运行入口和报告链接 | 明确加载专用回测配置的顺序 |

Freqtrade 会把 `ccxt_config` 合入同步和异步客户端，因此该覆盖对真正执行 `load_markets` 的异步客户端也生效；不需要重复设置两个不同参数。回测覆盖文件不由原配置自动加载，实盘默认配置保持原样。`defaultType`、手续费、杠杆、原生模型参数、volnorm 标签、特征、交易白名单及止盈止损均未改动。

诊断工具只影响其启动的 Python 进程，拒绝启动 `freqtrade trade`，没有修改系统代理、TLS 校验、已安装 Freqtrade/CCXT 或全局网络设置。工具是测试拦截器，不是离线撮合器，也不提供虚构的市场信息。

## 5. 验证结果

| 验证 | 实际结果 |
| --- | --- |
| 修改前现有测试 | 88 passed |
| 新增针对性测试 | 8 passed |
| 修改后完整测试 | **96 passed**，17.99 秒；[JUnit](baseline/acceptance/network-pytest.xml) |
| 静态检查 | Ruff lint 通过；70 个 Python 文件格式检查通过；`git diff --check` 通过 |
| 研究引擎断网拦截 | validate、dataset-build、两个模型三折训练和 compare 全部退出 0，HTTP / socket 事件均为 0 |
| 修复前完整原生回测 | 退出 0；3 个真实 exchangeInfo 请求；13 笔交易 |
| 修复后完整原生回测 | 退出 0；仅 1 个真实 fapi exchangeInfo 请求；13 笔交易 |
| 修复前后交易语义 | 完整交易及订单、signals/rejected/exited、4 个逐窗口预测文件和训练 schema 对照通过，容差 `1e-12` |
| 原生 Freqtrade 完全断网拦截 | **未通过**：在 fapi exchangeInfo 初始化处被拦截，退出 1，没有开始行情回放 |
| 实盘与模拟交易 | 原代码和分支保留，分支测试通过；未启动真实交易会话，未验证账户和订单接口 |

本次原生回测范围为 BTC/ETH，UTC `2025-01-01 → 2025-01-15`。修复前后分别使用全新的 userdir 和 FreqAI 缓存，均使用 `--cache none --export signals`。当前测试只允许三个已列明的市场元数据 URL，其他 requests/aiohttp HTTP 请求会立即报错，外部直连 socket/DNS 也被拒绝；连接现有本机代理不代表历史数据下载被允许。

证据：[修改前请求](baseline/acceptance/network-before.json)、[修改后请求](baseline/acceptance/network-after.json)、[全断网拒绝记录](baseline/acceptance/network-denied.json)、[交易及预测对照](baseline/acceptance/network-regression.json)、[修改前原生归档](baseline/acceptance/network-before.zip)、[修改后原生归档](baseline/acceptance/network-after.zip)。日志为同目录下的 `network-before.log`、`network-after.log`、`network-denied.log`。

[机器可读汇总](baseline/acceptance/network-summary.json) 记录环境、测试结果、配置及证据文件的 SHA-256。

因此应分别表述为：**研究流程断网拦截通过；原生历史回测完全断网未通过；只允许必要元数据时完整回测通过；实盘联网能力的代码路径保留但未执行交易验收。**

当前 joblib/NumPy 组合仍有 187 条依赖库反序列化弃用警告；未升级依赖，测试及工件读取均通过。

## 6. 运行方式

### 6.1 使用本地数据训练、交叉验证和比较

```bash
cd /home/wangke/project/FreqtradeStratege
quant_python=/home/wangke/project/freqtrade/.venv/bin/python
research_output=$(mktemp -d /tmp/quant-local-research.XXXXXX)

PYTHONPATH=. "$quant_python" -m quant.cli validate \
  -c configs/base.yaml -c configs/environment/local.yaml

PYTHONPATH=. "$quant_python" -m quant.cli dataset-build \
  -c configs/base.yaml -c configs/environment/local.yaml

PYTHONPATH=. "$quant_python" -m quant.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  --output "$research_output" --experiment-id ridge

PYTHONPATH=. "$quant_python" -m quant.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  -c configs/estimators/xgboost.yaml \
  --output "$research_output" --experiment-id xgboost

PYTHONPATH=. "$quant_python" -m quant.cli compare \
  "$research_output/ridge" "$research_output/xgboost"
```

`validate` 在当前 CLI 中校验配置，`run` 负责实际按配置进行三折时间验证和预测评估。训练、测试和预处理由研究后端管理，最终 holdout 默认保留。以上研究任务均不需要代理。

需要复核断网训练时，可在同一 shell 执行：

```bash
PYTHONPATH=. "$quant_python" tools/audit_local_network.py \
  --policy deny-all --report "$research_output/offline-audit.json" \
  research run -c configs/base.yaml -c configs/environment/local.yaml \
  --output "$research_output" --experiment-id offline-check
```

### 6.2 使用本地行情进行原生历史回测

```bash
cd /home/wangke/project/FreqtradeStratege
backtest_run=$(mktemp -d /tmp/quant-local-backtest.XXXXXX)
mkdir -p "$backtest_run/results"

/home/wangke/project/freqtrade/.venv/bin/freqtrade backtesting \
  -c "$PWD/config.json" \
  -c "$PWD/configs/backtest-local.json" \
  -c "$PWD/configs/environment/freqtrade-mihomo.json" \
  --userdir "$backtest_run" --datadir "$PWD/data" \
  --strategy-path "$PWD" --freqaimodel-path "$PWD/quant/models/freqai" \
  --strategy MyStrategy --timerange 20250101-20250115 \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --cache none --export signals --backtest-directory "$backtest_run/results"
```

合并顺序是原生交易配置 → 仅回测市场范围覆盖 → 本机代理覆盖 → CLI 参数。最后一层代理使用现有 `http://127.0.0.1:7890`；可直连 Binance 的环境可以去掉代理配置，但保留 `backtest-local.json`。本机 mihomo 须已运行，这些命令不会启停代理或切换全局节点。

需要复核请求范围时，保留完全相同的 `backtesting` 参数，把启动前缀换为：

```bash
PYTHONPATH=. /home/wangke/project/freqtrade/.venv/bin/python \
  tools/audit_local_network.py --policy metadata-only \
  --report /tmp/freqtrade-network-audit.json freqtrade backtesting \
  -c "$PWD/config.json" -c "$PWD/configs/backtest-local.json" \
  -c "$PWD/configs/environment/freqtrade-mihomo.json" \
  --userdir "$backtest_run" --datadir "$PWD/data" \
  --strategy-path "$PWD" --freqaimodel-path "$PWD/quant/models/freqai" \
  --strategy MyStrategy --timerange 20250101-20250115 \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --cache none --export signals --backtest-directory "$backtest_run/results"
```

如果要确认重新训练而非复用 FreqAI 预测缓存，应先重新创建 `backtest_run` 和 results 目录。`--cache none` 禁止的是交易回测结果缓存，不会自动清空 FreqAI 缓存。

行情缺失或需要增量更新时，另行执行显式下载任务；不要在这些本地训练/回测命令前自动追加下载步骤。未提供“全部接口禁用但仍成功运行原生回测”的命令，因为当前版本没有得到这种验证结果。

## 7. 剩余风险与边界

1. **必要的元数据依赖仍存在。** 当前实现未引入自定义元数据快照加载器，也未关闭初始化校验。fapi 不可达且代理失效时，原生回测仍会失败；风险最小的现行方案是保留真实 fapi 查询并使用明确的进程级代理。历史行情存在不能替代市场精度。
2. **72 个文件不等于 72 个交易对历史齐全。** XMR、XRP、XTZ、YFI、ZEC、ZEN、ZIL、ZRX 的 4h 文件在 2025 年就结束；最早为 ZIL 的 2025-09-12 20:00 UTC。RENDER 和 SUN 的数据从 2024 年中才开始，不足以支持 2025-01 前完整的 365 天训练加预热。本次完整回测只验证了 BTC/ETH，没有静默更改其他币对的训练窗口。
3. **不同数据类型结束时间不同。** mark 全部结束于 2026-10-12 18:00 UTC；funding_rate 结束于 2026-10-12 的不同时间；多数 4h K 线则到 2026-10-15。不能只按最新 K 线日期选择合约回测终点，也不能用零资金费率掩盖缺失数据。
4. **当前市场规则与历史市场状态不同。** 现查元数据不能保证重建过去每个时点的精度、下架状态和限制。需要严格历史市场规则复现时，应单独设计真实、有版本的规则快照；本次没有伪造这类数据。
5. **适用交易模式有限。** `["linear"]` 只用于本项目 USDT 线性合约回测；现货、币本位或混合市场任务必须使用相应配置。该覆盖不应直接作为实盘全局配置。
6. **验证方式有明确范围。** 网络拦截覆盖当前 Python 进程的 requests/aiohttp 和 socket 审计事件，不是操作系统级网络命名空间隔离。结论覆盖已检查调用链、库版本、数据和窗口；不宣称任意原生扩展或子进程的网络都被系统防火墙禁止。
7. **实盘需单独验收。** 本次未执行真实账户或下单操作，未将回测成功当成实盘验证。Freqtrade/CCXT 升级后应重新运行网络拦截和交易回归测试。

参考资料：[Freqtrade Backtesting](https://www.freqtrade.io/en/stable/backtesting/)、[FreqAI 运行与历史回测](https://www.freqtrade.io/en/stable/freqai-running/)、[CCXT 文档](https://docs.ccxt.com/)。接口细节及网络次数以本机 Freqtrade 2026.7 / CCXT 4.5.75 源码和本报告附带实测为准。
