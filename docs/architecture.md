# 架构与实现边界

采用设计 v2 的渐进迁移：研究核心位于 `src/quant_strategy/`，Freqtrade 仍管理交易生命周期。根目录 `MyStrategy.py` 保留同名发现入口；`feature.py`、`model.py`、`util.py` 保留兼容导出，不要求一次修改所有调用方。

```text
CLI / Python API → experiments → dataset / validation / training
                                       ↓
market_data → features / labels → preprocessing → backends
                                                   ↓
                                           prediction / artifacts
                                                   ↓
FreqAI.start → Strategy adapter → execution → portfolio → Freqtrade
```

`labels`、`portfolio`、`prediction` 和研究训练链路不导入 `freqtrade.*`。框架导入只在 `execution/freqtrade_strategy.py`，现有自定义 FreqAI 模型仍留在 `freqaimodels/`，保持模型发现和历史 pickle 路径。

原 `.gitignore` 的 `data/`、`models/` 会忽略任意层级同名目录，因此目标设计中的 `data/` 改名 `market_data/`，`models/` 改名 `backends/`，模型配置使用 `configs/estimators/`。未改动 `.gitignore`，也未搬动原始数据和运行缓存。

可替换部分：模型通过 `backends/factory.py` 注册，排名通过 `RankingPolicy` 注入，切分通过 `ValidationConfig.method` 选择，技术特征按配置启用。LightGBM 当前明确拒绝，风险策略只定义接口。

研究后端按交易对独立训练，使用同一套全局时间边界；不会把不同交易对同一时段分到 train/test 两侧。研究特征默认只来自每个交易对的原始 4h K 线，**没有复制 FreqAI 的相关币对和 shifted-candle 自动展开**。因此研究结果与当前生产 FreqAI 模型属于不同的已记录特征 schema，不能直接比较收益或复用模型。

实际核对参考：

- [FreqAI 特征展开](https://www.freqtrade.io/en/stable/freqai-feature-engineering/)：FreqAI 适配器继续交给框架做周期、币对和时间框架展开。
- [scikit-learn 时间序列验证](https://scikit-learn.org/stable/modules/cross_validation.html) 与 [预处理泄漏](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)：研究侧使用训练折内 Pipeline，并额外清除标签重叠区间。
- [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/)：比较了独立跟踪服务的参数、指标和工件接口；当前按设计采用 JSON/Parquet 文件，避免增加服务依赖。

详细验收状态见 [migration_plan.md](migration_plan.md)，不以已实现目录替代交易回测证据。
