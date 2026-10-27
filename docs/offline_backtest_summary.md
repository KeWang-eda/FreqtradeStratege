# 本地数据与完全离线回测：任务总结和使用说明

**这次任务看这一份即可。** 本文集中说明你提出的 Phase 0–6 要求、实际改动、验收结果、日常命令和剩余问题。其他分阶段文档、JSON、日志与归档作为证据附件保存，需要追查某项结果时再打开。

验收日期：2026-10-17；对应代码提交：`0c31df8`。本文整理的是该轮真实执行结果，本次文档整理没有重新训练或重新运行全量测试。

## 1. 你要求解决什么，最后解决到什么程度

任务是：已有本地历史数据时，让研究训练、验证和原生历史回测不再因 Binance 请求超时失败，同时保留策略交易语义和正常联网交易能力。

**结果：Phase 0–6 在明确验收范围内均为 PASS。** 独立研究流程已经断网运行；专用入口已经在操作系统网络隔离下完成真实 Freqtrade/FreqAI 训练、预测、交易模拟和导出，并与对应联网参考严格一致。

已验证范围为 BTC/ETH 两周，以及 BTC/ETH/BNB 三周。全 72 币交易、全历史、真实账户订单和长期 dry-run 尚未验证，不能从当前 PASS 推导这些范围也通过。

本轮保留了策略的开平仓、标签、预测跨度、特征、模型参数、交易对排名、仓位、杠杆、止损和 ROI。216 份本地行情文件没有修改，没有自动下载或补造行情，没有修改虚拟环境中的 Freqtrade/CCXT 源码、全局代理或 TLS 设置。

## 2. 原因和最终方案

超时的请求是 Binance U 本位合约的 `fapi/v1/exchangeInfo`，用于加载市场身份、价格与数量精度、下单限额等规则。**本地 K 线齐全，并不会让原生 Freqtrade 自动跳过市场规则初始化。** 历史 K 线、mark price 和 funding rate 本来就从本地读取，没有重复下载。

原生调用链是：`freqtrade backtesting → Backtesting → Binance/Exchange 初始化 → CCXT load_markets/fetch_markets → exchangeInfo`。

解决方法是新增显式离线入口：校验真实市场元数据快照，通过 `Backtesting(config, exchange=...)` 注入独立适配器，保留原生配置和市场规则校验。快照缺失、损坏、过期、版本或交易对不匹配时明确失败，不自动联网兜底。同步与异步 HTTP 均有拒绝守卫，强制刷新也只读取已校验快照。

| 运行方式 | 数据和市场规则来源 | 是否请求交易所 |
| --- | --- | --- |
| 研究 `validate/dataset-build/run/compare` | 本地行情文件 | 不需要 |
| 专用 `offline_backtest backtesting` | 本地行情 + 有效真实快照 | 不需要 |
| 普通 `freqtrade backtesting` | 本地行情 + 原生市场初始化 | 仍可能请求市场元数据 |
| 普通实盘 / dry-run | 原生交易所客户端 | 保留原有联网行为 |
| 显式 `capture` | 真实公开市场元数据接口 | 需要；不下载 K 线 |

适配器仅支持已验收的 **Freqtrade 2026.7 / CCXT 4.5.75、Binance USDT 永续、isolated、静态交易对**。没有把离线行为全局注入普通回测或交易。

## 3. Phase 0–6 做了哪些事

| 阶段 | 你的要求 | 实际交付与结论 |
| --- | --- | --- |
| Phase 0 | 核对仓库、环境、数据和旧报告 | 起始 `main@5ce05d6` 干净且与远程一致；独立复现 115 项测试；冻结 216 文件和 58 个源码/配置指纹。PASS |
| Phase 1 | 加固快照、适配器和网络边界 | 严格 schema、JSON 类型、原始规则、版本、范围、时效和杠杆验证；原子且拒绝覆盖发布；预检和异常资源释放。PASS |
| Phase 2 | 测试失败路径，防止比较器假通过 | 补齐缺失/篡改快照、模式、刷新、清理负测；比较完整配置、metadata、交易、嵌套订单、信号、预测和指标；故意改值能发现差异。PASS |
| Phase 3 | 判断本地数据真正够不够 | 新增只读覆盖工具；逐币检查文件、时间、缺口、非法值、预热、相关特征和标签边界；输出机器报告与不可用范围。PASS |
| Phase 4 | 完全断网完成原生回测并严格对照 | 空 userdir、禁用结果缓存、真实重新训练；网络命名空间 + strace + Python 审计；两币最低范围和三币扩展均通过。PASS |
| Phase 5 | 研究、离线和普通交易互不污染 | 本地研究完整运行；普通回测仍走原生元数据请求；受控测试确认 LIVE/DRY_RUN 原生客户端与凭证处理保留。PASS |
| Phase 6 | 全量检查、文档和可复现交付 | 最终 298 passed、0 failed、0 skipped；Lint 与 82 文件格式检查通过；保留完整证据并提交 push。PASS |

核心文件职责如下，读代码时按需要定位即可：

