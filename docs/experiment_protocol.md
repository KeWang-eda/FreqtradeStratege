# 实验协议与工件

在查看测试结果前固定数据、币对、特征 schema、标签、切分和模型参数。默认按每个币对独立训练 Ridge；XGBoost 为可选独立估计器。配置合并顺序由 `-c` 顺序明确给定，后者覆盖前者，最后应用 `--set dotted.key=value`。未知字段、特征、标签、后端、模型和切分方法拒绝运行；环境配置只应设置数据路径，策略语义放 base/experiment 配置。

固定切分使用 `test_size` 指定后段比例。其他方法将 `min_train_size` 后的时间段均分为 n_splits 个连续测试窗口；缺省初始训练时间数为总时间数 // (n_splits + 1)。滚动窗口使用 train_window_size 个全局时间点；扩展及 purged walk-forward 使用累积历史。所有方法都会清除真实标签区间重叠，普通 expanding 不会关闭这层保护。

标签区间端点按闭区间处理：训练标签结束时间 >= 测试最早可用时间即清除。显式 purge_candles 只能增加间隔，必须附 purge_reason。embargo_candles 作用在测试前的最后 N 个全局时间点，与 purge 的重叠只记在 purged 数量里。没有测试之后的样本进入训练。

最终时间段按 final_holdout_fraction 保留，默认不训练评估、不输出这一段的预测指标。开发样本的标签也不能延伸到最终 holdout。`--evaluate-final-holdout` 明确启用最终评估；一旦查看并据此调参，该时段的独立性已经消耗，应重规划最终区间。

XGBoost 早停取外层训练段的末尾 20% 作内部验证，并再次清除训练标签重叠。scaler 仅拟合内部训练段。外层测试标签不参与早停或特征选择；模型工件的训练截止时间包括早停读过的验证标签。

每次实验生成不可覆盖的独立目录：

```text
manifest.json                 # 状态、配置/数据指纹、Git、依赖、种子、输入范围
source.tar.gz                 # 运行时实际源码，包括尚未提交的新包和兼容入口
config.resolved.yaml          # 包括所有 CLI 覆盖值
feature_schema.json
dataset_metadata.parquet      # 全量可训练样本和标签信息区间
development_metadata.parquet  # folds 的开发样本索引空间
folds.json                    # 边界、位置索引、purge/embargo 记录
predictions.parquet           # truth 与 prediction 分列，附 pair/fold/phase
metrics_prediction.json       # 每折整体及逐 pair 的 MAE/RMSE/方向准确率/IC
metrics_backtest.json          # 未执行交易回测时明确 not_run
leakage_report.json            # 本次训练的区间/截止时间审计及适用范围
model/<fold>/<pair-hash>/      # 模型、预处理器、schema、checksum、版本
```

每折指标保留完整分布；多币对整体 IC 只是总体诊断，逐 pair 指标也必须看。`compare` 展示实验数据/配置指纹和各折指标，不自动选择或部署收益最高者。raw 与 volnorm 目标不同，RMSE 量纲也不同，不能直接以其数值大小判优。

FreqAI 的 365 天训练、7 天回测窗口、内部 test_size=0.2 与研究侧切分不是同一个配置。研究特征集合也不等同于生产相关币对/shift 展开后的集合。交易模型比较必须重新接入一致的 Freqtrade 交易成本和市场范围，单独保存回测指标。
