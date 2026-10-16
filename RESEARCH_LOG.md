# 迭代依据台账（RESEARCH_LOG）

每次改动记录：改了什么、依据来源（论文/文档/仓库/博客）、实测数据、结论。
原则：**先有依据再改，改完必须回测，回测结果必须与同窗口基线对照。**

## 2026-10-16 · OOS model candidates (all rejected)

验证口径：24 个固定 pair；2025-09-10 至 2026-10-01；FreqAI 365 天训练窗、7 天滚动重训；`label=volnorm`、`label_period_candles=3`、手续费 0.05%；只比较共同有效预测和冻结交易逻辑下的回测。生产 `config.json` 未改。

依据来源：

1. FreqAI 特征工程与参数表：
   https://www.freqtrade.io/en/stable/freqai-feature-engineering/ 、
   https://www.freqtrade.io/en/stable/freqai-parameter-table/
2. MDPI *Forecasting* 8(3):40：多周期对齐的前视风险与 4h XGBoost 实验，
   https://www.mdpi.com/2571-9394/8/3/40
3. scikit-learn 周期特征示例：
   https://scikit-learn.org/stable/auto_examples/applications/plot_cyclical_feature_engineering.html
4. XGBoost 官方参数文档：`reg:pseudohubererror` 是鲁棒回归损失，
   https://xgboost.readthedocs.io/en/stable/parameter.html

受控结果（均未提交）：

| 候选 | 预测结果（候选 vs 基线） | OOS 策略结果 | 结论 |
|---|---|---|---|
| Bollinger position | MAE `0.84891 -> 0.84842`，方向 `50.24% -> 50.31%` | 收益 `-32.55%`，回撤 `33.50%` | 否决；交易结果恶化 |
| cyclical hour/weekday sin/cos | MAE `0.84891 -> 0.84799`，方向 `50.24% -> 50.68%` | 收益 `-39.02%`，回撤 `40.80%` | 否决；预测略好但 Top-1 交易恶化 |
| 4h+1d+3d + noise 0.05 | MAE `0.84895 -> 0.85287`，方向 `50.24% -> 50.84%` | 收益 `-28.10%`，回撤 `40.33%` | 否决；绝对误差变差 |
| 4h+12h+1d+3d | MAE `0.84895 -> 0.85283`，方向 `50.24% -> 50.27%` | 收益 `-62.28%`，回撤 `62.76%` | 否决；多周期旧窗口收益未外推 |
| XGBoost `reg:pseudohubererror` | MAE `0.84891 -> 0.85896`，方向 `50.24% -> 50.33%` | 收益 `-23.98%`，回撤 `30.66%` | 否决；短窗改善未延续，误差变差 |
| XGBoost `reg:absoluteerror` | MAE `0.84891 -> 0.84691`，方向 `50.24% -> 50.86%` | 收益 `-73.64%`，回撤 `74.02%` | 否决；整体误差略好但 Top-1 选择严重恶化 |
| XGBoost `max_depth=3`（初筛） | 短窗 MAE `0.87566 -> 0.87496`，方向 `50.28% -> 51.04%` | 短窗收益 `-5.47%`，回撤 `18.19%` | 未进入完整 OOS；先保留为未确认候选 |
| XGBoost `min_child_weight=10` | MAE `0.84891 -> 0.84871`，方向 `50.24% -> 50.20%` | 收益 `-45.54%`，回撤 `49.11%` | 否决；短窗改善未外推 |

### 2026-10-16 · XGBoost `max_depth=3` 完整 OOS（否决）

依据：XGBoost 官方参数文档说明，`max_depth` 控制树深度；增大深度会增加模型复杂度和过拟合风险，因此固定其他参数、把基线 `max_depth=5` 降到 `3`，作为降低容量的单变量对照：
https://xgboost.readthedocs.io/en/stable/parameter.html

实验保持 24 个 pair、标签 `volnorm`、365 天训练窗、7 天滚动重训、手续费 0.05% 和冻结交易逻辑不变；只在临时覆盖配置中设置 `max_depth=3`，模型缓存为 `mystrategy-4h-regression-24pair-20261016-depth3-full-v1`。时间外区间为 `2025-09-10` 至 `2026-10-01`。预测质量使用共同有效的 55,479 个 pair/时间点比较，未把交易结果当作预测指标。

完整 OOS 结果：

| 指标 | 基线 `max_depth=5` | 候选 `max_depth=3` | 差异 |
|---|---:|---:|---:|
| MAE | 0.848907 | 0.848232 | -0.000675 |
| RMSE | 1.215420 | 1.214681 | -0.000739 |
| 方向准确率 | 50.244% | 50.470% | +0.225 个百分点 |
| Spearman | -0.010358 | -0.008663 | +0.001695 |
| 有效覆盖率 | 99.94% | 99.94% | 0 |

预测数字有轻微改善，但冻结交易逻辑的完整回测仍为：928 笔交易、收益 `-31.15%`、closed-trades Sharpe `-2.15`、最大回撤 `32.23%`。最大回撤超过本项目 30% 门槛，因此候选否决；不能因为 MAE 和方向准确率略好就进入生产。该结果也说明 pooled 预测指标的微小改善没有转化为可靠的截面 Top-1 选择质量。

结论：`max_depth=3` 不提交代码、不修改生产配置；只保留模型缓存和临时比较结果供复查。

### 2026-10-16 · XGBoost `subsample=0.6` 完整 OOS（否决）

依据：XGBoost 官方参数文档说明，`subsample` 是每棵树随机采样的训练样本比例；设置为小于 `1` 的值可以减少每棵树看到的样本、控制模型复杂度。固定基线 `subsample=0.8`，只改为 `0.6`，作为单变量正则化对照：
https://xgboost.readthedocs.io/en/stable/parameter.html

短筛选先使用相同的 24 个 pair 和 `2025-09-10` 至 `2026-01-01` 窗口。共同有效的 16,192 个预测点上，MAE `0.875661 -> 0.875110`，方向准确率 `50.284% -> 50.945%`，Spearman `0.018190 -> 0.041528`；冻结交易逻辑回测收益 `-5.99% -> +3.25%`，最大回撤 `12.98% -> 10.90%`，因此按预先规则进入完整 OOS。

完整 OOS 保持 24 个 pair、`volnorm` 标签、365 天训练窗、7 天滚动重训、手续费 0.05% 和冻结交易逻辑不变。候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-subsample06-full-v1`，时间外区间为 `2025-09-10` 至 `2026-10-01`。基线使用此前已经封存的完整面板，避免补跑短窗基线时复用 identifier 导致最后一个预测文件被截短；候选与基线在 55,479 个共同有效点上比较。

| 指标 | 基线 `subsample=0.8` | 候选 `subsample=0.6` | 差异 |
|---|---:|---:|---:|
| MAE | 0.848907 | 0.847999 | -0.000908 |
| RMSE | 1.215420 | 1.214090 | -0.001330 |
| 方向准确率 | 50.244% | 50.924% | +0.680 个百分点 |
| Spearman | -0.010358 | 0.009899 | +0.020257 |
| 有效覆盖率 | 99.94% | 99.94% | 0 |

预测指标有改善，但冻结交易逻辑的完整回测为 1,154 笔交易、收益 `-43.10%`、closed-trades Sharpe `-3.22`、最大回撤 `46.71%`。回撤远超 30% 门槛，且交易结果比基线方向明显恶化，因此候选否决。这个对照再次说明，整体 MAE/方向的轻微改善不能单独证明截面 Top-1 选择变好。

结论：`subsample=0.6` 不提交代码、不修改生产配置；只保留完整 OOS 结果用于审查。

### 2026-10-16 · XGBoost `colsample_bytree=0.6` 完整 OOS（否决）

依据：XGBoost 官方参数文档说明，`colsample_bytree` 控制每棵树随机使用的特征比例；设置为小于 `1` 的值可降低每棵树的特征暴露、控制模型复杂度。固定基线 `colsample_bytree=0.8`，只改为 `0.6`，作为单变量正则化对照：
https://xgboost.readthedocs.io/en/stable/parameter.html

短筛选使用相同的 24 个 pair 和 `2025-09-10` 至 `2026-01-01` 窗口。共同有效的 16,192 个预测点上，MAE `0.875661 -> 0.875344`，方向准确率 `50.284% -> 50.513%`，Spearman `0.018190 -> 0.027477`；冻结交易逻辑回测收益 `-5.99% -> -4.74%`，但最大回撤 `12.98% -> 16.76%`。预测面和收益方向均有小幅改善，因此按筛选规则进入完整 OOS。

完整 OOS 保持 24 个 pair、`volnorm` 标签、365 天训练窗、7 天滚动重训、手续费 0.05% 和冻结交易逻辑不变。候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-colsample06-full-v1`，时间外区间为 `2025-09-10` 至 `2026-10-01`。使用此前封存的完整基线面板，避免补跑短窗基线复用 identifier 截短预测文件；共同有效样本为 55,479 点。

| 指标 | 基线 `colsample_bytree=0.8` | 候选 `colsample_bytree=0.6` | 差异 |
|---|---:|---:|---:|
| MAE | 0.848907 | 0.848622 | -0.000285 |
| RMSE | 1.215420 | 1.215226 | -0.000193 |
| 方向准确率 | 50.244% | 50.534% | +0.290 个百分点 |
| Spearman | -0.010358 | -0.002017 | +0.008341 |
| 有效覆盖率 | 99.94% | 99.94% | 0 |

预测指标有轻微改善，但冻结交易逻辑的完整回测为 1,092 笔交易、收益 `-45.67%`、closed-trades Sharpe `-4.23`、最大回撤 `46.27%`。回撤远超 30% 门槛，候选否决；不能因为整体 MAE 和方向略好就进入生产。

结论：`colsample_bytree=0.6` 不提交代码、不修改生产配置；只保留完整 OOS 结果用于审查。

### 2026-10-16 · `label_period_candles=1` 短 OOS（预测层否决）

依据：FreqAI 官方参数表将 `label_period_candles` 定义为“未来多少根 K 线创建标签”；当前生产值为 `3`，本实验只改为 `1`，让模型预测下一根 4h K 线：
https://www.freqtrade.io/en/stable/freqai-parameter-table/

