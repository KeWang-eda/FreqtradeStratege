# 架构与实现边界

研究核心位于 `quant/`，Freqtrade 仍管理交易生命周期。根目录 `MyStrategy.py` 只保留框架要求的同名发现入口，并继承包内策略适配器。旧根目录 `feature.py`、`model.py`、`util.py` 转发模块已经移除；生产代码和测试统一从 `quant` 包导入。

```text
CLI / Python API → experiments → dataset / validation / training
                                       ↓
market_data → features / labels → preprocessing → backends
                                                   ↓
                                           prediction / artifacts
                                                   ↓
FreqAI.start → Strategy adapter → execution → portfolio → Freqtrade
```

`labels`、`portfolio`、`prediction`、共享估计器工厂和独立研究链路不导入 `freqtrade.*`。FreqAI 依赖集中在 `models/freqai/` 的模型插件与 `backends/freqai.py` 生命周期适配中；Freqtrade 的 `freqaimodel_path` 指向 `quant/models/freqai/`，根目录不再维护 `freqaimodels/`。

`models/estimators.py` 是 Ridge 与 XGBoost 的共享构造入口，供独立训练和 FreqAI 模型复用。`models/factory.py` 负责 standalone 配置和模型 wrapper，`backends/standalone.py`、`backends/freqai.py` 分别适配两种生命周期。算法和模型类归 `models/`，训练生命周期适配归 `backends/`。

`.gitignore` 继续忽略原始行情和运行时模型缓存，并对源码目录 `quant/models/` 添加跟踪例外。没有搬动原始数据或运行缓存。

源码路径迁移会使既有 `configs/contracts/` 研究合同中的文件指纹失效。合同和历史验收工件保留原样；不得通过改写哈希让旧合同重新有效。需要重新建立受控研究时，必须按新代码路径显式冻结新合同，期间正式研究状态保持 `BLOCKED`。

可替换部分：模型通过 `models/factory.py` 构造，排名通过 `RankingPolicy` 注入，切分通过 `ValidationConfig.method` 选择，技术特征按配置启用。LightGBM 当前明确拒绝，风险策略只定义接口。

研究后端按交易对独立训练，使用同一套全局时间边界；不会把不同交易对同一时段分到 train/test 两侧。研究特征默认只来自每个交易对的原始 4h K 线，**没有复制 FreqAI 的相关币对和 shifted-candle 自动展开**。因此研究结果与当前生产 FreqAI 模型属于不同的已记录特征 schema，不能直接比较收益或复用模型。

实际核对参考：

- [FreqAI 特征展开](https://www.freqtrade.io/en/stable/freqai-feature-engineering/)：FreqAI 适配器继续交给框架做周期、币对和时间框架展开。
- [scikit-learn 时间序列验证](https://scikit-learn.org/stable/modules/cross_validation.html) 与 [预处理泄漏](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)：研究侧使用训练折内 Pipeline，并额外清除标签重叠区间。
- [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/)：比较了独立跟踪服务的参数、指标和工件接口；当前按设计采用 JSON/Parquet 文件，避免增加服务依赖。

详细验收状态见 [migration_plan.md](migration_plan.md)，不以已实现目录替代交易回测证据。
