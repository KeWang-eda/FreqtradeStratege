# FreqtradeStratege

4h 加密货币回归策略及独立研究引擎。按重构设计 v2 分离特征、标签、时间验证、模型训练、预测和仓位决策，保留 Freqtrade/FreqAI 交易入口。

当前实际配置使用 **XGBoostRegressorES**，72 个交易对白名单，最多 1 个持仓，预测跨度 3 根 K 线。默认 volnorm 标签是未来收益率除以当前 ATR(14)/close。每个决策时点只比较同一根 K 线的有效预测，按预测绝对值取第一名，正数做多、负数做空，没有幅度阈值。同分沿用白名单顺序。

目标与当前持仓一致则持有，目标变化则轮换；完整快照没有有效候选则退出，缺少某个币对的快照则等待。保留 2 倍杠杆上限、stoploss=-1、ROI=999、关闭 trailing 的现有规则。

## 目录

- `MyStrategy.py`：原策略名与发现入口；实际回调在 `src/quant_strategy/execution/freqtrade_strategy.py`。
- `feature.py`、`model.py`、`util.py`：旧调用方的兼容导出。
- `src/quant_strategy/`：不依赖 Freqtrade 初始化的研究核心、后端适配和工件管理。
- `freqaimodels/`：保留现有两个 FreqAI 模型及其加载路径。
- `config.json`：原生交易配置；`configs/`：独立研究的分层 YAML 配置。
- `tests/`：单元、契约、集成、回归、防泄漏和研究 E2E 测试。
- `docs/baseline/`：修改前配置、依赖清单和基线状态。

源码目录使用 `market_data/`、`backends/` 和 `configs/estimators/`，避免被原 `.gitignore` 的 `data/`、`models/` 规则忽略。原始行情文件、模型缓存及其他忽略内容未重构。

## 本地运行

沿用当前环境，从仓库根目录运行：

```bash
/home/wangke/project/freqtrade/.venv/bin/python -m pytest -q

PYTHONPATH=src /home/wangke/project/freqtrade/.venv/bin/python -m quant_strategy.cli validate \
  -c configs/base.yaml -c configs/environment/local.yaml

PYTHONPATH=src /home/wangke/project/freqtrade/.venv/bin/python -m quant_strategy.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  -c configs/experiments/baseline_volnorm.yaml \
  --output /tmp/quant-experiments --experiment-id volnorm-ridge
```

独立后端支持 Ridge 和 XGBoost，四种按时间切分、真实标签区间 purge、训练折内预处理及独立的早停验证。最终 holdout 默认保留且不评分，需要显式 `--evaluate-final-holdout` 才评估。每次运行保存配置、Git/源码快照、依赖、输入指纹、模型、逐折预测和审计报告。

研究示例默认仅使用每个交易对自身的 4h 特征；生产 FreqAI 仍保留相关币对与 shifted-candle 自动展开。两者特征 schema 不同，研究指标不能直接作为生产模型替换依据。

## 验证边界与文档

修改前 11 项测试已冻结，原版特征/标签有数值回归样本。分层测试还覆盖 FreqAI 2026.7 的真实 train/predict 接口、跨币种时间一致性、特征因果性、测试集与早停隔离，以及工件加载。

真实 Freqtrade 交易回测尝试受到 Binance 市场信息请求超时阻塞，旧新交易列表及长短窗口截断对照仍待复现；本地研究训练通过不代表交易回测验收完成。

- [架构与目录](docs/architecture.md)
- [接口与扩展](docs/interfaces.md)
- [特征和标签](docs/feature_catalog.md)
- [实验协议和工件](docs/experiment_protocol.md)
- [命令、回测与测试](docs/operations.md)
- [迁移、差异、验收及回滚](docs/migration_plan.md)
- [本次验证结果与待验收项](docs/validation_report.md)

改动生产特征、标签或模型参数后应更换 `freqai.identifier`。本次通过适配保留原生产特征 schema，实际交易/模型配置保持原值。