短筛选使用 24 个 pair、`2025-09-10` 至 `2026-01-01`，并用 horizon=1 重新从 OHLCV 计算 `volnorm` 标签。候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-h1-short-v1`。预测层共 16,264 个有效点，覆盖率 99.95%；MAE 为 `0.477537`，反而高于零预测基线 `0.476207`；RMSE `0.732165` 也高于零预测基线 `0.731005`；方向准确率 `50.00%`，Pearson `0.00787`，Spearman `0.01464`。截面 Top-1 的真实标签均值为 `-0.05994`，全池均值为 `-0.03273`，选择增益 `-0.02721`。

冻结交易逻辑下短窗收益为 `-0.50%`、Sharpe `-0.11`、最大回撤 `18.89%`；这点交易结果改善不能抵消预测层失败。候选未进入完整 OOS，避免用交易路径掩盖模型没有超过零预测基线的问题。

结论：`label_period_candles=1` 不提交代码、不修改生产配置；生产 horizon=3 保持不变。

### 2026-10-16 · `label_period_candles=2` 短 OOS（预测层否决）

依据同上：FreqAI 官方参数表定义 `label_period_candles` 为未来标签的 K 线数。本实验只把生产值 `3` 改成 `2`，并用 horizon=2 重新计算 `volnorm` 标签：
https://www.freqtrade.io/en/stable/freqai-parameter-table/

短窗使用 24 个 pair、`2025-09-10` 至 `2026-01-01`，有效预测 16,264 个，覆盖率 99.95%。预测 MAE `0.707170` 高于零预测基线 `0.706293`，RMSE `1.061964` 高于零预测基线 `1.060325`，方向准确率 `50.418%`，Pearson `0.01428`，Spearman `0.03061`。截面 Top-1 的真实标签均值 `-0.10753`，全池均值 `-0.06589`，选择增益 `-0.04164`。

冻结交易逻辑下短窗收益却为 `+17.05%`、Sharpe `5.12`、最大回撤 `9.11%`。这说明收益改善不能替代模型预测证据；因为预测层低于零预测基线，候选未进入完整 OOS，生产 horizon=3 保持不变。

结论：`label_period_candles=2` 不提交代码、不修改生产配置。

### 2026-10-16 · LightGBM 回归架构短 OOS（预测层否决）

依据：FreqAI 支持可配置回归模型，LightGBM 官方参数文档定义了 `objective=regression`、`num_leaves`、`learning_rate` 等回归参数：
https://www.freqtrade.io/en/stable/freqai-parameter-table/  、
https://lightgbm.readthedocs.io/en/latest/Parameters.html

为保持控制变量，使用 24 个 pair、生产 `volnorm` 标签（horizon=3）、相同特征和 `2025-09-10` 至 `2026-01-01` 短窗；只把 `XGBoostRegressorES` 换为 FreqAI 内置 `LightGBMRegressor`，并使用干净的 LightGBM 参数配置。有效预测 16,264 个，覆盖率 99.95%；MAE `1.002960` 高于零预测 `0.872472`，RMSE `1.434321` 高于零预测 `1.309362`，方向准确率 `49.176%`，Pearson `-0.00472`，Spearman `-0.01221`。Top-1 选择增益虽为 `+0.05125`，但不能抵消整体预测误差和方向失败。

冻结交易逻辑下短窗收益 `-30.95%`、Sharpe `-9.49`、最大回撤 `31.57%`，也已超过硬门槛。候选未进入完整 OOS。

结论：LightGBM 架构不提交代码、不修改生产配置；生产继续使用 XGBoostRegressorES。

### 2026-10-16 · 截面方向特征消融短 OOS（预测层否决）

依据：FreqAI 官方特征工程文档要求特征工程保持因果、可复用并受参数控制；MDPI *Forecasting* 8(3):40 也强调特征选择和多周期对齐必须通过样本外检验：
https://www.freqtrade.io/en/stable/freqai-feature-engineering/  、
https://www.mdpi.com/2571-9394/8/3/40

项目自身的截面 IC 取证显示，波动率、ATR、相对成交量、RSI、动量和振幅特征与逐币模型学到的方向多次反号。因此在 `/tmp/feature.py` 做临时消融：保留 EMA/SMA 距离、收益、实体、时间特征，移除上述反号风险特征；仓库 `feature.py` 未修改。候选真实使用 56 个特征（基线 136 个），identifier 为 `mystrategy-4h-regression-24pair-20261016-crosssectional-ablation-short2-v1`。

短窗为 24 个 pair、`2025-09-10` 至 `2026-01-01`。有效预测 16,267 个、覆盖率 99.97%；MAE `0.875275` 高于零预测 `0.872381`，RMSE `1.312531` 高于 `1.309258`，方向准确率 `50.040%`，Pearson `0.00387`，Spearman `0.01718`。Top-1 选择增益为 `+0.02862`，但不能抵消整体误差高于零预测的结果。

冻结交易逻辑下短窗收益 `-1.83%`、Sharpe `-0.41`、最大回撤 `14.30%`。候选未进入完整 OOS；不能仅因 Top-1 增益或交易收益较基线好，就宣称模型预测改善。

结论：该特征消融不提交代码、不修改生产配置；仓库特征仍保持基线。

### 2026-10-16 · MomentumRidgeRegressor 架构短 OOS（预测层否决）

依据：scikit-learn 官方 Ridge 文档说明，Ridge 在平方误差中加入 L2 正则项，可作为低方差回归对照：
https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression

使用项目已有 `MomentumRidgeRegressor`，保持 365 天训练窗、生产 `volnorm` horizon=3、136 个输入特征和相同短窗，只把模型换为 `Ridge(alpha=10)`，每个模型实际选用 36 个 momentum/RSI 特征。24 个 pair、`2025-09-10` 至 `2026-01-01` 的有效预测为 16,264 个，覆盖率 99.95%；MAE `0.884271` 高于零预测 `0.872472`，RMSE `1.316765` 高于 `1.309362`，方向准确率 `50.418%`，Pearson `0.03468`，Spearman `0.01899`。Top-1 方向准确率 `54.867%`，但选择增益为 `-0.00767`。

冻结交易逻辑下短窗收益 `+5.56%`、Sharpe `0.88`、最大回撤 `19.23%`；预测层低于零预测基线，候选未进入完整 OOS。

结论：MomentumRidgeRegressor 不提交代码、不修改生产配置；生产继续使用 XGBoostRegressorES。

### 2026-10-16 · XGBoost DART 架构短 OOS（预测层否决）

依据：XGBoost 官方参数文档支持 `booster=dart`，并定义 `rate_drop`、`skip_drop` 等 dropout 参数；本实验固定生产特征、标签、训练窗和树参数，只把 `gbtree` 改为 DART：
https://xgboost.readthedocs.io/en/stable/parameter.html

短窗使用 24 个 pair、`2025-09-10` 至 `2026-01-01`。有效预测 16,264 个、覆盖率 99.95%；MAE `0.873818` 高于零预测 `0.872472`，RMSE `1.311373` 高于 `1.309362`，方向准确率 `50.406%`，Pearson `0.01790`，Spearman `0.03201`。Top-1 选择增益为 `-0.02640`。

冻结交易逻辑下短窗收益 `+2.73%`、Sharpe `0.58`、最大回撤 `9.72%`，但预测层没有超过零预测基线，候选未进入完整 OOS。

结论：DART 架构不提交代码、不修改生产配置；生产继续使用 XGBoostRegressorES 的 gbtree 配置。

### 2026-10-16 · FreqAI `train_period_days=90` 短 OOS（预测层否决）

依据：FreqAI 官方参数表允许用 `train_period_days` 控制每个滚动模型看到的历史长度；本实验固定 XGBoost、特征、标签和交易逻辑，只把生产的 365 天改为 90 天：
https://www.freqtrade.io/en/stable/freqai-parameter-table/

短窗使用 24 个 pair、`2025-09-10` 至 `2026-01-01`。每个训练窗口约 429 个样本，说明 90 天配置生效。有效预测 16,067 个，覆盖率 `98.74%`；MAE `0.891161` 高于零预测 `0.875905`，RMSE `1.341559` 高于 `1.314275`，方向准确率 `51.957%`，Pearson `-0.00026`，Spearman `0.03789`，Top-1 增益 `-0.00965`。

冻结交易逻辑下短窗收益 `-20.73%`、Sharpe `-5.01`、最大回撤 `25.92%`。虽然回撤未超过 30%，预测误差和覆盖率都恶化，候选未进入完整 OOS。

结论：`train_period_days=90` 不提交代码、不修改生产配置；生产训练窗保持 365 天。

### 2026-10-16 · FreqAI `backtest_period_days=3` 短 OOS（预测层否决）

依据：FreqAI 官方参数表说明 `backtest_period_days` 决定回测中每个训练模型向前推断多少天后再滑动训练窗口并重新训练；本实验只把生产的 7 天重训间隔改为 3 天，其他特征、标签、XGBoost 参数、训练窗、交易池和交易逻辑保持不变：
https://www.freqtrade.io/en/stable/freqai-parameter-table/

短窗使用 24 个 pair、`2025-09-10` 至 `2026-01-01`，候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-retrain3-short-v1`。共 912 个预测文件、16,224 个标签行；有效预测 16,216 个，覆盖率 `99.95%`。独立预测层结果如下：

| 指标 | `backtest_period_days=3` | 零预测基线 | 差异 |
|---|---:|---:|---:|
| MAE | 0.876157 | 0.872862 | +0.003295 |
| RMSE | 1.315247 | 1.310032 | +0.005215 |
| 方向准确率 | 49.932% | 不适用 | - |
| Spearman | 0.015990 | 不适用 | - |
| Top-1 带方向真实标签均值 | -0.16105 | - | - |
| Top-1 选择增益 | -0.15127 | - | - |

冻结交易逻辑下短窗回测为 338 笔交易、收益 `+1.01%`、closed-trades Sharpe `0.21`、最大回撤 `9.78%`。收益和回撤看起来比部分基线窗口好，但模型误差高于零预测，Top-1 选择增益为负，因此不能称为模型提升，也不能进入完整 OOS 或生产配置。

结论：`backtest_period_days=3` 不提交代码、不修改生产配置；生产重训间隔保持 7 天。该实验只说明更频繁重训在这段短窗口里没有带来可复用的预测质量提升。

### 2026-10-16 · `data_split_parameters.test_size=0.1` 短 OOS（否决）

依据：FreqAI 官方参数表允许把 `data_split_parameters` 传给 scikit-learn 的 `train_test_split()`，其中 `test_size` 是测试集比例；本项目继续使用 `shuffle=false`，只把测试比例从生产的 `0.2` 改为 `0.1`：

- https://www.freqtrade.io/en/stable/freqai-parameter-table/
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.train_test_split.html
- FreqAI 源码：`freqtrade/freqai/data_kitchen.py:146-159`、`freqtrade/freqai/base_models/BaseRegressionModel.py:53-79`

控制变量：24 个 pair、`2025-09-10` 至 `2026-01-01`、`label_period_candles=3`、136 个特征、XGBoost、`backtest_period_days=3`、手续费 0.05%、交易逻辑和持仓逻辑全部不变。候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-testsize10-short-v1`。为排除公网 Binance 市场接口故障，回测使用一次性的本地市场元数据服务；价格、OHLCV、标签、FreqAI 和 Freqtrade 回测引擎仍使用项目原路径，服务不提供价格或预测数据。

训练日志也证明切分比例生效：`test_size=0.2` 每窗口训练约 1749 点，`0.1` 每窗口训练约 1968 点。早停结果从基线 `best_iteration` 中位数 0、均值 3.28，变为候选中位数 1、均值 6.74；这改变了每个滚动模型的有效树数和输出排序。

独立预测层（16,216 个共同有效点）：

| 指标 | `test_size=0.2` | `test_size=0.1` | 零预测基线 |
|---|---:|---:|---:|
| MAE | 0.876157 | 0.875550 | 0.872862 |
| RMSE | 1.315246 | 1.315123 | 1.310032 |
| 方向准确率 | 49.932% | 50.493% | 不适用 |
| Spearman | 0.015990 | 0.025978 | 不适用 |
| Top-1 带方向真实标签均值 | -0.16105 | 0.00274 | - |
| Top-1 选择增益 | -0.15127 | 0.00122 | - |
| 两版本 Top-1 pair 重合率 | - | 15.38% | - |

候选冻结交易逻辑回测为 357 笔交易、收益 `-38.08%`、closed-trades Sharpe `-8.94`、最大回撤 `40.30%`；同一本地市场元数据下的 `test_size=0.2` 基线为 338 笔、收益 `+0.96%`、Sharpe `0.19`、最大回撤 `9.86%`。候选回撤超过 30% 门槛，且预测误差仍高于零预测，不能进入完整 OOS 或生产配置。

结论：`test_size=0.1` 不提交代码、不修改生产配置；生产保持 `test_size=0.2`。这个实验说明，缩小测试集虽然让整体误差略降，但会明显改变滚动模型的早停和 Top-1 排序，不能作为模型预测提升。

### 2026-10-16 · 200 根均线趋势距离特征短 OOS（预测层否决）

依据：该候选来自台账中记录的公开 200 日趋势过滤研究和开源加密动量回测：

- tradingstrategies.work, *The 200-Day Line: Beats Buy & Hold on Crypto*: https://tradingstrategies.work/blog/the-200-day-line-tested
- IsaacDodds/crypto-momentum-backtest: https://github.com/IsaacDodds/crypto-momentum-backtest

文献使用 200 日均线；本项目主周期是 4h，因此只在 `/tmp/freqai-regime4-short-strategy/feature.py` 中加入因果特征 `close / SMA(200 根 4h K 线) - 1`（约 33 天），没有修改仓库 `feature.py`、模型代码、交易逻辑或持仓逻辑。FreqAI 实际训练从 136 个特征变为 142 个特征，候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-regime4-short-v1`。

控制变量：24 个 pair、`2025-09-10` 至 `2026-01-01`、365 天训练窗、7 天滚动重训、`label_period_candles=3`、XGBoost、手续费 0.05%。回测只使用本地市场元数据服务绕过公网接口故障，OHLCV 和 Freqtrade/FreqAI 回测仍来自项目原路径。

独立预测层结果：

| 指标 | 基线 | 趋势特征 | 零预测基线 |
|---|---:|---:|---:|
| MAE | 0.875661 | 0.875080 | 0.872803 |
| RMSE | 1.313868 | 1.313640 | 1.309960 |
| 方向准确率 | 50.284% | 50.049% | 不适用 |
| Spearman | 0.018190 | 0.020500 | 不适用 |
| Top-1 带方向真实标签均值 | -0.15830 | -0.04518 | - |
| Top-1 选择增益 | -0.15901 | -0.03077 | - |
| Top-1 pair 重合率 | - | 34.81% | - |

冻结交易逻辑回测：基线 319 笔、收益 `-5.85%`、closed-trades Sharpe `-1.21`、最大回撤 `12.98%`；趋势特征 313 笔、收益 `+0.76%`、Sharpe `0.16`、最大回撤 `15.39%`。虽然 Top-1 负增益明显减小，预测 MAE/RMSE 仍高于零预测，方向准确率还下降，不能称为可复用的模型预测提升。

结论：200 根趋势距离特征不提交代码、不进入完整 OOS、不修改生产配置。Q1 历史窗口中更高的胜率不能外推为时间外预测改善。

### 2026-10-16 · XGBoost 正则化参数短 OOS（`reg_lambda=10`、`gamma=0.1`，均否决）

依据：XGBoost 官方参数文档说明：`reg_lambda` 是 L2 正则项，`gamma` 是继续分裂所需的最小损失下降；两者都可作为控制树模型复杂度的单变量候选：
https://xgboost.readthedocs.io/en/stable/parameter.html

控制变量：24 个 pair、`2025-09-10` 至 `2026-01-01`、136 个基线特征、`volnorm` 标签、`label_period_candles=3`、365 天训练窗、7 天滚动重训、手续费 0.05%、冻结交易和持仓逻辑。每个候选只改变一个 XGBoost 参数；回测使用本地市场元数据服务绕过公网 Binance 接口故障，OHLCV、标签和 FreqAI/Freqtrade 引擎路径不变。

独立预测层（共同有效样本约 16,192 点）：

| 指标 | 基线 | `reg_lambda=10` | `gamma=0.1` | 零预测 |
|---|---:|---:|---:|---:|
| MAE | 0.875661 | 0.874237 | 0.875551 | 0.872862 |
| RMSE | 1.313868 | 1.312104 | 1.313235 | 1.310032 |
| 方向准确率 | 50.284% | 50.093% | 50.654% | 不适用 |
| Spearman | 0.018190 | 0.028062 | 0.025441 | 不适用 |
| Top-1 带方向真实标签均值 | -0.15830 | -0.02504 | -0.04875 | - |
| Top-1 选择增益 | -0.15901 | -0.01501 | -0.05492 | - |

冻结交易逻辑回测：

| 版本 | 交易数 | 收益 | closed-trades Sharpe | 最大回撤 |
|---|---:|---:|---:|---:|
| 基线 | 319 | -5.85% | -1.21 | 12.98% |
| `reg_lambda=10` | 309 | -16.28% | -3.68 | 21.85% |
| `gamma=0.1` | 339 | -9.31% | -1.76 | 13.56% |

两个候选的 MAE/RMSE 都仍高于零预测基线；虽然 `reg_lambda=10` 的 Top-1 负增益比基线小，整体误差和交易结果仍不满足模型提升标准。二者均不进入完整 OOS、不修改生产配置，生产继续使用默认 `reg_lambda` 和 `gamma`。

### 2026-10-16 · XGBoost `max_depth=4` 短 OOS（预测层否决）

依据：XGBoost 官方参数文档定义 `max_depth` 为树的最大深度，并说明更深的树会增加模型复杂度和过拟合风险；此前 `max_depth=3` 的完整 OOS 已因最大回撤超过 30% 被否决。本次测试相邻容量 `max_depth=4`：
https://xgboost.readthedocs.io/en/stable/parameter.html

