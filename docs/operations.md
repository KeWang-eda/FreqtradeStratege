# 使用与验证

沿用当前环境，不升级核心依赖。可使用 `PYTHONPATH=src`；需要安装 CLI 时执行：

```bash
/home/wangke/project/freqtrade/.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
```

从仓库根目录运行：

```bash
PYTHONPATH=src /home/wangke/project/freqtrade/.venv/bin/python -m quant_strategy.cli validate \
  -c configs/base.yaml -c configs/environment/local.yaml

PYTHONPATH=src /home/wangke/project/freqtrade/.venv/bin/python -m quant_strategy.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml -c configs/research.yaml \
  -c configs/experiments/baseline_volnorm.yaml \
  --output /tmp/quant-experiments --experiment-id volnorm-ridge
```

数据路径相对于运行目录解析。文件映射键为 pair，支持 Feather、Parquet 和 CSV。Feather/Parquet 要求时间戳自带时区；CSV 明确按 UTC 解析。不修改输入文件，不静默排序或去重。

XGBoost 配置层使用 `configs/estimators/xgboost.yaml`；同一模型的 params 按键合并，模型名称切换时清除旧模型参数：

```bash
PYTHONPATH=src /home/wangke/project/freqtrade/.venv/bin/python -m quant_strategy.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  -c configs/estimators/xgboost.yaml \
  --output /tmp/quant-experiments --experiment-id raw-xgboost

PYTHONPATH=src /home/wangke/project/freqtrade/.venv/bin/python -m quant_strategy.cli compare \
  /tmp/quant-experiments/volnorm-ridge /tmp/quant-experiments/raw-xgboost
```

`dataset-build -c ...` 仅构建并检查数据集，`artifact-check <实验目录>` 检查工件完整性及模型加载，`leakage-check <实验目录>` 重新查看已保存的训练边界报告并校验工件。后者不重新运行整套防泄漏测试，应同时运行 `pytest tests/leakage`。

Freqtrade 入口仍为原来的 MyStrategy，模型仍为 config.json 中的 XGBoostRegressorES。实际回测使用独立 userdir，避免污染当前模型缓存：

```bash
mkdir -p /tmp/quant-freqtrade-check
/home/wangke/project/freqtrade/.venv/bin/freqtrade backtesting \
  -c "$PWD/config.json" -c "$PWD/configs/environment/freqtrade-mihomo.json" \
  --userdir /tmp/quant-freqtrade-check \
  --datadir "$PWD/data" --strategy-path "$PWD" \
  --freqaimodel-path "$PWD/freqaimodels" --strategy MyStrategy \
  --timerange 20250101-20250115 --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --cache none --export trades --backtest-directory /tmp/quant-freqtrade-results
```

行情、标记价格和历史资金费率均从 `--datadir` 读取。Freqtrade 2026.7 启动回测仍会通过 CCXT 查询市场规则（如合约精度和下单限制），有本地 K 线并不会跳过这个步骤；Binance 模拟/回测的杠杆档位由该版本内置 JSON 提供。当前机器已运行 mihomo，原生 Freqtrade 覆盖配置 `configs/environment/freqtrade-mihomo.json` 显式将同步/异步请求送到 `http://127.0.0.1:7890`，不修改系统或代理全局设置。无须代理的环境可去掉第二个 `-c`。独立研究 CLI 只读取本地文件，不需要访问 Binance。

测试与静态检查：

```bash
/home/wangke/project/freqtrade/.venv/bin/python -m pytest -q
/home/wangke/project/freqtrade/.venv/bin/ruff check src tests MyStrategy.py feature.py model.py util.py verify_no_lookahead.py _quant_strategy_bootstrap.py
```

单元、契约、集成、回归、防泄漏、研究 E2E 分目录运行。FreqAI 集成直接调用当前已安装框架的数据厨房、预处理器、BaseRegressionModel.train/predict 及两个自定义模型，不连接交易所。

导出短、长两个交易回测后运行：

```bash
python verify_no_lookahead.py short.zip long.zip --report /tmp/truncation.json
```

脚本会选择真实结果 JSON，检查双向交易差异，忽略区间末端强平的退出时间。0=一致，1=存在差异，2=无效输入。报告只证明指定重叠窗口的交易回归一致，不能代替其他防泄漏测试。
