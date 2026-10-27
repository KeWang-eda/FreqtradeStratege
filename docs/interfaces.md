# 公共接口与扩展

```python
from quant.api import load_config, run_experiment, load_model

config = load_config(
    ["configs/base.yaml", "configs/environment/local.yaml",
     "configs/experiments/baseline_volnorm.yaml"],
    ["validation.n_splits=3"],
)
output = run_experiment(config, "/tmp/quant-experiments")
```

`build_dataset(frames, config)` 接受 `pair → OHLCV DataFrame`，返回 `Dataset(X, y, metadata, quality)`。X 仅含 `%` 开头的特征，y 为独立标签，metadata 包含 pair、K 线开盘时间、可用时间和标签结束时间。预热或未来标签不完整的行会排除并记录各原因数量；不填零、不使用未来值补齐。

`PredictionRecord` 必须声明预测量纲、标签模式、horizon、模型名/版本、特征版本、信号时间和 ready 状态。`PredictionBatch.to_frame()` 可保存 Parquet。独立后端记录实际使用过的训练/早停验证标签的最晚结束时间；FreqAI 未公开的训练截止时间记为 `None`，不推造时间证明。

`candidates_from_batch(batch, pairs, timestamp)` 检查统一时点及量纲；不完整返回 `None`，完整但没有有效预测返回空 tuple。这两个状态对应“等待”和“没有目标”，交易动作不同。

`portfolio.decide_position_action` 返回类型化 `PositionDecision`。旧 `model.decide_position_action` 仍返回 `(action, reason)`。绝对值相同时保留传入顺序；策略传入白名单顺序。沿用旧代码零预测在排名中归为 short 的边界，但零不会产生入场信号。

`Regressor` 支持 fit/predict/save，`StandaloneRegressor.load()` 检查模型版本和特征列序。整体工件 `load_model(path, config)` 先检查 manifest、配置/标签/特征版本、依赖版本和 checksum，再加载训练好的预处理器。只加载本项目生成并可信的本地 joblib 文件。

`TrainingBackend` 的能力声明不等同于每个估计器都支持所有能力：Ridge 不使用早停；XGBoost 在配置早停时要求内部验证。FreqAI 不接受独立研究的 split/fit/save 请求，只通过真实 `strategy.freqai.start(dataframe, metadata, strategy)` 管理生命周期，并用 `from_frame()` 转为标准预测。

新增模型需更新注册表、配置可接受名称和参数校验，并通过 fit/predict/save/load 契约测试；新增排名需实现 `rank()` 并独立回归。扩展生产特征或标签前必须使用新 schema/version 和新的 `freqai.identifier`，重新运行交易回归。