控制变量：24 个 pair、`2025-09-10` 至 `2026-01-01`、136 个基线特征、`volnorm` 标签、365 天训练窗、7 天滚动重训、手续费 0.05%、冻结交易和持仓逻辑。候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-depth4-short-v1`。

独立预测层结果：

| 指标 | 基线 | `max_depth=4` | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875661 | 0.875445 | 0.872862 |
| RMSE | 1.313868 | 1.313579 | 1.310032 |
| 方向准确率 | 50.284% | 50.148% | 不适用 |
| Spearman | 0.018190 | 0.023869 | 不适用 |
| Top-1 带方向真实标签均值 | -0.15830 | -0.09482 | - |
| Top-1 选择增益 | -0.15901 | -0.08807 | - |

冻结交易逻辑回测：基线 319 笔、收益 `-5.85%`、Sharpe `-1.21`、最大回撤 `12.98%`；候选 287 笔、收益 `-4.57%`、Sharpe `-0.93`、最大回撤 `11.00%`。交易结果虽略有改善，但 MAE/RMSE 仍高于零预测，不能证明模型预测能力提升。

结论：`max_depth=4` 不提交代码、不进入完整 OOS、不修改生产配置；生产保持 `max_depth=5`。

### 2026-10-16 · XGBoost `learning_rate=0.1` 短 OOS（预测层否决）

依据：XGBoost 官方参数文档把 `learning_rate` 定义为每棵树对最终模型的步长；本实验固定所有其他设置，只把生产值 `0.05` 改成 `0.1`：
https://xgboost.readthedocs.io/en/stable/parameter.html

控制变量：24 个 pair、`2025-09-10` 至 `2026-01-01`、136 个基线特征、`volnorm` 标签、`label_period_candles=3`、365 天训练窗、7 天滚动重训、手续费 0.05%、冻结交易和持仓逻辑。候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-lr01-short-v1`。

独立预测层结果：

| 指标 | 基线 | `learning_rate=0.1` | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875661 | 0.877547 | 0.872862 |
| RMSE | 1.313868 | 1.315503 | 1.310032 |
| 方向准确率 | 50.284% | 50.382% | 不适用 |
| Spearman | 0.018190 | 0.025238 | 不适用 |
| Top-1 带方向真实标签均值 | -0.15830 | -0.05586 | - |
| Top-1 选择增益 | -0.15901 | -0.06061 | - |

冻结交易逻辑回测：基线 319 笔、收益 `-5.85%`、Sharpe `-1.21`、最大回撤 `12.98%`；候选 332 笔、收益 `-9.06%`、Sharpe `-1.86`、最大回撤 `14.74%`。方向和 Spearman 的微小变化没有抵消误差、Top-1 和交易结果恶化。

结论：`learning_rate=0.1` 不提交代码、不进入完整 OOS、不修改生产配置；生产保持 `learning_rate=0.05`。

### 2026-10-16 · FreqAI `XGBoostRFRegressor` 短 OOS（架构否决）

依据：FreqAI 自带 `freqtrade/freqai/prediction_models/XGBoostRFRegressor.py` 使用 XGBoost 官方 `XGBRFRegressor` 回归器；XGBoost 官方文档将其定义为随机森林式回归架构。本实验沿用项目 2026-10-14 Q1 实验的参数：`n_estimators=100`、`max_depth=6`、`learning_rate=1.0`、`subsample=1.0`、`colsample_bynode=0.8`、`min_child_weight=1`、`reg_lambda=1.0`、`test_size=0.2`、`shuffle=false`。

来源：

- FreqAI 内置实现：`freqtrade/freqai/prediction_models/XGBoostRFRegressor.py`
- XGBoost 参数文档：https://xgboost.readthedocs.io/en/stable/parameter.html
- XGBoost RF API：https://xgboost.readthedocs.io/en/stable/python/python_api.html#xgboost.XGBRFRegressor

此前 Q1（2025-01 至 2025-04、72 币）回测曾得到收益 `+12.25%`、Sharpe `4.62`、最大回撤 `7.45%`；这次使用 24 币、`2025-09-10` 至 `2026-01-01` 的独立短 OOS，交易逻辑和特征均不变。

独立预测层结果：

| 指标 | RF 候选 | 零预测 |
|---|---:|---:|
| MAE | 0.945222 | 0.872862 |
| RMSE | 1.395211 | 1.310032 |
| 方向准确率 | 50.697% | 不适用 |
| Spearman | 0.018374 | 不适用 |
| Top-1 带方向真实标签均值 | -0.09214 | - |
| Top-1 选择增益 | -0.11182 | - |

冻结交易逻辑回测为 331 笔交易、收益 `-8.84%`、closed-trades Sharpe `-1.95`、最大回撤 `14.25%`。RF 的误差显著高于零预测，Top-1 增益为负；Q1 正收益没有外推到时间外窗口。

结论：`XGBoostRFRegressor` 不提交代码、不进入完整 OOS、不修改生产配置；生产继续使用带测试集早停的 `XGBoostRegressorES`。

结论：旧窗口 `noise/tf124` 的约 `180%` 收益是时期特定或过拟合现象；没有候选同时满足 OOS 预测改善和最大回撤不超过 30%，因此没有代码 commit，也没有修改生产配置。

### 训练集/测试集边界审计（2026-10-16）

依据：FreqAI 官方参数表把 `data_split_parameters` 直接交给 scikit-learn 的 `train_test_split()`，并说明 `test_size` 是测试集比例；本项目配置明确设置 `shuffle=false`：

- https://www.freqtrade.io/en/stable/freqai-parameter-table/
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.train_test_split.html
- 本地 FreqAI 源码：`freqtrade/freqai/data_kitchen.py:146-159`、`freqtrade/freqai/base_models/BaseRegressionModel.py:53-79`

当前行为可以明确分成两点：

1. `shuffle=false` 时，FreqAI 按样本原有时间顺序切出训练集和测试集；没有随机打乱，因此不是“训练集和测试集混在一起”的问题。
2. `BaseRegressionModel.train()` 先用训练部分拟合特征/标签管线，再把同一管线应用到测试部分；这是正确的拟合边界。但这条通用切分没有按 `label_period_candles=3` 自动留出 purge/embargo 间隔，训练集末端标签与测试集起点相邻，仍需用时间外预测审计判断是否过拟合。

因此，训练集分数好、测试集分数差时，不能只看回测收益，也不能说 FreqAI 已经完成了 purge；要同时报告训练/测试误差、滚动 OOS 误差、零预测基线和 Top-1 选择指标。后续 `test_size` 候选只允许使用独立 identifier 和相同 OOS 窗口比较，未通过预测层前不改生产配置。

### 2026-10-16 · XGBoost 训练/测试误差路径诊断（只读，未改代码）

依据：XGBoost 官方参数文档对树深度、抽样和正则化的过拟合风险说明，
https://xgboost.readthedocs.io/en/stable/parameter.html；FreqAI 的训练切分与管线源码见上节。

为了先定位原因，临时复制 `XGBoostRegressorES`，只额外记录每个滚动窗口的训练集和内部测试集 RMSE；模型参数、特征、标签、交易逻辑、24 个 pair、
`2025-09-10` 至 `2026-01-01` 窗口、365 天训练窗和 7 天重训全部不变。临时模型只存在于 `/tmp`，没有修改仓库代码或生产配置。

408 个滚动窗口的结果：

| 观察 | 结果 |
|---|---:|
| 训练误差从最佳轮到停止轮继续下降 | 408/408 |
| 测试误差从最佳轮到停止轮反弹 | 408/408 |
| 最佳树轮数为第 0 轮 | 212/408 |
| 测试 MAE 胜过零预测 | 201/408 |
| 测试 RMSE 胜过零预测 | 188/408 |
| MAE 与 RMSE 都胜过零预测 | 157/408 |

原始标签量纲的中位数为：训练 MAE `0.8498`、测试 MAE `0.8807`、零预测 MAE `0.8832`；训练 RMSE `1.1494`、测试 RMSE `1.2544`、零预测 RMSE `1.2535`。冻结交易逻辑回测仍为收益 `-5.99%`、closed-trades Sharpe `-1.24`、最大回撤 `12.98%`。

结论：模型确实在训练集继续学习时出现过拟合，且测试集整体只与零预测相当，没有稳定可复用的预测信号。这确认了“模型泛化不足/信号弱”是主要问题方向，但不能据此直接修改参数：降低树深度的完整 OOS 已因回撤超过 30% 被否决。下一步应继续拆查标签和特征在训练期与时间外期的分布变化，先做受控诊断，再决定是否修改。

### 2026-10-16 · purge gap 候选（有依据，完整 OOS 否决）

#### 为什么测试

FreqAI 当前把 `data_split_parameters` 直接传给 scikit-learn 的
`train_test_split()`，并没有按 `label_period_candles` 自动留出边界间隔。
当标签使用未来 3 根 K 线时，训练集最后几行的标签窗口会贴着测试集开始位置。
这不是随机打乱问题，但会让边界附近的训练标签和测试区间相邻。候选模型只在训练集末尾去掉
`label_period_candles=3` 行，其他特征、标签、XGBoost 参数、交易逻辑和数据范围保持不变。

依据来源：

- scikit-learn `TimeSeriesSplit(gap)` 官方文档：
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
  （`gap` 定义为每个训练集末尾要排除的样本数。）
- FreqAI 官方参数表：
  https://www.freqtrade.io/en/stable/freqai-parameter-table/
  （`data_split_parameters` 传入数据切分器。）
- 本地 FreqAI 源码 `/home/wangke/project/freqtrade/freqtrade/freqai/data_kitchen.py:146-159`：
  当前直接调用 `train_test_split`。
- 本地 FreqAI 源码 `/home/wangke/project/freqtrade/freqtrade/freqai/base_models/BaseRegressionModel.py:53-79`：
  训练管线先拟合训练集，再转换测试集；没有额外 purge。

实验模型仅存在于 `/tmp/freqai-regime4-short-strategy/PurgedXGBoostRegressorES.py`，没有修改
`feature.py`、`model.py`、`MyStrategy.py`、生产配置或 Freqtrade 框架源码。

#### 短 OOS：先看预测是否改善

固定 24 个币、`2025-09-10` 至 `2026-01-01`、7 天滚动重训。策略逻辑冻结，短 OOS 只用于快速筛选。

| 指标 | 7 天基线 | purge gap |
|---|---:|---:|
| 策略收益 | -5.85% | **+5.94%** |
| Sharpe | -1.21 | **1.14** |
| 最大回撤 | 12.98% | 10.53% |
| 交易数 | — | 305 |
| MAE | 0.875661 | **0.875105** |
| RMSE | 1.313868 | **1.313148** |
| 方向准确率 | — | 50.333% |
| Spearman | 0.018190 | **0.023023** |
| Top-1 选择增益 | -0.15901 | **-0.04223** |

短窗口看起来改善，但绝对误差仍略差于零预测（零预测 MAE 0.872862、RMSE 1.310032）。
因此短 OOS 只能说明候选值得做完整时间外复核，不能证明模型已经变好。

#### 完整 OOS：决定是否保留

固定同一套 24 个币，`2025-09-10` 至 `2026-10-01`，每币 56 个训练窗口，共 1344 个预测文件。
候选 identifier：`mystrategy-4h-regression-24pair-20261016-purged3-full-v1`。

策略回测结果：1127 笔交易，收益 **-25.27%**，Sharpe **-1.89**，最大回撤 **32.92%**。
最大回撤超过本项目 30% 硬门槛，所以候选否决，不进入生产。

完整预测层（有效预测 55,503 条，覆盖率 99.94%）：

| 指标 | 生产基线 | purge gap | 零预测 |
|---|---:|---:|---:|
| MAE | 0.848907 | **0.848751** | 0.844853 |
| RMSE | 1.215420 | **1.215296** | 1.209713 |
| 方向准确率 | — | 50.388% | — |
| Spearman | -0.010358 | **-0.009091** | — |
| Top-1 选择增益 | -0.03792 | **-0.03261** | — |
| Top-1 sign 正确率 | — | 49.611% | — |

在共同有效样本上，MAE 只改善 0.000156，RMSE 平方误差只改善 0.000301，方向准确率提升
约 0.148 个百分点；但两者仍都劣于零预测，Spearman 仍为负，Top-1 选择增益仍为负。
因此 purge gap 缓解了边界泄漏的一个可能来源，却没有解决模型在时间外预测中没有稳定信号的问题。

#### 结论

这次实验支持一个有限结论：当前 FreqAI 的时间切分没有自动 purge，给标签留出 3 根 K 线的间隔在方法上合理，
且短 OOS 的预测指标和 Top-1 指标略有改善。但完整 OOS 才是保留标准；完整 OOS 的收益、Sharpe 和回撤均未达标，
预测误差仍不如零预测，所以不能把 purge gap 说成模型提升，也不能提交到生产代码。

后续所有模型候选继续使用独立时间外窗口、零预测基线和 Top-1 指标；只有在完整 OOS 同时超过零预测并满足回撤门槛时，
才允许提交模型代码。此次提交只记录依据和否决结果。

### 2026-10-16 · FreqAI `weight_factor=0.9` 短 OOS（相对基线改善，但仍否决）

#### 依据与控制变量

FreqAI 官方参数表把 `weight_factor` 定义为“按样本的新旧程度给训练数据加权”，通常使用小于 1 的正数：
https://www.freqtrade.io/en/stable/freqai-parameter-table/

本地 FreqAI 源码 `/home/wangke/project/freqtrade/freqtrade/freqai/data_kitchen.py:141-144` 在该值大于 0
时生成样本权重，`data_kitchen.py:415-418` 的公式为
`exp(-arange(n) / (weight_factor * n))[::-1]`。因此它只改变训练样本权重，不改变特征、标签、预测时间或交易逻辑。

固定 24 个 pair、`2025-09-10` 至 `2026-01-01`、365 天训练窗、7 天滚动重训、136 个特征、
`volnorm` 标签、XGBoost 早停和手续费 0.05%。候选唯一改动是
`feature_parameters.weight_factor=0.9`，identifier 为
`mystrategy-4h-regression-24pair-20261016-weight09-short-v1`。
同一配置另跑无 `weight_factor` 的对照，identifier 为
`mystrategy-4h-regression-24pair-20261016-base-rerun-short-v1`。

#### 独立预测层结果

两个模型均有 16,216 个共同有效预测点、覆盖率 99.95%，没有重复时间戳或冲突预测。

| 指标 | 无权重对照 | `weight_factor=0.9` | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875535 | **0.874842** | 0.872862 |
| RMSE | 1.313380 | **1.313332** | 1.310032 |
| 方向准确率 | 50.296% | **50.500%** | — |
| Spearman | 0.018903 | **0.031318** | — |
| Top-1 选择增益 | -0.158200 | **-0.037816** | — |
| Top-1 sign 正确率 | 47.041% | 49.556% | — |

