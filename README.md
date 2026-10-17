# FreqtradeStratege

4h 加密货币回归策略及独立研究引擎。按重构设计 v2 分离特征、标签、时间验证、模型训练、预测和仓位决策，保留 Freqtrade/FreqAI 交易入口。

**当前训练可信度准入：FAIL。** 本轮任务只需看[训练可信度治理总报告](docs/training_readiness_summary.md)：398 项测试通过，但原生训练/早停验证存在标签跨界，正式训练被拒绝，Phase 3–5 阻断；生产模型按用户决定保留。

**本地数据 / 离线回测任务只需看这一份：[任务总结与使用说明](docs/offline_backtest_summary.md)。** 包含 Phase 0–6 结论、修改内容、真实测试结果、运行命令和剩余问题；分阶段文档作为证据附件保留。

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

先激活包含 Freqtrade 2026.7 / CCXT 4.5.75 的虚拟环境，设置 `export FREQTRADE_PYTHON="$(command -v python)"`。当前版本约束是离线适配器的兼容边界，不会自动升级依赖。

```bash
"$FREQTRADE_PYTHON" -m pytest -q

PYTHONPATH=src "$FREQTRADE_PYTHON" -m quant_strategy.cli validate \
  -c configs/base.yaml -c configs/environment/local.yaml

PYTHONPATH=src "$FREQTRADE_PYTHON" -m quant_strategy.cli run \
  -c configs/base.yaml -c configs/environment/local.yaml \
  -c configs/experiments/baseline_volnorm.yaml \
  --output /tmp/quant-experiments --experiment-id volnorm-ridge
```

独立后端支持 Ridge 和 XGBoost，四种按时间切分、真实标签区间 purge、训练折内预处理及独立的早停验证。最终 holdout 默认保留且不评分，需要显式 `--evaluate-final-holdout` 才评估。每次运行保存配置、Git/源码快照、依赖、输入指纹、模型、逐折预测和审计报告。

研究示例默认仅使用每个交易对自身的 4h 特征；生产 FreqAI 仍保留相关币对与 shifted-candle 自动展开。两者特征 schema 不同，研究指标不能直接作为生产模型替换依据。

## 验证边界与文档

离线任务的结论、命令及验收范围统一在[任务总结与使用说明](docs/offline_backtest_summary.md)。已有分阶段报告与历史记录保留供追查，不作为必须逐篇阅读的操作步骤。

<details>
<summary>其他架构资料与历史证据（按需展开）</summary>

- [架构与目录](docs/architecture.md)
- [接口与扩展](docs/interfaces.md)
- [特征和标签](docs/feature_catalog.md)
- [实验协议和工件](docs/experiment_protocol.md)
- [命令、回测与测试](docs/operations.md)
- [迁移、差异、验收及回滚](docs/migration_plan.md)
- [本次验证结果与适用范围](docs/validation_report.md)
- [本地历史数据与 Binance 网络请求排查](docs/local_data_network_audit.md)
- [完全离线回测：市场快照、实现和测试证据](docs/offline_backtest_snapshot.md)
- [本轮 Phase 0–6 验收、风险与迁移](docs/acceptance/final_report.md)
- [早期原版 / 重构版真实回测对照](docs/baseline/acceptance/README.md)

</details>

改动生产特征、标签或模型参数后应更换 `freqai.identifier`。本次通过适配保留原生产特征 schema，实际交易/模型配置保持原值。