| 文件 | 本次修改目的 |
| --- | --- |
| `quant/execution/market_snapshot.py` | 真实快照采集、严格验证、完整性校验、原子发布 |
| `quant/execution/offline_backtest.py` | 专用离线入口、原生引擎注入、模式隔离、传输拒绝、资源清理 |
| `tools/audit_local_network.py` | HTTP、DNS、socket、子进程审计，拒绝事件不能被吞掉后算成功 |
| `tools/verify_freqtrade_regression.py` | 严格比较真实回测工件，并用负向测试证明能发现差异 |
| `tools/audit_historical_coverage.py` | 只读数据质量与覆盖审计 |
| `tools/run_offline_acceptance.py`、`tools/run_offline_extension.py` | 编排空缓存、系统隔离、真实回归和证据发布 |
| `quant/infrastructure/experiment_store.py` | 仅收紧溯源用 Git 子进程，不改研究计算 |

## 4. 实际测试和回归结果

| 项目 | BTC/ETH 最低验收 | BTC/ETH/BNB 扩展验收 |
| --- | ---: | ---: |
| UTC 区间，终点不包含 | 2025-01-01 至 2025-01-15 | 2025-01-01 至 2025-01-22 |
| 联网参考 | 既有真实联网归档 | 本轮新联网训练 |
| 每次离线训练完成数 | 4 | 9 |
| 预测文件数 | 4 | 9 |
| 交易 / 订单，两侧相同 | 13 / 26 | 29 / 58 |
| 总盈亏 USDT，两侧相同 | -7.72891548 | -25.447139770000007 |
| 最终余额 USDT，两侧相同 | 992.27108452 | 974.55286023 |
| 离线 HTTP、DNS、外部 connect/send | 全部 0 | 全部 0 |
| 交易、订单、信号、预测、metadata、配置及指标差异 | 无 | 无 |

原生 metadata 显示 BTC/ETH 每模型 92 列特征，BNB 为 136 列，来自原有相关币特征展开；没有把 92 列硬编码成全币种规则。预测、信号、指标沿用 `rtol=atol=1e-12`；交易、嵌套订单、metadata 和配置精确比较。仅排除实际进程运行起止时间，路径先校验再规范独立运行根目录。

独立研究也在系统隔离中完成了 validate、dataset-build、Ridge/XGBoost 各 3 折训练和 compare：29706 样本、26 个研究特征，每个模型 18934 行预测，外部网络操作为 0。研究 schema 与原生策略不同，未据研究结果替换生产模型。

最终全量为 **298 passed / 0 failed / 0 skipped，50.49 秒**；867 条依赖弃用 warning 保留。项目未配置类型检查，不宣称类型检查通过。操作系统断网使用 `unshare --user --map-root-user --net`，并结合 `strace -f` 与 Python 审计，未用 HTTP mock 替代。

失败尝试没有删除：包括代理采集超时、审计器误判本地通信、数据审计单位错误等，均修复或解释后重验。最终还发现覆盖报告重新生成导致旧输入 SHA 无法直接追溯，因此使用最终报告重新完整跑了最低回测，并冻结输入副本，三方 SHA 一致；没有改旧哈希掩盖问题。

## 5. 数据限制和剩余风险

72 币的 216 份 futures、mark、funding 文件都存在，但“文件存在”不等于“所有区间都可完整回测”。按本轮最低区间及训练预热要求，**56 币原始数据严格就绪**；已完成真实离线交易验收的仍只有上述两币和三币范围。

需要处理的具体问题：

- **16 币 funding 历史付款时刻表待确认**：AXS、BSV、CAKE、ENJ、IOST、KAVA、ONT、RENDER、RLC、SKL、SOL、SUN、TRB、XTZ、ZIL、ZRX。频率变更不直接等于漏数据，不能补零。
- **早期训练数据缺口**：按原生 2290 根 startup/训练预热计算，RENDER 缺 1338 根 4h 行情，SUN 缺 1501 根；不能完整覆盖最低区间所需历史。
- **部分数据提前结束**：8 币在 2025 年中停止覆盖，不能声称可回测到 2026 年。
- **快照有范围和时效**：原最低快照只有 BTC/ETH，扩展快照包括 BNB；其他币需要真实规则快照。默认有效期 30 天。
- **当前规则不等于历史规则**：2026 年采集的精度、限额和杠杆规则不能证明 2025 年当时的真实规则。本轮证明相同规则输入下在线/离线结果一致。
- **未验证范围**：全 72 币交易、其他区间/机器/框架版本、真实账户认证与订单、长期 dry-run。

建议下一步先确认 funding 时刻表和早期行情是否可补齐，再显式采集更广范围的真实市场快照，逐步扩大同配置回归验收。框架升级需重新检查内部钩子并跑完整验收。

## 6. 日常直接怎么运行

以下均从仓库根目录执行。当前机器已有 Freqtrade 虚拟环境在相邻目录；若环境放在别处，将解释器变量改为实际路径，不需要升级依赖。

```bash
export FREQTRADE_PYTHON="$PWD/../freqtrade/.venv/bin/python"
export PYTHONPATH=.
```

### 本地数据集、训练、交叉验证和模型比较