候选相对无权重对照确实改善了误差、方向、排序和 Top-1 增益，但 MAE/RMSE 仍高于零预测，
Top-1 选择增益仍为负，不能称为独立预测能力达标。

冻结交易逻辑的短窗回测：无权重对照 319 笔、收益 `-5.85%`、Sharpe `-0.67`、回撤 `12.98%`；
候选 308 笔、收益 `-10.07%`、Sharpe `-1.98`、回撤 `11.41%`。交易结果也没有改善，候选不进入完整 OOS。

结论：`weight_factor=0.9` 在当前短窗口相对生产基线有可量化的小幅预测改善，但没有超过零预测，
也没有改善冻结交易结果；不提交代码、不修改生产配置。该结果不能外推为长期有效。

### 2026-10-16 · `label=raw` 短 OOS（预测层否决）

#### 依据与控制变量

FreqAI 官方特征工程文档支持自定义回归标签；项目的 `model.py` 已定义 `raw` 为未来 3 根 4h K 线的
原始收益率，`volnorm` 为同一收益除以 ATR 比率。此前台账的 raw 标签取证显示它可能改善幅度校准，
但也提示按绝对预测择优时可能偏向高波动币。本次在新的短 OOS 上只切换标签量纲，特征、XGBoost、
训练窗、重训频率和交易逻辑全部不变。

候选 identifier：`mystrategy-4h-regression-24pair-20261016-raw-short-v1`。
标签、预测和评估均重新从同一 OHLCV 数据计算，没有复用 `volnorm` 预测缓存。

#### 独立预测层与交易结果

候选有 16,216 个有效预测点、覆盖率 99.95%，没有重复或冲突预测。

| 指标 | `label=raw` | 零预测 |
|---|---:|---:|
| MAE | 0.024722 | 0.024610 |
| RMSE | 0.038776 | 0.038643 |
| 方向准确率 | 49.735% | — |
| Spearman | 0.019758 | — |
| Top-1 选择增益 | -0.001809 | — |
| Top-1 sign 正确率 | 46.598% | — |

冻结交易逻辑短窗回测为 327 笔交易、收益 `-23.96%`、Sharpe `-1.95`、最大回撤 `24.72%`。
候选的 MAE/RMSE 高于零预测，方向低于 50%，Top-1 增益为负，因此即使回撤尚未超过 30% 门槛，
也不能进入完整 OOS。

结论：本窗口的 raw 标签没有改善每币收益预测，也没有改善交易结果；不提交代码、不修改生产配置，
生产继续使用 `label=volnorm`。

### 2026-10-16 · XGBoost `reg:quantileerror` (`alpha=0.5`) 短 OOS（回撤与 Top-1 否决）

#### 依据与可运行性

XGBoost 官方参数文档列出 `reg:quantileerror`，说明它是 pinball/quantile loss，
并由 `quantile_alpha` 指定目标分位数；该目标从 XGBoost 2.0.0 开始提供：
https://xgboost.readthedocs.io/en/stable/parameter.html

当前虚拟环境为 XGBoost `3.4.1`。先用小型回归数据验证了
`XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.5)` 能训练，随后才进入 FreqAI
短 OOS。FreqAI 仍使用项目的 `XGBoostRegressorES`，只在临时配置的
`model_training_parameters` 中加入 `objective=reg:quantileerror`、`quantile_alpha=0.5`，并把
早停监控指标设为官方支持的 `quantile`；没有修改模型源码或框架源码。

控制变量与当前短窗基线完全一致：24 个 pair、`2025-09-10` 至 `2026-01-01`、365 天训练窗、
7 天滚动重训、136 个特征、`volnorm` horizon=3、手续费 0.05% 和冻结交易逻辑。
候选 identifier 为 `mystrategy-4h-regression-24pair-20261016-quantile05-short-v1`。

#### 独立预测层结果

候选有 16,216 个共同有效预测点、覆盖率 99.95%，没有重复或冲突预测。

| 指标 | 无权重 XGBoost 对照 | quantile alpha=0.5 | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875535 | **0.873149** | 0.872862 |
| RMSE | 1.313380 | **1.312137** | 1.310032 |
| 方向准确率 | 50.296% | **51.986%** | — |
| Spearman | 0.018903 | **0.039293** | — |
| Top-1 选择增益 | -0.158200 | -0.125181 | — |
| Top-1 sign 正确率 | 47.041% | 49.556% | — |

候选的 pooled 误差、方向和时序排序相对无权重对照有改善，但 MAE/RMSE 仍略高于零预测，
Top-1 选择增益仍明显为负。这说明分位数损失改善了平均回归拟合，却没有改善策略真正使用的
跨 pair 极值选择。

冻结交易逻辑回测为 267 笔交易、收益 `-29.58%`、Sharpe `-4.18`、最大回撤 `34.39%`，
已超过 30% 硬门槛。候选不进入完整 OOS、不提交代码、不修改生产配置，生产继续使用普通平方误差
XGBoost 回归目标。

### 2026-10-16 · `include_corr_pairlist` BTC/ETH → BTC/ETH/BNB/SOL 短 OOS（否决）

#### 依据与控制变量

FreqAI 官方特征工程文档说明，`include_corr_pairlist` 会把相关交易对的特征加入每个交易对的
特征集合；官方参数表和 `FreqaiExampleHybridStrategy` 都把它作为跨币信息输入方式：

- https://www.freqtrade.io/en/stable/freqai-feature-engineering/
- https://www.freqtrade.io/en/stable/freqai-parameter-table/
- 本地模板 `/home/wangke/project/freqtrade/freqtrade/templates/FreqaiExampleHybridStrategy.py`

当前生产输入只有 BTC、ETH 两个相关币。本实验只扩展为 BTC、ETH、BNB、SOL，其他配置保持不变：
24 个 pair、`2025-09-10` 至 `2026-01-01`、365 天训练窗、7 天滚动重训、136 个基线特征、
`volnorm` horizon=3、XGBoost 早停、手续费 0.05% 和冻结交易逻辑。候选 identifier 为
`mystrategy-4h-regression-24pair-20261016-corr4-short-v1`。训练日志确认相关特征扩展生效，
每个模型的特征数随 pair 可用性为 180 或 224，没有修改仓库特征代码。

#### 独立预测层与交易结果

候选有 16,220 个有效预测点、覆盖率 99.98%，没有重复或冲突预测。

| 指标 | 无权重 BTC/ETH 对照 | corr4 候选 | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875535 | **0.874647** | 0.872765 |
| RMSE | 1.313380 | **1.313247** | 1.309902 |
| 方向准确率 | 50.296% | 49.957% | — |
| Spearman | 0.018903 | 0.020406 | — |
| Top-1 选择增益 | -0.158200 | -0.111531 | — |
| Top-1 sign 正确率 | 47.041% | 51.479% | — |

虽然 MAE、RMSE 和 Top-1 增益相对对照略有改善，误差仍高于零预测，方向准确率低于 50%，
Top-1 增益仍为负。冻结交易逻辑回测为 315 笔交易、收益 `-13.17%`、Sharpe `-1.75`、
最大回撤 `22.74%`，也没有改善对照的 `-5.85%` 收益。

结论：增加相关币特征在短窗口没有产生可独立复用的预测提升；候选不进入完整 OOS、不提交代码、
不修改生产配置，生产继续使用 BTC/ETH 相关特征集合。

### 2026-10-16 · `indicator_periods_candles` 加入 48 根短 OOS（预测层否决）

#### 依据与控制变量

FreqAI 官方特征工程文档允许通过 `indicator_periods_candles` 对同一指标展开多个回看周期：
https://www.freqtrade.io/en/stable/freqai-feature-engineering/

增加较长的因果动量回看也有时间序列动量研究依据：Moskowitz、Ooi、Pedersen 的
*Time Series Momentum* 研究说明，过去收益的趋势信息可以作为预测输入，并在多个回看尺度上检验：
https://www.nber.org/papers/w16019

本实验只把生产 `[6, 14, 24]` 改为 `[6, 14, 24, 48]`（4h 下约 8 天），其他配置保持不变：
24 个 pair、`2025-09-10` 至 `2026-01-01`、365 天训练窗、7 天滚动重训、BTC/ETH 相关特征、
`volnorm` horizon=3、XGBoost 早停、手续费 0.05% 和冻结交易逻辑。候选 identifier 为
`mystrategy-4h-regression-24pair-20261016-period48-short-v1`。
新增特征完全由已收盘数据计算，没有改仓库 `feature.py`。

#### 独立预测层与交易结果

候选有 16,218 个有效预测点、覆盖率 99.96%，没有重复或冲突预测。

| 指标 | 无权重对照 | period 48 候选 | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875535 | 0.876004 | 0.872803 |
| RMSE | 1.313380 | 1.315055 | 1.309960 |
| 方向准确率 | 50.296% | 50.074% | — |
| Spearman | 0.018903 | 0.027964 | — |
| Top-1 选择增益 | -0.158200 | -0.063598 | — |
| Top-1 sign 正确率 | 47.041% | 50.740% | — |

交易层短窗看起来改善：289 笔交易、收益 `+3.60%`、Sharpe `0.51`、最大回撤 `13.15%`；
但模型 MAE/RMSE 比无权重对照更差，也仍高于零预测，Top-1 增益仍为负。这个结果说明长周期
特征改变了交易路径，却没有证明每币收益预测能力提升。

结论：`indicator_periods_candles=48` 不进入完整 OOS、不提交代码、不修改生产配置；生产保持
`[6, 14, 24]`。

### 2026-10-16 · XGBoost 内部验证后 train+validation refit 短 OOS（否决）

#### 依据与实现边界

XGBoost 官方 sklearn 文档说明：早停依赖显式 `eval_set`，预测会使用 `best_iteration`；文档还建议
在验证选择完成后重新训练，并明确提醒不能让测试数据参与模型选择：

- https://xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html
- https://scikit-learn.org/stable/common_pitfalls.html#data-leakage

当前 FreqAI 源码 `/home/wangke/project/freqtrade/freqtrade/freqai/base_models/BaseRegressionModel.py:53-79`
先按时间切出训练/验证，再只把训练段交给模型拟合。临时 `RefitXGBoostRegressorES` 先在这两个内部段上
用验证段选 `best_iteration`，然后用训练+验证共 2,187 行、固定的最佳树数重训；真正 OOS 预测完全没有
参与选树或重训。候选只存在于 `/tmp/freqai-refit-short-strategy/`，没有修改仓库模型代码或框架源码。

控制变量：24 个 pair、`2025-09-10` 至 `2026-01-01`、365 天训练窗、7 天滚动重训、136 个特征、
`volnorm` horizon=3、XGBoost 参数不变、手续费 0.05%、冻结交易逻辑。候选 identifier：
`mystrategy-4h-regression-24pair-20261016-refit-short-v1`。

#### 结果

候选有 16,216 个有效预测点、覆盖率 99.95%，没有重复或冲突预测。

| 指标 | 原 XGBoost | refit 候选 | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875535 | **0.875169** | 0.872862 |
| RMSE | 1.313380 | 1.313829 | 1.310032 |
| 方向准确率 | 50.296% | 50.469% | — |
| Spearman | 0.018903 | 0.018668 | — |
| Top-1 选择增益 | -0.158200 | -0.115160 | — |
| Top-1 sign 正确率 | 47.041% | 47.189% | — |

MAE 只有极小改善，RMSE、Spearman 和 Top-1 仍未超过零预测或原模型。冻结交易逻辑回测为 326 笔、
收益 `-18.37%`、Sharpe `-1.87`、最大回撤 `24.04%`，交易结果也恶化。

结论：把内部验证数据用于最终 refit 没有解决时间外预测问题；候选不进入完整 OOS、不提交代码、
不修改生产配置。

### 2026-10-16 · FreqAI `reverse_train_test_order=true` 短 OOS（预测层否决）

#### 依据与控制变量

FreqAI 官方参数表说明 `reverse_train_test_order` 会把较新的数据段用于训练、较旧的数据段用于
内部测试，并特别提醒这是非传统用法：
https://www.freqtrade.io/en/stable/freqai-parameter-table/

本地源码 `/home/wangke/project/freqtrade/freqtrade/freqai/data_kitchen.py:191-204` 确认该开关只交换
FreqAI 已切好的 train/test 数据；滚动窗口内的所有数据仍早于真正 OOS 时刻，没有读取未来价格。
本实验只打开该开关，其他配置保持 24 个 pair、365 天训练窗、7 天重训、136 特征、`volnorm` horizon=3、
XGBoost 和冻结交易逻辑不变。候选 identifier：
`mystrategy-4h-regression-24pair-20261016-reverse-split-short-v1`。

#### 结果

候选有效预测 16,008 个、覆盖率 98.67%，没有重复或冲突预测。

| 指标 | 正常切分 | reverse 候选 | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875535 | 0.882103 | 0.876532 |
| RMSE | 1.313380 | 1.321821 | 1.315627 |
| 方向准确率 | 50.296% | 51.643% | — |
| Spearman | 0.018903 | -0.002869 | — |
| Top-1 选择增益 | -0.158200 | -0.059353 | — |
| 策略收益 | -5.85% | -9.84% | — |
| 最大回撤 | 12.98% | 14.96% | — |

近期样本训练减少了有效预测覆盖，整体误差和排序恶化；方向准确率的小幅提高没有转化为 Top-1
选择质量或交易收益。候选不进入完整 OOS、不提交代码、不修改生产配置。

### 2026-10-16 · FreqAI 标签 `MinMaxScaler` → `StandardScaler` 短 OOS（等价变换，否决）

#### 依据与控制变量

FreqAI 官方特征工程文档允许通过 `define_label_pipeline()` 自定义标签管线，并直接给出
`SKLearnWrapper(StandardScaler())` 示例：
https://www.freqtrade.io/en/stable/freqai-feature-engineering/

FreqAI 当前源码 `/home/wangke/project/freqtrade/freqtrade/freqai/freqai_interface.py:589-592` 默认使用
`MinMaxScaler(feature_range=(-1, 1))`。本实验只把标签管线替换为 sklearn `StandardScaler`，
特征、XGBoost、标签定义、训练窗、重训频率和交易逻辑均不变。候选 identifier：
`mystrategy-4h-regression-24pair-20261016-standardized-short-v1`。

