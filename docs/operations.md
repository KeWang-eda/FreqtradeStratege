# 使用与验证

沿用当前环境，不升级核心依赖。可使用 `PYTHONPATH=.`；需要安装 CLI 时执行：

先激活已安装 Freqtrade 2026.7 / CCXT 4.5.75 的环境，再设置 `export FREQTRADE_PYTHON="$(command -v python)"`。Freqtrade 命令从项目根目录用 `python -m freqtrade` 启动，这样根目录的 `quant` 包可被模型 resolver 导入。本项目未配置 mypy/pyright，不把“未配置类型检查”当作检查通过。以下命令从项目根运行，原配置的数据路径须与当前本地文件一致。

```bash
"$FREQTRADE_PYTHON" -m pip install -e . --no-deps --no-build-isolation
```

从仓库根目录运行：

```bash
PYTHONPATH=. "$FREQTRADE_PYTHON" -m quant.cli validate \
  -c configs/base.yaml -c configs/environment/local.yaml

PYTHONPATH=. "$FREQTRADE_PYTHON" -m quant.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml -c configs/research.yaml \
  -c configs/experiments/baseline_volnorm.yaml \
  --output /tmp/quant-experiments --experiment-id volnorm-ridge
```

数据路径相对于运行目录解析。文件映射键为 pair，支持 Feather、Parquet 和 CSV。Feather/Parquet 要求时间戳自带时区；CSV 明确按 UTC 解析。不修改输入文件，不静默排序或去重。

XGBoost 配置层使用 `configs/estimators/xgboost.yaml`；同一模型的 params 按键合并，模型名称切换时清除旧模型参数：

```bash
PYTHONPATH=. "$FREQTRADE_PYTHON" -m quant.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  -c configs/estimators/xgboost.yaml \
  --output /tmp/quant-experiments --experiment-id raw-xgboost

PYTHONPATH=. "$FREQTRADE_PYTHON" -m quant.cli compare \
  /tmp/quant-experiments/volnorm-ridge /tmp/quant-experiments/raw-xgboost
```

`dataset-build -c ...` 仅构建并检查数据集，`artifact-check <实验目录>` 检查工件完整性及模型加载，`leakage-check <实验目录>` 重新查看已保存的训练边界报告并校验工件。后者不重新运行整套防泄漏测试，应同时运行 `pytest tests/leakage`。

Freqtrade 入口仍为原来的 MyStrategy，模型仍为 config.json 中的 XGBoostRegressorES。实际回测使用独立 userdir，避免污染当前模型缓存：

```bash
mkdir -p /tmp/quant-freqtrade-check /tmp/quant-freqtrade-results
"$FREQTRADE_PYTHON" -m freqtrade backtesting \
  -c "$PWD/config.json" -c "$PWD/configs/backtest-local.json" \
  -c "$PWD/configs/environment/freqtrade-mihomo.json" \
  --userdir /tmp/quant-freqtrade-check \
  --datadir "$PWD/data" --strategy-path "$PWD" \
  --freqaimodel-path "$PWD/quant/models/freqai" --strategy MyStrategy \
  --timerange 20250101-20250115 --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --cache none --export trades --backtest-directory /tmp/quant-freqtrade-results
```

行情、标记价格和历史资金费率均从 `--datadir` 读取。Freqtrade 2026.7 启动回测仍会通过 CCXT 查询市场规则（如合约精度和下单限制），有本地 K 线并不会跳过这个步骤；Binance 模拟/回测的杠杆档位由该版本内置 JSON 提供。当前机器已运行 mihomo，原生 Freqtrade 覆盖配置 `configs/environment/freqtrade-mihomo.json` 显式将同步/异步请求送到 `http://127.0.0.1:7890`，不修改系统或代理全局设置。无须代理的环境可去掉代理覆盖对应的 `-c`。独立研究 CLI 只读取本地文件，不需要访问 Binance。

`configs/backtest-local.json` 专用于当前 USDT 合约历史回测，将默认的现货/线性/币本位市场查询缩小为线性合约；实测元数据请求从 3 个降为 1 个，行情没有重新下载。代理不需要时，只去掉指向 `freqtrade-mihomo.json` 的 `-c`，保留回测范围覆盖。断网研究、必要元数据限制和完整证据见 [本地数据网络排查报告](local_data_network_audit.md)。

完全断网时，使用 `PYTHONPATH=. python -m quant.execution.offline_backtest backtesting --snapshot SNAPSHOT.json -- ...原生回测参数...`。该独立入口校验真实市场快照后注入原生引擎，缺失或损坏不会回退联网。仅支持指定版本的 Binance USDT isolated 历史回测，显式采集、完整命令及真实断网证据见[完全离线回测报告](offline_backtest_snapshot.md)。实盘/模拟交易不使用此入口。

测试与静态检查：

```bash
"$FREQTRADE_PYTHON" -m pytest -q
"$FREQTRADE_PYTHON" -m ruff check quant tests tools MyStrategy.py verify_no_lookahead.py
"$FREQTRADE_PYTHON" -m ruff format --check quant tests tools MyStrategy.py verify_no_lookahead.py
```

单元、契约、集成、回归、防泄漏、研究 E2E 分目录运行。FreqAI 集成直接调用当前已安装框架的数据厨房、预处理器、BaseRegressionModel.train/predict 及两个自定义模型，不连接交易所。

导出短、长两个交易回测后运行：

```bash
python verify_no_lookahead.py short.zip long.zip --report /tmp/truncation.json
```

脚本会选择真实结果 JSON，检查双向交易差异，忽略区间末端强平的退出时间。0=一致，1=存在差异，2=无效输入。报告只证明指定重叠窗口的交易回归一致，不能代替其他防泄漏测试。