`run` 按配置执行交叉验证和预测评估，以下使用原研究配置的 3 折；不会请求 Binance。每次使用新目录。

```bash
research_run=$(mktemp -d)
"$FREQTRADE_PYTHON" -m quant.cli validate \
  -c configs/base.yaml -c configs/environment/local.yaml
"$FREQTRADE_PYTHON" -m quant.cli dataset-build \
  -c configs/base.yaml -c configs/environment/local.yaml
"$FREQTRADE_PYTHON" -m quant.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  --output "$research_run" --experiment-id ridge
"$FREQTRADE_PYTHON" -m quant.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  -c configs/estimators/xgboost.yaml \
  --output "$research_run" --experiment-id xgboost
"$FREQTRADE_PYTHON" -m quant.cli compare \
  "$research_run/ridge" "$research_run/xgboost"
```

### 使用本地行情和快照进行原生离线回测

这是日常离线入口。命令重新建立空 userdir，避免 FreqAI 缓存污染；`--cache none` 本身不会清除旧模型。快照必须在有效期内，过期应显式重新采集。

```bash
offline_run=$(mktemp -d)
mkdir "$offline_run/results"
"$FREQTRADE_PYTHON" -m quant.execution.offline_backtest backtesting \
  --snapshot docs/baseline/acceptance/binance-usdt-market-snapshot.json -- \
  -c config.json -c configs/backtest-local.json \
  --userdir "$offline_run" --datadir "$PWD/data" \
  --strategy-path "$PWD" --freqaimodel-path "$PWD/quant/models/freqai" \
  --strategy MyStrategy --timerange 20250101-20250115 \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --cache none --export signals --backtest-directory "$offline_run/results"
```

日常离线不需要 mihomo。若要与原联网参考做完整配置严格对照，使用下方验收 runner，它会加载与参考完全相同的配置，包括代理 overlay；离线进程仍不连接代理。

三币三周运行可将上述快照换成 `docs/acceptance/phase4_extension_snapshot.json`，交易对增加 `BNB/USDT:USDT`，区间改为 `20250101-20250122`。同样要求快照有效和空 userdir。

### 明确联网采集新市场快照

只有需要更新规则或增加交易对时执行，采集真实公开元数据，不下载行情。直连环境可去掉 `--proxy`；目标文件不得已存在。

```bash
snapshot_run=$(mktemp -d)
"$FREQTRADE_PYTHON" -m quant.execution.offline_backtest capture \
  --snapshot "$snapshot_run/binance-usdt.json" \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --proxy http://127.0.0.1:7890
```

采集后将离线命令的 `--snapshot` 指向新文件。默认不读取账户或下单接口。

### 重新执行完整测试和系统级离线验收

系统需要安装 strace，且允许 user/network namespace；不支持时应报告 BLOCKED/未验收。使用新的输出目录保存对应覆盖报告，后续不要覆盖它。

```bash
acceptance_run=$(mktemp -d)
"$FREQTRADE_PYTHON" -m pytest -q --junitxml="$acceptance_run/tests.xml"
"$FREQTRADE_PYTHON" tools/audit_historical_coverage.py \
  --config config.json --timerange 20250101-20250115 \
  --output "$acceptance_run/coverage.json" --markdown "$acceptance_run/coverage.md"
# 全币种审计返回 1 表示报告已生成但有范围限制；不是全部可回测。
"$FREQTRADE_PYTHON" tools/run_offline_acceptance.py phase4 \
  --coverage "$acceptance_run/coverage.json" --output "$acceptance_run"
"$FREQTRADE_PYTHON" tools/run_offline_acceptance.py phase5 --output "$acceptance_run"
"$FREQTRADE_PYTHON" -m ruff check quant tests tools \
  MyStrategy.py  verify_no_lookahead.py
"$FREQTRADE_PYTHON" -m ruff format --check quant tests tools \
  MyStrategy.py  verify_no_lookahead.py
```

验收 runner 对冻结实验显式放宽快照年龄，仅用于复现既定输入；生产入口默认仍为 30 天。普通 `freqtrade backtesting`、实盘和 dry-run 继续使用原来的入口与配置。

## 7. 只有需要核验证据时再看附件

本文已经包含任务结论、使用方法和风险，无须按顺序阅读所有阶段文档。下面是查询入口：

| 想核实什么 | 对应附件 |
| --- | --- |
| 每阶段验收表、失败尝试、源码指纹及完整文件清单 | [原始最终验收报告](acceptance/final_report.md) |
| 72 币逐文件覆盖和不可用范围 | [机器覆盖报告](acceptance/phase3_data_coverage.json) |
| 最终最低回测的网络、交易和预测结果 | [最低验收 summary](acceptance/phase4_revalidation/phase4_summary.json) |
| 三币新联网参考与离线严格对照 | [扩展验收 summary](acceptance/phase4_extension_summary.json) |
| 298 项测试是否真实执行及 skip 数量 | [最终 JUnit](acceptance/phase6_pytest.xml) |

这些附件保留作审计记录；后续这项任务的阅读和使用入口统一为本文。