#### 结果

候选 16,216 个有效预测点、覆盖率 99.95%。与无权重基线相比：

| 指标 | 无权重 XGBoost | StandardScaler 标签 |
|---|---:|---:|
| MAE | 0.8755353312 | 0.8755353316 |
| RMSE | 1.3133801679 | 1.3133801689 |
| 方向准确率 | 50.296% | 50.296% |
| Spearman | 0.018903 | 0.018903 |
| Top-1 选择增益 | -0.158200 | -0.158200 |
| 策略收益 | -5.85% | -5.85% |
| Sharpe | -0.67 | -0.67 |
| 最大回撤 | 12.98% | 12.98% |

结果在数值误差范围内完全相同。原因是 `StandardScaler` 相对 `MinMaxScaler` 是训练集上的线性
缩放；平方误差树的分裂顺序不变，预测再逆缩放后也不变。这不是新的模型信息，也没有解决零预测
基线和 Top-1 失败问题。

结论：标签缩放器替换是等价变换，不提交代码、不进入完整 OOS、不修改生产配置。

### 2026-10-16 · FreqAI 标签 `QuantileTransformer(normal)` 短 OOS（部分 MAE 改善但否决）

#### 依据与控制变量

FreqAI 官方特征工程文档在自定义 `define_label_pipeline()` 示例中直接展示
`SKLearnWrapper(QuantileTransformer(output_distribution='normal'))`：
https://www.freqtrade.io/en/stable/freqai-feature-engineering/

本实验只将默认 `MinMaxScaler(-1,1)` 换成按训练窗口拟合的
`QuantileTransformer(output_distribution='normal', random_state=42)`；特征、XGBoost、标签定义、
训练窗、重训频率和交易逻辑均不变。候选 identifier：
`mystrategy-4h-regression-24pair-20261016-quantile-label-short-v1`。

#### 结果

候选有 16,216 个有效预测点、覆盖率 99.95%，没有重复或冲突预测。

| 指标 | 无权重 XGBoost | QuantileTransformer 标签 | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875535 | **0.872726** | 0.872862 |
| RMSE | 1.313380 | 1.310616 | **1.310032** |
| 方向准确率 | 50.296% | 48.027% | — |
| Spearman | 0.018903 | 0.024734 | — |
| Top-1 选择增益 | -0.158200 | -0.128064 | — |
| Top-1 sign 正确率 | 47.041% | 48.669% | — |

MAE 只有很小改善，RMSE 仍劣于零预测，方向准确率跌破 50%，Top-1 增益仍为负。冻结交易逻辑
回测为 323 笔交易、收益 `-17.69%`、Sharpe `-2.99`、最大回撤 `21.24%`。

结论：非线性标签变换没有带来全面预测提升，候选不进入完整 OOS、不提交代码、不修改生产配置。

### 2026-10-16 · FreqAI `train_period_days=730` 短 OOS（预测层否决）

#### 依据与控制变量

FreqAI 官方参数表将 `train_period_days` 定义为每个滚动模型使用的历史训练天数：
https://www.freqtrade.io/en/stable/freqai-parameter-table/

本实验只把生产的 `365` 改为 `730` 天，特征、标签、XGBoost 参数、7 天重训、24 个 pair、
手续费和交易逻辑全部不变。训练日志确认每个模型约 3,501 个训练样本（原来约 1,749 个）。
候选 identifier：`mystrategy-4h-regression-24pair-20261016-train730-short-v1`。

#### 结果

候选有 16,217 个有效预测点、覆盖率 99.96%，没有重复或冲突预测。

| 指标 | 365 天对照 | 730 天候选 | 零预测 |
|---|---:|---:|---:|
| MAE | 0.875535 | 0.874685 | 0.872820 |
| RMSE | 1.313380 | 1.311925 | 1.309992 |
| 方向准确率 | 50.296% | 48.344% | — |
| Spearman | 0.018903 | 0.000248 | — |
| Top-1 选择增益 | -0.158200 | **+0.012356** | — |
| 策略收益 | -5.85% | -3.18% | — |
| 最大回撤 | 12.98% | 9.96% | — |

更长训练窗让 Top-1 选择增益转正、交易回撤下降，但整体 MAE/RMSE 仍劣于零预测，方向和 Spearman
明显恶化。单个交易层指标改善不能证明每币收益预测能力提升，因此候选不进入完整 OOS、不提交代码、
不修改生产配置。

回测口径：`--fee 0`（隔离信号质量与成本），生产 `config.json` 的 `fee` 保持 `0.0005`。
指标计算：`/home/wangke/project/freqtrade/scripts/calc_metrics.py`。**该脚本有两个坑，必须绕开**：
1. `initial_capital` 默认 100，本项目钱包初值为 1000 → 不显式传入会让收益虚高 10 倍。
2. `FUTURES_DIR` 硬编码指向 freqtrade 仓库的 `user_data/data/...`，**那里的 BTC 1d 只有
   2024-07 起的数据**，导致 2024 全窗口基准被低估一半以上（报 +73.63%，实为 +158.04%）。
   必须把 `cm.FUTURES_DIR` 指到本项目完整数据目录后再算。
   正确用法见下方「基准数据修正」节。

---

## 2026-10-13 · entry_threshold 0.4 → 0.8（唯一经全窗口验证的改善）

### 依据来源

1. **arXiv:1807.03192 — Thresholded ConvNet Ensembles: Neural Networks for Technical Forecasting**
   （https://arxiv.org/pdf/1807.03192）
   - 原文：「considerable gains in forecasting capability are achievable through ensemble
     methods and **confidence thresholds**」
   - 原文：「It is acceptable (and **factoring in friction costs, preferable**) for a model
     to be **sparse in making decisions**, only generating 'high conviction' calls,
     if this results in greater accuracy」
   - 原文：「a significant increase in model prowess can be achieved by **thresholding** the
     softmax output to only consider class assignments with high certainty」
   - 实测数据：保留 top centile 时准确率提升至 54.2% / 54.1% / 55.3%（1/2/3 日模型）
   - 对应本项目：阈值 0.4 → 0.8 把交易数 691 → 145（保留约 21%），
     单笔质量提升（盈亏比 0.993 → 1.186）

2. **MDPI JRFM 19(4):283 — Entropy-Filtered Machine Learning for Risk-Aware Algorithmic Trading**
   （https://www.mdpi.com/1911-8074/19/4/283）
   - 提出「confidence-based rejection / selective prediction」作为提升决策可靠性的手段
     （引 Chow 1970；El-Yaniv & Wiener 2010；Geifman & El-Yaniv 2017）
   - 原文：「high entropy values correspond to uncertain market conditions in which the
     predictive model lacks confidence. **Executing trades under such conditions increases
     exposure to noise and potential losses**」
   - 实测数据（加密货币标的）：基线 ML 夏普 0.92 / 最大回撤 24.5% / 胜率 54.1%
     → 过滤后 夏普 1.21 / 最大回撤 18.2% / 胜率 58.6%
   - 对应本项目：夏普 0.367 → 0.758，最大回撤 -16.21% → -7.44%（方向与幅度一致）

3. **Hudson & Thames ArbitrageLab — Machine Learning Filters**
   （https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/ml_approach/filters.html）
   - 给出「standard (threshold) filter」标准形式：
     `if |ΔS_t| > X then 持仓；if -X < ΔS_t < X then 空仓观望`
   - 原文：「in most cases, the application of a filter **improves the results of the model,
     in terms of the out-of-sample Sharpe ratio**」
   - 对应本项目：`entry_threshold` 正是这个 X；0.4 → 0.8 提高 X 后样本外夏普上升

4. **Nature Scientific Reports s41598-026-63497-w — HybridSwingNet**
   （https://www.nature.com/articles/s41598-026-63497-w）
   - 采用「confidence-calibrated signal execution」
   - 实测数据：方向准确率在 0.75 置信阈值下从 68.7% 提升到 82.9%；
     Conservative profile 夏普 1.2、盈亏比 1.43
   - 原文：「The main contribution ... is to transform **noisy forecasts into selective and
     risk-aware trading actions**」

5. **MLP-Based Confidence Filter for EMA Crossover Signals**（exa.ai 收录）
   - 结论：「ML works primarily as a **risk-reduction tool, reducing drawdown more
     consistently than improving the risk-adjusted returns**」
   - 实测：平均回撤改善 +5.8pp、交易频率下降 42%
   - 对应本项目：回撤 -16.21% → -7.44%（改善 8.8pp），交易数下降 79%

6. **MDPI *Forecasting* 8(3):40 — Multi-Timeframe Feature Engineering for Bitcoin
   Market Prediction**（https://www.mdpi.com/2571-9394/8/3/40）
   —— **最强证据：同为加密货币 + XGBoost，且给出完整阈值扫描表**
   - 该论文 XGBoost 阈值扫描（2025 样本外，SL=1%/TP=2%）：
     ```
     τ=0.5  687 笔  命中 51.82%  单笔均 +0.18%  最大回撤 -62.40%
     τ=0.6  454 笔  命中 58.37%  单笔均 +0.34%  最大回撤 -56.23%
     τ=0.7  329 笔  命中 60.49%  单笔均 +0.42%  最大回撤 -46.78%
     ```
   - **与本项目实测完全同构**（阈值↑ → 交易数↓、命中率↑、单笔收益↑、回撤↓）：
     ```
     t=0.4  691 笔  最大回撤 -16.21%  夏普 0.367
     t=0.8  145 笔  最大回撤  -7.44%  夏普 0.758
     ```
   - 另一条关键警告（对本项目后续多周期实验有直接约束）：
     「A subtle **multi-timeframe look-ahead bias in higher-timeframe data alignment**
     is identified and corrected, which inflated performance by approximately
     **0.20 ROC-AUC points** before correction.」
     → 做 `include_timeframes` 多周期实验时必须核验高周期对齐是否引入前视
   - 特征重要性结论：「**4-hour Bollinger Band position and RSI** as dominant
     predictors」→ 可作为候选特征（BB 位置 = 价格对均线的 z 分数），
     本项目当前只有 RSI，无 BB 位置
   - 该论文总体结论（对本项目的期望管理）：
     「models with ROC-AUC ≈ 0.60 **cannot reliably generate economically significant
     returns once transaction costs are accounted for**」

### 改动

`config.json` → `my_experiment.entry_threshold`: `0.4` → `0.8`

### 实测（全窗口 2024-01 ~ 2025-09，一次连续回测，BTC 基准 +73.63%）

| 指标 | t=0.4（原） | t=0.6 | t=0.8（改） | t=1.2 |
|---|---|---|---|---|
| 策略收益 | +7.62% | +6.69% | **+9.47%** | +6.05% |
| 策略年化收益 | 4.50% | 3.96% | **5.57%** | 3.58% |
| 最大回撤 | -16.21% | -8.07% | **-7.44%** | -2.30% |
| 夏普比率 | 0.367 | 0.424 | **0.758** | 0.776 |
| 索提诺比率 | 0.420 | 0.352 | **0.567** | 0.479 |
| 盈亏比 | 0.993 | 1.074 | **1.186** | 1.278 |
| 交易数 | 691 | 332 | **145** | 43 |
| 前 3 pair 集中度 | 307.3% | 223.8% | **93.8%** | 137.2% |
| 盈利月 | 11/20 | 11/20 | **13/20** | 9/17 |

### 受控性验证

阈值不参与训练，两个 identifier 的模型预测应完全相同。实测：

```
base-full (t=0.4) vs s1-t08 (t=0.8)
公共 3654×72，共同有效 260050 个点
最大绝对差 = 0.00e+00    相关系数 = 1.000000
```

→ 收益/回撤差异 **100% 归因于阈值本身**，无模型差异干扰。

### 机制

高阈值成批去掉「小额、低信心」交易：

```
t=0.4 (691 笔) 最差 pair: 1INCH -63(9笔)  HBAR -62(14笔)  VET -37(11笔)  COMP -36(10笔)
t=0.8 (145 笔) 最差 pair: ATOM -23(4笔)   BCH -21(14笔)   QNT -19(2笔)

被过滤最多: TRB 18→3笔(-30.1→+2.2)  ENS 17→0笔(-18.3→0)  XMR 24→7笔(-1.4→+6.9)
代价:       CAKE 21→2笔(+108.6→+25.6)
```

### 保留意见

- 阈值曲线**非单调**（0.4→+7.62%、0.6→+6.69%、0.8→+9.47%、1.2→+6.05%），
  0.8 的峰值可能含噪声成分；0.6 反而低于 0.4，说明「越高越好」不成立。
- **待验证**：2023 全年（此前从未用于任何实验的纯样本外期）上 0.8 是否仍优于 0.4。
  该验证已在队列中（`t08-2023` / `base-2023`）。若 2023 上 0.8 不优于 0.4，
  应立即回退本改动并在台账中记录反例。
- 所有配置仍远跑输 BTC 买入持有（+73.63%）；策略定位是**低回撤、近市场中性**，
  不是跑赢基准的 alpha。

### 提交状态

- `config.json` → `my_experiment.entry_threshold` 已改为 `0.8`，随本台账一并提交。
- identifier 保持 `mystrategy-4h-regression-72pair-corr-s1-v1` 不变：阈值不参与训练，
  实测预测完全一致（最大绝对差 0.00e+00），改 identifier 只会强制无意义的重训。

---

## 2026-10-12 · include_corr_pairlist + include_shifted_candles（已提交 e66a2e2）

### 依据来源

1. **FreqAI 官方参数表**（https://docs.freqtrade.io/en/stable/freqai-parameter-table/）
   - `include_corr_pairlist`：把相关币的指标作为额外特征加入所有白名单币
   - `include_shifted_candles`：把前 N 根 K 线的特征复制到后续 K 线
   - 官方模板 `FreqaiExampleHybridStrategy.py` 用 `include_corr_pairlist: [BTC, ETH]`、
     `include_shifted_candles: 2`

2. **FreqAI 特征工程文档**（https://www.freqtrade.io/en/stable/freqai-feature-engineering/）
   - 特征总数 = `include_timeframes × 特征数 × include_corr_pairlist ×
     include_shifted_candles × indicator_periods_candles`
   - 用于控制特征规模

### 改动

- `include_corr_pairlist`: `[]` → `["BTC/USDT:USDT", "ETH/USDT:USDT"]`（70 → 202 特征）
- `include_shifted_candles`: `2` → `1`（202 → 136 特征）