新旧版本使用独立 userdir 并以 `--export signals` 导出后，可用 `PYTHONPATH=. python tools/verify_freqtrade_regression.py OLD_USERDIR NEW_USERDIR --report /tmp/regression.json` 比较完整交易、三类导出信号、逐窗口预测及训练 schema。工具只读取本地生成且可信的 joblib 归档。已执行的两窗口结果及完整复现命令见 [真实回测验收](baseline/acceptance/README.md)。

## 当前离线流程与分阶段复验

最新比较器还要求两侧各有唯一原生 `_config.json`，所有有效配置及模型 metadata 都比较。交易/订单/metadata/配置严格对照；预测、信号、指标维持 `rtol=atol=1e-12`。仅排除实际运行起止时间戳，路径仅验证并规范根前缀；不同训练参数、缺配置或模型文件不能通过。旧版只比较部分字段的报告保留为历史记录。

先做只读覆盖审计，输出到全新目录。全 72 币命令可能返回 1，含义是报告生成成功但存在缺数据或快照范围问题；0 表示请求范围全部具备条件，2 是无法完成审计。不要给返回 1 的全币种报告标“全部可回测”。

```bash
export PYTHONPATH=.
acceptance_run=$(mktemp -d)
"$FREQTRADE_PYTHON" tools/audit_historical_coverage.py \
  --config config.json --timerange 20250101-20250115 \
  --output "$acceptance_run/coverage.json" --markdown "$acceptance_run/coverage.md"

"$FREQTRADE_PYTHON" tools/run_offline_acceptance.py phase4 \
  --coverage "$acceptance_run/coverage.json" --output "$acceptance_run"
"$FREQTRADE_PYTHON" tools/run_offline_acceptance.py phase5 --output "$acceptance_run"
```

Phase 4 会核对 BTC/ETH 范围、原始文件哈希和准入条件，创建空 userdir，使用 `unshare` 网络命名空间、`strace -f` 和 Python 请求拒绝审计。工具/权限不足会明确 BLOCKED，不用 HTTP mock 替代。为与冻结联网参考严格同配置，验收命令也加载同一 mihomo overlay；离线运行不会使用代理，代理服务是否可用不影响离线验收。

上面的 `coverage.json` 与本次回测保存在同一个全新输出目录，须一起留存；重新审计使用另一目录，不能覆盖旧 gate。同一路径的报告重新生成后，旧 summary 的 SHA 不再指向当前字节，不能以“运行过”代替证据。最终补证的示例见[冻结 gate 与三方哈希](acceptance/phase4_revalidation/coverage_provenance.json)。

直接使用本地快照回测，无需代理 overlay：

```bash
offline_run=$(mktemp -d)
mkdir -p "$offline_run/results"
"$FREQTRADE_PYTHON" -m quant.execution.offline_backtest backtesting \
  --snapshot docs/baseline/acceptance/binance-usdt-market-snapshot.json -- \
  -c config.json -c configs/backtest-local.json \
  --userdir "$offline_run" --datadir "$PWD/data" \
  --strategy-path "$PWD" --freqaimodel-path "$PWD/quant/models/freqai" \
  --strategy MyStrategy --timerange 20250101-20250115 \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --cache none --export signals --backtest-directory "$offline_run/results"
```

上面与联网参考的 transport 配置不同，直接拿它做“严格同配置”对照会失败；使用前面的验收 runner 可得到正确对照条件。`--cache none` 不清理 FreqAI 缓存，必须保持全新 userdir。

生产使用的快照默认最长 30 天，过期时显式采集新文件，不覆盖可信旧文件。冻结验收快照保留原采集时间与版本，专用验收 runner 显式放宽年龄仅用于复现旧实验；不能把这个容限作为生产默认或把当前规则解释成过去规则。

```bash
market_snapshot="$acceptance_run/binance-usdt-$(date -u +%Y%m%dT%H%M%SZ).json"
"$FREQTRADE_PYTHON" -m quant.execution.offline_backtest capture \
  --snapshot "$market_snapshot" --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --proxy http://127.0.0.1:7890
```

采集只获取真实市场元数据，直连环境可省略 `--proxy`，不会启动代理、下载行情、关闭 TLS 或访问账户。原子发布拒绝已有目标；若采集崩溃，显式 `.tmp` 不会被读取为最终快照。精度/限额/档位/版本或范围失败需处理实际原因，不能篡改 SHA 或填零。

扩展范围、按阶段的执行证据与未验证项见[最终报告](acceptance/final_report.md)。原报告中的 115/217 项是各时点历史统计，最终全量结果以最终报告及其 JUnit 为准。

最低验收通过后，可显式重做 BTC/ETH/BNB 三周扩展。以下 runner 会采集真实市场快照并运行一次原生联网参考，再在系统网络隔离下从空 userdir 重新训练离线回测；它是需要代理可用的联网验收任务，不是日常离线入口。真实数据仍只读，不下载行情。

```bash
extension_run=$(mktemp -d)
"$FREQTRADE_PYTHON" tools/run_offline_extension.py \
  --minimum-summary docs/acceptance/phase4_summary.json \
  --coverage docs/acceptance/phase3_extension_coverage.json \
  --output "$extension_run"
```

扩展 runner 仅适用于现有固定配置与 `http://127.0.0.1:7890` 验收代理，不是通用下载或全交易所工具。超时、范围或对照失败会保留失败证据并非零退出，不会放宽比较政策或自动复用缓存。详细结果见[扩展报告](acceptance/phase4_extension.md)。