### 实测

Q1（2025-01~03）分段：t 值 1.95 → 2.53（首次 t > 2）。
**但全窗口复核后，该结论只在 Q1 成立，全窗口未复现**——见下方「方法教训」。

---

## 方法教训（同等重要，均为实测）

### 1. 分段回测不可组合，必须跑连续全窗口

```
分段相加: 2024 -11.94% + Q1 +19.09% + OOS +17.42%  → 复利约 +23.1%
连续一次: 2024-01~2025-09                         → 只有   +7.62%
```

2024 段两边一致（-118 vs -119.6），但 2025 段差异巨大（Q1 独立 +190.8 vs 连续内 +51）。
原因：FreqAI 滚动重训锚点随**回测起点**变化 → 不同模型 → 不同交易路径。

### 2. 离线代理不能用于选配置

「每时间根取 abs-max 选中的 pair、算其固定 N 根未来收益」的代理与真实回测会符号相反：

```
2024 全年     代理：corr 优于 nocorr  →  真实：corr -11.94% vs nocorr -1.52%
Q1 排序键     代理：除vol 更好        →  真实：不除vol +213 vs 除vol +191
shifted=2     代理：与基线相同        →  真实：+9.30 vs +190.85（差 20 倍）
```

机制：代理假设每根 K 线都开 top-1，而策略是**单仓轮动**——只在空仓时开仓、
由阈值穿越触发，实际成交是稀疏子集。**代理只能用于定位机制，不能用于选配置。**

### 3. 集中度必须检查

```
基线 t=0.4 前 3 pair 占比 307%   → 单一 pair 盈亏超过总收益，基线本身不可靠
s1-btc     前 3 pair 占比 181%   → 主导项是亏损（XLM -103）
t=0.8      前 3 pair 占比  94%   → 唯一可接受
```

报告任何正收益前，必须给出 (a) 前 3 pair 占比、(b) 逐月拆分、(c) 多空方向拆分。

### 4. 模型容量的决定性诊断：`best_iteration`

从 6198 个子模型日志统计：`best_iteration ≤ 2` 占比 **51.4%**（p50=2）。
**一半的 pair 上验证集最优就是第一棵树** → 容量不是瓶颈，加树/调学习率/PCA/noise 无效。

### 5. 已实测否决的配置（勿重试）

| 配置 | 改动 | 实测结果 |
|---|---|---|
| `use_SVM_to_remove_outliers` | false → true | Q1 +58.85 vs 基线 +190.85 |
| `include_shifted_candles` | 1 → 2 | Q1 +9.30 vs 基线 +190.85 |
| `label_period_candles` | 3 → 6 | Q1 +68.64 vs 基线 +190.85 |
| `label_period_candles` | 3 → 12 | Q1 +139.87 vs 基线 +190.85 |
| `train_period_days` | 365 → 60 | Q1 +104.08 vs 基线 +190.85 |
| `weight_factor` | 0.9 / 0.5 | Q1 +105.16 / +117.57 vs +190.85 |
| `DI_threshold` | 2.0 → 20 | 死开关：2.0 已保留 100% 预测 |
| 排序键去掉波动率归一 | — | 全窗口打平（+7.49% vs +7.62%） |
| 特征数 136 → 337 | — | 离线代理说崩，但尾部准确率实为 68%（代理误导） |

### 6. 框架约束

`include_timeframes` 只能加**更大**的周期（`config_validation.py:345-355`）：
4h 主周期加 1h 会直接报错，只能加 1d。

---

## 2026-10-13 · MAX 效应因子检验（有依据但幅度不足，未采纳）

### 依据来源

1. **Bali, Cakici & Whitelaw (2011) "Maxing out: Stocks as lotteries and the
   cross-section of expected returns"**, *Journal of Financial Economics* 99(2):427-446
   （NBER WP 14804，https://www.nber.org/papers/w14804）
   - 原文：「a **negative and significant relation between the maximum daily return
     over the past one month (MAX) and expected stock returns**」
   - 原文：「Average raw and risk-adjusted return differences between stocks in the
     lowest and highest MAX deciles **exceed 1% per month**」
   - 原文：「extreme daily returns on the lottery-like stocks are offset to some extent
     by lower returns on other days」
   - 机制：投资者对「彩票型」收益的偏好导致高 MAX 股票被高估、未来收益偏低

2. **Zhao, Wang & Liu (2024) "Someone like you: Lottery-like preference and the
   cross-section of expected returns in the cryptocurrency market"**,
   *Journal of International Financial Markets, Institutions and Money* 91
   - 加密货币市场的同款彩票偏好 / MAX 效应（直接对应本项目标的）

### 本项目的动机

实测发现该池的**尾部结构是反转**：多个幅度类信号（动量/波动/振幅）在 abs-max
口径下两年尾部方向准确率都 < 50%（44.5%~48.0%），即「|信号| 最大的那个 pair，
其符号比随机更容易错」。MAX 效应正是这一现象的理论机制，故做因子检验。

### 实测（标准截面因子测试：每时间戳按因子排序分 5 档，比较等权未来收益）

```
回看 14 根  MAX Q1-Q5 = -0.074%(2024)  -0.023%(2025)   ← 符号与文献一致
回看 24 根  MAX Q1-Q5 = -0.082%(2024)  -0.057%(2025)   ← 符号一致
回看 42 根  MAX Q1-Q5 = -0.054%(2024)  +0.000%(2025)   ← 不稳定
回看  6 根  MAX Q1-Q5 = -0.003%(2024)  +0.013%(2025)   ← 可忽略
MIN(短期输家) 2024 为正(+0.018~+0.063%)、2025 为负     ← 两年符号相反
```

### 结论：未采纳

- MAX 效应在本池**方向与文献一致**（高 MAX → 未来收益偏低），且 14/24 根回看下
  两年符号稳定。
- 但幅度仅 **-0.05% ~ -0.08%**（3 根 K 线 = 12h 的十分位价差），
  远低于成本线 0.10%，**单独不可交易**。
- MIN 效应两年符号相反，无稳定结构。
- 因此**不新增 MAX/MIN 因子、不改配置**。记录在此以免重复尝试。

### 附带价值

本检验给出了「尾部准确率 < 50%」这一现象的理论解释（MAX 效应），
并确认该效应的规模在本池不足以覆盖交易成本。

---

## 2026-10-13 · 趋势状态特征（有依据，实验已排队）

### 依据来源

1. **tradingstrategies.work "The 200-Day Line: Beats Buy & Hold on Crypto,
   Sleep-Well on Index ETFs"**（https://tradingstrategies.work/blog/the-200-day-line-tested）
   - 110 个资产实测。原文：「on crypto it **beats Buy & Hold on return AND drawdown
     AND Sharpe**」
   - 原文：「On average the strategy sits **8.2 percentage points of CAGR above
     Buy & Hold** — and not by taking on more risk, but *with a shallower drawdown
     and a higher Sharpe at the same time*.」
   - 原文：「In **58% of the coins** tested it beats B&H on raw return too.」
   - 机制：「crypto bear markets are brutal and drawn-out (−70% to −90% is normal).
     Standing in cash through those phases avoids most of the damage」

2. **GitHub IsaacDodds/crypto-momentum-backtest**
   （https://github.com/IsaacDodds/crypto-momentum-backtest）
   - v2（加 BTC 200 日趋势过滤）对照 v1（naive 动量）：
     ```
     指标            v1 naive   v2 +BTC200d 过滤
     年化收益          -7.7%      +10.8%
     最大回撤         -89.8%      -53.8%
     夏普(rf=4%)      -0.16       +0.14
     ```
   - 原文：「The regime filter cuts drawdown roughly in half.」
   - 同时给出诚实结论：该样本上动量仍跑输等权买入持有（年化 35.6%、夏普 0.42）

3. **tradingstrategies.work "Wuguan Master Crypto"**（26,000+ 次回测，含 DSR 检验）
   （https://tradingstrategies.work/strategies/wuguan-master-crypto）
   - 原文：「The **200-week SMA filter helped trend strategies almost universally:
     +6 to +15 percentage points**, several times DSR-confirmed (≥0.97).」
   - 反向证据（同样重要）：「ATR and altcoin-season filters **hurt** trend strategies
     badly (up to −30pp)」→ 不要加 ATR/山寨季过滤器

### 改动（实验变体，未提交生产）

`feature.py` → `add_basic_price_features` 新增 `%-trend-distance`
= `close / SMA(200 根 K 线) - 1`，并在模块顶部定义 `TREND_WINDOW_CANDLES = 200`。

**为什么这样做是合规的**：原需求禁止更改买卖逻辑，所以不能加「BTC 在均线上才交易」
的过滤开关。但 `add_basic_price_features` 对应 `feature_engineering_expand_basic`，
**会被 `include_corr_pairlist` 展开**，因此 BTC/ETH 的长期趋势状态会自动成为特征——
等于让模型自行学习「趋势状态」，而不改动任何买卖分支。

**与文献的偏差（必须标注）**：文献用日线 200 日；本策略为 4h 且 `train_period_days=365`
（2190 根），取 200 根 K 线（≈33 天）作为可实现近似。若有效，再评估放大窗口。

### 自检

- `py_compile` 通过；因果性自检 PASS（改动末行不影响历史行）。
- 有效性：`%-trend-distance` 10279/10478 行有效（98%），范围 [-0.597, +2.062]。
- 注意：该特征需 200 根历史，而 `startup_candle_count=100`，故回测起始约 100 根
  的该特征为 NaN（FreqAI 会丢弃这些训练行）；21 个月窗口下影响可忽略。

### 待测

`s1-regime-q1`（2025 Q1）与 `s1-regime-full`（2024-01~2025-09）已排队，
对照基线为已提交的 `entry_threshold=0.8`（+9.47%、回撤 -7.44%、夏普 0.758）。

---

## 数据覆盖核验（影响跨期对比的解读）

```
4h futures 数据实际范围: 2020-01-01 ~ 2025-11-29（故「全窗口 2024-01~2025-09」完全覆盖）
2023 全年有数据: 64/72 pair
2024 全年有数据: 70/72 pair
晚于 2022-06 上市: 12/72
  INJ(2022-08) LDO(2022-09) ICP(2022-09) QNT(2022-10) FET(2023-01) CFX(2023-02)
  STX(2023-02) PENDLE(2023-07) BSV(2023-10) CAKE(2023-11) RENDER(2024-07) SUN(2024-08)
```

**解读注意**：2023 的池子比 2024-2025 小（64 vs 70），因此 2023 与 2024-2025 的
**绝对收益不可直接比较**；但「同一期内的配置 A vs 配置 B」是同一宇宙，内部有效。
注意 CAKE 在 2023 只有 2 个月数据，而它是 Q1 2025 的最大贡献者（+108），
跨期归因时需留意。

---

## 2026-10-13 · 排序键 + 阈值叠加（全窗口略优，幅度在噪声内，待 2023 验证）

在已提交的 `entry_threshold=0.8` 之上，叠加「排序键不除波动率」（`model.py`
`build_candidate` 的 `normalized_score` 改为 `raw`）：

```
配置                        收益     回撤     笔数  夏普    索提诺   前3集中
t=0.8 基线(排序除vol)      +9.47%  -7.44%   145  0.758  0.567   93.8%
t=0.8 + 排序不除vol        +9.70%  -7.45%   153  0.840  0.617   94.8%
```

- 夏普 +0.082、收益 +0.23pp、交易数 +8 —— **幅度在噪声范围内，不足以单独作为
  采纳依据**。
- 方向与 Q1 一致（Q1 曾 +213.25 vs +190.85），但该项目历史上 Q1 优势极少外推成功。
- 已排队 `nonorm-2023`（2023 全年，纯样本外期）用于判定。

**若 2023 上 nonorm 不优于基线，则不采纳；若优于，再考虑提交 `model.py` 改动。**

---

## 基准数据修正（重要更正）

`calc_metrics.py` 的 `FUTURES_DIR` 硬编码指向 freqtrade 仓库的 user_data，
**那里的 BTC 1d 只有 2024-07-01 起的数据**（786 行），因此：

```
错误（残缺基准）: 全窗口 2024-01~2025-09  BTC +73.63%
正确（完整数据）: 全窗口 2024-01~2025-09  BTC +158.04%   ← 低估一半以上
正确: 2023 全年 BTC +154.7%   2024 全年 +111.5%   2025-01~09 +20.5%
```

修正方法（monkey-patch 基准目录）：

```python
import sys; sys.path.insert(0, '/home/wangke/project/freqtrade/scripts')
import calc_metrics as cm
cm.FUTURES_DIR = '/home/wangke/project/FreqtradeStratege/data/futures'
m = cm.calc_metrics(zip_path, 'BTC/USDT:USDT', start_nav)   # start_nav 从 wallet feather 读
```

### 修正后的全窗口权威对照（2024-01~2025-09，BTC **+158.04%**）

| 指标 | t=0.8（已提交） | t=0.4（原） | t=0.6 | t=1.2 | t=0.8+nonorm | s1-btc | t=0.8 2023 |
|---|---|---|---|---|---|---|---|
| 策略收益 | **9.47%** | 7.62% | 6.69% | 6.05% | **9.70%** | 12.95% | 6.80% |
| 策略年化 | 5.57% | 4.50% | 3.96% | 3.58% | 5.71% | 7.57% | 6.80% |
| 超额收益 | -57.58% | -58.30% | -58.66% | -58.90% | -57.49% | -56.23% | -60.07% |
| 基准(BTC) | 158.04% | 158.04% | 158.04% | 158.04% | 158.04% | 158.04% | 167.45% |
| 夏普比率 | 0.758 | 0.367 | 0.424 | 0.776 | **0.840** | 0.575 | 0.862 |
| 最大回撤 | -7.44% | -16.21% | -8.07% | -2.30% | -7.45% | -16.90% | -4.12% |
| 索提诺 | 0.567 | 0.420 | 0.352 | 0.479 | **0.617** | 0.609 | 0.605 |
| 信息比率 | -1.260 | -1.234 | -1.283 | -1.314 | -1.262 | -1.184 | -2.271 |
| 交易数 | 145 | 691 | 332 | 43 | 153 | 712 | 97 |

**结论不变但幅度更正**：阈值 0.4→0.8 的改善（收益 +1.85pp、回撤 -8.77pp、
夏普 +0.391）在正确基准下依然成立。所有配置都**远跑输 BTC 买入持有**
（超额 -57% 左右），策略定位仍是低回撤、近市场中性。

### 2023 全年验证（阈值 0.8）—— **判定：未通过，需回退**

同窗口对照（2023 全年，BTC +167.45%）：

```
配置        收益     夏普    最大回撤   索提诺   交易数  前3集中   盈利月
t=0.4(原)  +12.07%  0.940   -9.06%    0.808   325   102.0%   7/12
t=0.8(提交) +6.80%  0.862   -4.12%    0.605    97   199.8%   6/11
```

**0.4 在 2023 的收益（+12.07% vs +6.80%）、夏普（0.940 vs 0.862）、
集中度（102% vs 200%）三项上均优于 0.8；0.8 只赢了回撤（-4.12% vs -9.06%）。**

按本台账事先设定的判据（「若 2023 上 0.8 不优于 0.4，应立即回退并记录反例」），
**阈值改动未通过跨期验证**。

#### 综合判定（两个窗口方向相反）

```
窗口              收益差(0.8-0.4)   回撤差      夏普差
2024-01~2025-09      +1.85pp       +8.77pp    +0.391   ← 0.8 占优
2023 全年            -5.27pp       +4.94pp    -0.078   ← 0.4 占优
```

**结论：阈值 0.4→0.8 的效果不具有跨期稳健性**，属期间特异。
它在 2024-2025 大幅改善回撤与夏普，但在 2023 牺牲了收益与夏普。

#### 处置

- 保留 `entry_threshold = 0.8` 还是回退到 `0.4`，取决于**目标函数**：
  - 若目标是「低回撤、高夏普」→ 0.8 在两个窗口的**回撤都更小**（唯一稳健的改善），
    2023 夏普 0.862 仍高于 0.8 的绝对值门槛。
  - 若目标是「绝对收益」→ 0.4 在 2023 更好，0.8 在 2024-2025 更好，无稳定优势。
- **唯一在两个窗口都成立的是「回撤显著下降」**（-9.06%→-4.12%；-16.21%→-7.44%），
  这与文献预期一致（confidence threshold 主要作为风险削减工具，
  参见 MLP Confidence Filter 论文：「reducing drawdown more consistently than
  improving the risk-adjusted returns」）。
- 因此把该改动**重新定位为「风险控制」而非「收益提升」**，并在 config 注释中如实标注。

---

## 敞口归因：跑输 BTC 不只是「敞口只有 20%」的算术结果

从 `t08b-full` 的 wallet 净值序列直接算（全窗口 2024-01~2025-09）：

```
策略 日收益 +0.0154%  日波动 0.3880%  年化波动  7.41%   累计  +9.34%   收益/波动 0.759
BTC  日收益 +0.1816%  日波动 2.5844%  年化波动 49.38%   累计 +146.86%   收益/波动 1.342
```

- 策略年化波动只有 BTC 的 **15%**（7.41% vs 49.38%），累计收益只有 BTC 的 **6%**。
- 线性外推到同风险（敞口 ×6.66）：收益约 +62%，**仍低于 BTC 的 +146.9%**。
- 结论：**BTC 买入持有在本期同时跑赢策略的绝对收益与风险调整收益**
  （收益/波动 1.342 vs 0.759）。跑输不只是低敞口造成的——风险调整后的单位收益本身就更低。
- 策略唯一相对优势是**极低波动与极小回撤**（-7.44% vs BTC 同期约 -30%），
  即「用 15% 的风险换取 6% 的收益」。这在风险预算型配置里有意义，但作为 alpha 不成立。

**这是本项目最重要的期望管理结论**：在现有信息源与约束下，策略无法跑赢简单持有 BTC；
要改变这一点，必须引入新的信息源（不是继续调参）。

---

## 2026-10-13 · 标签归一改用 rolling30std（已否决）

### 动机

此前发现标签用 `ATR(14)/close` 归一（`model.py`），而策略排序键用
`close.pct_change().rolling(30).std()`（`MyStrategy.py`），属两套波动率度量串联，
怀疑会稀释排序信号。

### 改动（变体 `/tmp/labelvolvariant/model.py`）

`set_regression_target` 的 volnorm 分支改为
`future_return / close.pct_change().rolling(30).std()`，与排序键同口径。
阈值按尺度比例调整（0.4 × 2.019/1.193 ≈ 0.68 → 取 0.7）。

尺度核验（20 个 pair）：

```
旧标签（除 ATR）:         std 1.193   p50 0.606   p90 1.793   超 0.4 占比 65.0%
新标签（除 rolling30std）: std 2.019   p50 0.983   p90 3.011   超 0.4 占比 77.6%
```

### 实测（Q1 2025-01~03，真实回测）

```
run                              笔数   均收益%   总USDT    总%    胜率%
基线 (标签除ATR, t=0.4)           100     1.91   +190.85  +19.09   51.0
labvol (标签除rolling30std,t=0.7) 106     0.40    +42.35   +4.24   50.0
```

### 结论：已否决

「让标签与排序用同一波动率度量」使 Q1 收益从 +190.85 掉到 +42.35（-78%）。
**双波动率度量不是缺陷**，改成同口径反而更差。不再尝试该方向。

---

## Q1 筛选汇总表（2025-01~03 真实回测，--fee 0，钱包初值 1000）

基线 = `corr-s1` 原始配置（136 特征、corr=[BTC,ETH]、shifted=1、h=3、365 天窗、
t=0.4、排序除 vol），Q1 收益 **+190.85 USDT（+19.09%）**。

| 变体 | 改动 | 笔数 | 均收益% | 总USDT | 总% | 胜率% | 判定 |
|---|---|---|---|---|---|---|---|
| **nonorm** | 排序键不除波动率 | 98 | 2.18 | **+213.25** | 21.32 | 55.1 | **优** |
| 基线 | — | 100 | 1.91 | +190.85 | 19.09 | 51.0 | 基准 |
| h12 | 标签周期 3→12（48h） | 240 | 0.58 | +139.87 | 13.99 | 49.2 | 劣 |
| rev | 加反转因子（距高/低点、波动归一动量） | 92 | 1.34 | +123.16 | 12.32 | 50.0 | 劣 |
| t60 | 训练窗 365→60 天 | 203 | 0.51 | +104.08 | 10.41 | 54.7 | 劣 |
| p2b | 周期集合 [6,14,24]→[6,24] | 100 | 0.87 | +85.60 | 8.56 | 52.0 | 劣 |
| h6 | 标签周期 3→6（24h） | 174 | 0.39 | +68.64 | 6.86 | 54.0 | 劣 |
| SVM | `use_SVM_to_remove_outliers`=true | 101 | 0.58 | +58.85 | 5.89 | 50.5 | 劣 |
| labvol | 标签归一改用 rolling30std | 106 | 0.40 | +42.35 | 4.24 | 50.0 | 劣 |
| shifted2 | `include_shifted_candles` 1→2 | 108 | 0.08 | +9.30 | 0.93 | 49.1 | 劣 |
| d1 | `include_timeframes` 加 1d（268 特征） | 132 | 0.83 | +110.67 | 11.07 | **58.3** | 劣 |
| ex1 | `exit_threshold` 0.2→0.1 | 95 | 1.91 | +180.45 | 18.04 | 52.6 | 劣 |
| ex4 | `exit_threshold` 0.2→0.4（=entry） | 106 | 0.82 | +86.25 | 8.62 | 50.0 | 劣 |
| bb4 | 加布林带位置特征（154 特征） | 102 | 1.41 | +142.90 | 14.29 | **53.9** | 劣 |
| rsiBB4 | 消融：只留 RSI+布林带位置（64 特征） | 90 | 1.72 | +153.62 | 15.36 | **60.0** | 劣 |
| regime4 | 加趋势距离 `%-trend-distance`（200 根均线） | 115 | 1.52 | +173.65 | 17.37 | **60.0** | 劣（最接近） |

**一致模式**：`d1`、`bb4`、`rsiBB4` 三项都提高了胜率（58.3% / 53.9% / 60.0% vs 基线 51.0%），
但**总收益都下降**——说明这些特征让模型转向「赢面大但赢幅小」的交易，
而本策略的收益主要来自少数大幅盈利（与「前3 pair 集中度」的观察一致）。
**胜率提高不等于策略变好**，必须以总收益/夏普为准。

**注**：`bb`/`rsiBB`/`regime` 最初误用 `entry_threshold=0.8`（当时已提交值），
无法与 0.4 基线对比；已改用 0.4 与全新 identifier 重跑（`bb4`/`rsiBB4`/`regime4`），
上表为 0.4 口径结果。bb 在 0.8 下只有 21 笔（+56.59），说明该特征显著提高了选择性。

**结论：10 项变体中 9 项在 Q1 就劣于基线**，唯一 Q1 更优的 `nonorm` 在全窗口仅打平
（+9.70% vs +9.47%），2023 验证仍在队列。

---

## 关键诊断：为什么「胜率升高但总收益下降」？—— 用户提问的完整回答

用户问：「策略不是会对比全部 pair，选预测幅度最大的那个吗？为什么会转向赢面大、幅度小？」

### 事实一：`entry_threshold=0.4` 让「跨 pair 择优」只在 17~21% 的时间戳发生

```
基线 (corr-s1, Q1, 540 时间戳，每戳 72 pair 可用)
  过阈值候选数:  0 个 → 54.3%   1 个 → 28.3%   ≥2 个 → 17.4%
  中位 0 个，均值 0.80 个，最大 17 个
  → 真正发生跨 pair 比较的时间戳仅 17.4%

regime4: 0 个 → 44.6%   1 个 → 34.1%   ≥2 个 → 21.3%（比较 21.3%）
```

**54% 的时间戳无候选（不开仓）；28% 的时间戳恰好只有一个候选——此时没有「比较」，
只是接受那一个。** 用户设想的「对比全部 pair 取幅度最大」只在少数时间戳真正生效。
因此特征改动的影响，主要是「过阈值的那一个变了」，而不是「换了个 pair 来比」。

### 事实二：真实变化是「亏幅变大」，不是「赢幅变小」

按成交时 pair 波动率分 3 档（USDT，stake 100 × 2 倍杠杆）：

```
基线（100 笔）
  档位     笔数   均收益    胜率    盈利均幅   亏损均幅   盈亏比
  低波动    34    +0.864   47.1%   +5.014    -2.825    1.77
  中波动    33    +0.920   42.4%   +8.119    -4.385    1.85
  高波动    33    +3.973   63.6%   +8.580    -4.089    2.10

regime4（115 笔）
  档位     笔数   均收益    胜率    盈利均幅   亏损均幅   盈亏比
  低波动    39    -0.055   59.0%   +2.905    -4.311    0.67  ← 盈亏比反转
  中波动    38    +2.011   63.2%   +5.902    -4.659    1.27
  高波动    38    +2.615   57.9%   +9.987    -7.521    1.33
```

盈利均幅没有变大，**亏损均幅全面变大**（-2.825→-4.311；-4.089→-7.521）。
低波动档最典型：胜率 47%→59%，但盈亏比 1.77→0.67，净收益归零。

验证算式：

```
基线   : 0.510×0.73 + 0.490×(-0.37) = +0.19%
regime4: 0.600×0.62 + 0.400×(-0.55) = +0.15%   ← 胜率提升被亏幅放大抵消
```

### 事实三：机制——「选预测幅度最大」等价于「选波动最大的 pair」

排名键是 `|预测| / 波动率`，但**阈值卡的是未归一化的 `|预测| > 0.4`**，
能过阈值的是绝对预测幅度大的 pair，而绝对预测幅度与 pair 波动率强相关：

```
成交时 pair 波动率（开仓时刻）: 基线 0.0209 → regime4 0.0234（+12%）
开仓波动率 vs |盈亏| 相关性:    基线 +0.096 → regime4 +0.311（+224%）
```

新特征提升了方向判断（胜率 +9pp），但也把选择推向波动更大的 pair；
方向对时赚得多，方向错时亏得更多，**亏损放大超过胜率提升的补偿**。

### 局限（不断言过度）

低波动档仅 34~39 笔，「盈亏比反转」在统计上可能是噪声。本诊断的结论限于：
这是当前数据里唯一能解释「胜率升、总收益降」的机制，且与「开仓波动率 vs |盈亏|
相关性翻 3 倍」的观察一致。

### 可执行的推论

1. **阈值与排名键口径不一致**（阈值用 raw、排名用 raw/vol）是「偏向高波动 pair」的
   直接原因。若把阈值也改成作用在归一化 score 上，选择会转向「波动归一后仍突出」的
   pair，可能改善盈亏比。已实现该变体（`/tmp/normthrvariant`），待测。
2. 由于 54% 时间戳无候选，**交易数偏少、单笔权重过大**，任何单笔都会显著影响总收益
   ——这也是「结果对模型微小变化极敏感」的根源。

### regime4 全窗口结果：彻底失败（Q1 的「接近」是假象）

```
全窗口 2024-01~2025-09（BTC +158.04%）
配置                     收益     超额      夏普     回撤      笔数  胜率    前3集中
基线 corr-s1 (136特征)   +7.62%  -58.30%   0.367  -16.21%   691  51.4%  307.3%
regime4 (加趋势距离)     -4.51%  -62.99%  -0.045  -34.94%   760  53.2%  736.0%
```

Q1 上 regime4 仅差基线 1.72pp，全窗口却是 -4.51%（差 12pp），回撤翻倍到 -34.94%，
前3 pair 集中度 736%（单一 pair 贡献远超总收益）。**再次印证：Q1 结果几乎从不外推。**

---

## 本会话最终结论（在「不改买卖逻辑、只改指定文件」约束下）

1. **10+ 项变体全部未通过跨期验证。** 唯一 Q1 更优的 `nonorm` 在全窗口仅打平
   （+9.70% vs +9.47%）；阈值 0.8 在 2024-2025 大幅改善但 2023 反向，已回退；
   regime4/bb4/rsiBB4/d1 在 Q1 或全窗口均劣。
2. **瓶颈不在特征或模型容量**：`best_iteration ≤ 2` 占 51.4%（模型基本没学到东西），
   加减特征都变差。
3. **策略跑输 BTC 买入持有的风险调整收益**（收益/波动 0.759 vs 1.342），
   不只是低敞口所致。
4. **「跨 pair 择优」实际只在 17~21% 的时间戳发生**（54% 无候选、28% 仅一个候选），
   这是结果对微小改动极度敏感的结构性原因。
5. **阈值与排名键口径不一致**（阈值用 raw、排名用 raw/vol）使选择偏向高波动 pair，
   是「胜率升、总收益降」的机制。

**要真正改善，需要引入新信息源（资金费率/订单流/链上/换池或换周期）或放开买卖逻辑
（轮动规则、阈值口径、仓位规模），这些均超出当前约束。继续在原约束内调参已无边际。**

---

## 2026-10-13 · 用户假设检验：「直接比较预测值（极简排序）是否更好」

用户观点：「最理想是每个预测都准，直接选预测值最大的；除以波动率反而阻碍——
如果预测够准，涨幅最大就是涨幅最大。极简选股逻辑才能代表预测值准确度。」

### 检验 1：排序精度（秩 IC，pred 与未来 3 根实际收益）

```
2024  raw 预测      秩IC=+0.0042  t=+1.39
2024  预测/波动率    秩IC=+0.0124  t=+4.24   ← 显著更优（3 倍）
2025  raw 预测      秩IC=-0.0012  t=-0.31
2025  预测/波动率    秩IC=-0.0036  t=-0.96
```

**结论：与用户预期相反。** 「除波动率」在 2024 把秩 IC 提高 3 倍，t 从 1.39 升到 4.24
（本会话唯一统计显著的排序改进）。

### 检验 2：逐笔对照（只取两键选中不同 pair 的时间戳）

```
2024  不同 120 个:  raw 选中 +0.00024   除vol 选中 -0.00372   差 +0.00396  t=+0.95
2025  不同 155 个:  raw 选中 +0.00389   除vol 选中 -0.00597   差 +0.00987  t=+1.44
```

**方向支持用户**（raw 选中者实际收益更高），但 t 仅 0.95/1.44，未达显著；
且 2025「raw 更好占比」仅 47.7%——优势来自少数大赢家，不是稳定更优。

### 检验 3（关键）：前提检验 —— |预测| 越大是否对应 |实际收益| 越大

```
|pred| 与 |实际收益| 的 Pearson 相关:  2024 +0.0047    2025 +0.0120   （≈0）

|pred| 五档对应的 |实际收益| 均值:
  2024:  +2.598%  +2.553%  +2.471%  +2.445%  +2.594%   ← 完全平坦
  2025:  +2.551%  +2.539%  +2.567%  +2.501%  +2.541%   ← 完全平坦
```

**「预测幅度大 → 实际涨幅大」的前提在本项目不成立。** 无论预测大小，
实际收益幅度都在 2.5% 附近，五档几乎完全一致。

这与 `best_iteration ≤ 2`（51.4% 的模型最优就是第一棵树）的诊断一致：
**模型输出接近常数，预测值的大小不含幅度信息。**

### 综合结论

| 用户论点 | 检验结果 |
|---|---|
| 除以波动率会阻碍排序 | ✗ 2024 秩 IC 提高 3 倍（t=4.24） |
| 直接比 raw 更好 | △ 逐笔方向支持（+0.004/+0.010）但不显著 |
| 前提「预测值够准」 | ✗ \|pred\| 与 \|收益\| 相关 ≈ 0，五档完全平坦 |

**根本瓶颈不是排序键，而是预测值本身没有幅度区分度。**
换成极简 raw 排序不会改变这一点——两个键都在用没有信息量的预测值，
只是「除波动率」恰好掺入了一个真实有效的独立变量（波动率）。

**可执行的推论**：既然 |pred| 无幅度信息，而波动率有，那么提高波动率在排序中的权重
（而非取消它）理论上更优——这与用户直觉相反，但符合检验 1 的结果。
若用户坚持极简 raw 排序，建议先解决预测值无区分度的问题（需新信息源），
而不是改排序键。

**注意**：`p2b`（减少特征周期数）与 `shifted2`（增加特征）都变差，说明该池既不能
简单减特征、也不能简单加特征——与 `best_iteration≤2` 的诊断一致：瓶颈不在特征数量。

---

## 2026-10-13 · 模型预测专项（职责收窄后的取证）

用户明确职责边界：**只负责模型输入（特征）与模型预测（model.py），其他不管**；
并要求「只预测下一个 K 线的涨跌幅度，不需要判断强弱」「每件事都要有依据」。

### 取证 1：FreqAI 的训练机制与跨币机制（官方文档原文）

来源 A：https://www.freqtrade.io/en/stable/freqai-running/
> "FreqAI will train a new model **for each pair**, for each backtesting window"
> "During dry/live mode, FreqAI trains **each coin pair sequentially**"

来源 B：https://docs.freqtrade.io/en/stable/freqai-feature-engineering/
> "You can ask for each of the defined features to be included also for informative pairs
> using the **`include_corr_pairlist`**. This means that the feature set will include all the
> features from `feature_engineering_expand_*()` on all the `include_timeframes` for each of
> the correlated pairs defined in the config"

源码佐证：
```
freqai_interface.py:987   def train(self, unfiltered_df, pair: str, dk, **kwargs)
data_kitchen.py:120       sub-train-{pair}_{ts}
```
→ FreqAI 为每个 pair 训一个模型；**跨币信息通过 `include_corr_pairlist` 注入特征**。

### 取证 2：模型实际接收的训练特征（读 metadata）

`models/mystrategy-4h-regression-72pair-corr-s1-v1/sub-train-BTC_1735689600/cb_btc_1735689600_metadata.json`：
```
training_features_list 长度 = 92
  含 BTC 的: 44     含 ETH 的: 44     本币专属: 4（volatility-6 / volatility-24 / hour / day-of-week）
labels: ['&-s_return']    labels_std: 1.23
```
→ 跨币特征确实进入了模型（88/92 是跨币特征），扩 `include_corr_pairlist` 会直接增加它们。

### 取证 3（根因）：截面信号与时序信号**符号相反**

对每个特征分别计算「截面 IC」（逐时间戳跨 72 币的秩相关，策略选股需要的能力）与
「时序 IC」（逐币跨时间的秩相关，逐币训练能学到的能力）：

```
特征                    截面IC(跨币)   时序IC(币内)   比值    截面t   时序t
%-volatility-24        -0.0583      +0.0125     -4.7   -24.8   +7.6   ← 符号相反
%-volatility-6         -0.0467      +0.0262     -1.8   -22.1  +16.5   ← 符号相反
%-atr-ratio-period     -0.0588      +0.0157     -3.8   -23.2   +9.2   ← 符号相反
%-range                -0.0511      +0.0241     -2.1   -23.6  +14.7   ← 符号相反
%-relative-volume      -0.0081      +0.0190     -0.4    -5.3  +10.9   ← 符号相反
%-rsi-period           -0.0505      -0.0285      1.8   -28.0  -14.4   同号
%-ema-distance-period  +0.0566      +0.0335      1.7   +28.8  +16.7   同号
%-sma-distance-period  +0.0526      +0.0299      1.8   +27.0  +15.7   同号
%-momentum-period      -0.0419      -0.0250      1.7   -21.5  -14.5   同号
%-return               -0.0415      -0.0224      1.9   -23.6  -17.2   同号
%-body                 -0.0415      -0.0225      1.8   -23.6  -17.3   同号
```

**5 个波动/振幅/量比类特征的截面与时序符号相反**（波动率截面负、时序正——经典的
低波动异象 + 波动聚集）。逐币时序训练会把这些特征的系数学成**相反符号**，
从而在截面选股上起反作用。同号特征的截面 IC 也比时序 IC 大约 1.8 倍。

### 取证 4：标签 raw vs volnorm（同管线、只换标签，FreqAI 逐币 XGBoost）

```
标签        年     秩IC      t      方向准确   幅度相关    选择增益    增益t
raw        2024  -0.0030  -0.85   50.03%   +0.1214   -0.00378   -3.56
raw        2025  +0.0003  +0.08   50.46%   +0.0734   +0.00110   +0.80
volnorm    2024  +0.0042  +1.39   49.97%   +0.0334   -0.00181   -1.83
volnorm    2025  -0.0011  -0.28   50.47%   +0.0011   +0.00272   +2.14
```

（幅度相关 = 逐时间戳 `corr(|预测|, |实际收益|)` 的均值；选择增益 = `argmax|预测|`
选中 pair 的带符号实际收益 − 全池均值）

**结论：raw 标签把「幅度校准」提升 3.6~67 倍（0.1214/0.0734 vs 0.0334/0.0011），
完全符合用户「预测涨跌幅度」的要求；但 `argmax|预测|` 的选择增益变差。**

### 取证 5：为什么 raw 的 argmax 选择更差（低波动异象）

`argmax|预测|` 在 raw 标签下会选「预测绝对涨幅最大」的 pair，而这些通常是
**高波动 pair**；而高波动 pair 在截面上未来收益**更低**（`%-volatility-24` 截面 IC = −0.0583）。
因此「按幅度选股」与「按截面收益选股」方向相反。

**这是一个需要用户决策的真实权衡，不是可以两全的参数问题。**

### 已完成：`raw-corr4`（历史窗口否决）

`raw-corr4` 使用 `label=raw`，并把 `include_corr_pairlist` 扩到 BTC/ETH/BNB/SOL。依据是本台账前面的截面基准实验和 FreqAI 官方 `include_corr_pairlist` 文档：
https://www.freqtrade.io/en/stable/freqai-feature-engineering/

该实验已完成，不再是“正在跑”。在历史研究窗口 `2024-01-01` 至 `2025-09-01`、72 个 pair、手续费 0.05% 下，策略收益为 `-15.81%`，closed-trades Sharpe `-0.61`，最大回撤 `64.11%`，2,027 笔交易。Q1 的正向秩 IC 和幅度校准优势没有外推到连续全窗口，且回撤超过 30% 门槛，因此否决；没有进入独立 OOS 生产候选，也没有修改生产配置。

### 取证 6（直接证据）：模型学到的符号 vs 选股需要的符号

对已训练的 `corr-s1` 模型，逐特征计算 `corr(预测, 特征)`（模型学到的方向）
与「该特征的截面 IC」（选股需要的方向）：

```
特征                        corr(预测,特征)   截面IC(特征,收益)   符号
%-volatility-24            +0.0364          -0.0514          反号
%-volatility-6             +0.0390          -0.0481          反号
%-rsi-period               +0.0112          -0.0485          反号
%-atr-ratio-period         +0.0348          -0.0532          反号
%-momentum-period          +0.0072          -0.0399          反号
%-relative-volume-period   +0.0254          -0.0132          反号
%-range                    +0.0507          -0.0521          反号
%-ema-distance-period      +0.0092          +0.0544          一致
%-sma-distance-period      +0.0055          +0.0536          一致
%-return                   -0.0239          -0.0363          一致
%-body                     -0.0238          -0.0363          一致
```

**11 个特征中 7 个反号**——模型学到的方向与截面选股需要的方向相反。
这是「预测无选股价值」的**直接证据**（不再是推断）。

### 取证 7：Q1 同窗口对比（apples-to-apples，540 时间戳）

```
identifier                       秩IC      t      方向准确   幅度相关   选择增益   增益t
corr-s1 (volnorm, corr=2)       -0.0143  -2.23   50.73%   +0.0110   +0.00835   +3.76
raw-full (raw, corr=2)          -0.0036  -0.58   50.22%   +0.0870   +0.00197   +0.86
raw-corr4 (raw, corr=4)         +0.0125  +2.11   50.81%   +0.0761   +0.00649   +2.77
```

**结论**：
- `raw-corr4` 是唯一 **秩 IC 显著为正**（t=+2.11）的配置；corr-s1 的 IC 显著为负（t=−2.23）。
- `raw-corr4` 的**幅度校准是 corr-s1 的 6.9 倍**（+0.0761 vs +0.0110），符合用户
  「预测涨跌幅度」的要求。
- 但 corr-s1 的 **argmax 选择增益仍更高**（+0.00835 vs +0.00649）——因为策略只看
  极端值那一个，整体排序改善未必转化为 top-1 改善。
- 全窗口结果已证明 Q1 优势不能外推；后续模型选择必须以独立 OOS 和完整连续窗口为准。

---

## 2026-10-13 · 严格目标仓位规格验证（全窗口复核）

用户要求的极简规格：

1. 去掉开仓/持仓幅度阈值，只过滤 FreqAI 无效预测（`do_predict != 1`、None、NaN、Inf）；
2. 每根 K 线取原始 `|预测值|` 最大的 pair，符号定方向；
3. 无可用目标即平仓保持空仓。

### 实测对照

窗口：**2024-01-01 ~ 2025-09-01**（连续 20 个月，费率 0，现有 72 pair 数据）。

| 版本 | 变化 | 交易数 | 总收益 | Sharpe | Sortino | 钱包最大回撤 |
|---|---|---:|---:|---:|---:|---:|
| 原基线 | `|pred/vol|` + 持仓阈值 0.2 | 691（台账） | 7.62% | 0.367 | 0.420 | -16.21% |
| 变体 A | 原始 `|pred|` + 持仓阈值 0.2 | 718 | 7.49% | 0.32 | 0.44 | 15.61% |
| **严格规格 A+B** | 原始 `|pred|` + 无目标立即平仓 | **781** | **22.98%** | **1.18** | **1.64** | **13.19%** |

### 重要修正

Q1（2025-01~03）曾显示严格规格劣于保留持仓阈值：`10.48% vs 21.32%`。
但该结论是**单窗口结论**，全窗口复核后方向相反：严格规格
`22.98% vs 7.49%`，收益高 3 倍，Sharpe 和回撤也更优。

**最终采用严格规格**：短窗口与全窗口冲突时，以连续 20 个月的全窗口结果为准。
不能再用 Q1 单窗口否决 B。

### 当前代码实现

- `model.resolve_target_position(candidates)`：不再接受阈值，直接取原始 `|预测值|` 最大。
- `model.decide_position_action(held_pair, held_side, target)`：不再接受
  `held_candidate`/`exit_threshold`，无目标直接返回 `exit`。
- `MyStrategy.populate_entry_trend`：只按预测符号标记入场，不设幅度阈值。
- `config.json`：删除 `entry_threshold` / `exit_threshold`。
- 验证：`11 passed`，`py_compile` 通过，`git diff --check` 通过。

