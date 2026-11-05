# 方向学习器：自身logloss选树的实现与证据

## 本轮唯一机制问题

上一候选把回归模型选出的实际树数直接给分类器。H8检验：保持二元
目标、原生预处理后的特征、成熟训练/验证行、权重、参数、0.5边界
不变，仅改为分类器自身的加权验证logloss早停。

依据是XGBoost官方early-stopping接口：eval_metric决定模型选择标准，
callback可指定validation_0、最小化logloss、patience30、save_best=True。
每个模型建立新callback，树数上限300。不改为方向error，不扫耐心、
深度、学习率、阈值或窗口。训练logloss改善不自动等于方向accuracy改善。

主要来源：

- https://xgboost.readthedocs.io/en/stable/python/python_api.html
- https://xgboost.readthedocs.io/en/stable/tutorials/custom_metric_obj.html
- https://scikit-learn.org/stable/modules/model_evaluation.html

实际接口同时按conda quant的XGBoost 3.2.0源码核对。原生回归模型只
作参考，主配对从始至终是固定树数binary→自身logloss选树binary。

## 方向准确率结果

主指标为未加权sign(prediction)==sign(volnorm truth)，零真值保留。
输出为direction_margin，不能与收益单位混淆。旧三窗和额外两窗均已
用于历史开发，不能称全新留出数据。

| 阶段 | 点数 | 回归参考 | 固定树数binary | 自身logloss选树 |
|---|---:|---:|---:|---:|
| 原三窗口 | 1917 | 50.0261% (959) | 52.6865% (1010) | 52.8951% (1014) |
| 额外两窗口 | 1512 | 47.6852% (721) | 50.3968% (762) | 54.0344% (817) |

括号为正确预测数。主配对原三窗净多对4次（+0.2087个百分点），
时间块区间跨零；额外两窗净多对55次（+3.6376个百分点）。

| 额外复制时期 | 固定binary | logloss | 净变化 |
|---|---:|---:|---:|
| 2023-06-23至2023-08-04（结束不含，UTC） | 410/756 | 456/756 | +46 |
| 2024-06-23至2024-08-04（结束不含，UTC） | 352/756 | 361/756 | +9 |

复制按各时期内日期同步重采样，同日三币成组，5000次circular block
bootstrap，每块长seed42。候选减固定binary的95%区间（百分点）：

| 块长 | 区间 |
|---|---|
| 6根 | [+0.9921, +6.1508] |
| 12根 | [+1.1243, +6.0185] |
| 24根 | [+1.3889, +5.9524] |

这支持在该复制样本中修正分类器选树规则，足以保留并提交为研究候选，
但不是生产替换证据：

- 原三窗口相对固定binary两降一升，合并只净增4次。
- 复制的保留训练标签多数方向基线为774/1512=51.1905%，候选虽为
  817/1512，其相对多数基线的日期块区间仍跨零。
- 2024复制期候选361/756仍低于多数372/756和回归363/756。
- 2023提升不是单币集中：BTC/ETH/BNB分别152/161/143点正确，固定
  binary为141/138/131；保留训练+验证多数为133/138/131。
- 训练窗口共享历史、预测模型冻结，不复现实盘每日重训；历史已重复
  查看，不把多个窗口视为完全独立试验。

“保留训练+验证多数”只使用实际保留的两类行，不含purge删除行，
不能泛称所有历史成熟标签。两个stage各有2个零收益，均保留分母。
样本键、truth、ready完全相同，覆盖率100%。

## 实际模型代码，不只是配置

新增quant/models/native_direction.py::NativeDirectionLearner，将验证过
的拟合过程提取为独立研究方向head：

- fit_preprocessed接收原生变换后的特征及索引对齐的原单位收益标签；
  不重新拟合一套近似特征pipeline。
- 从原始y>0编码二类，拒绝NaN/Inf、错位、重复/重排schema、训练验证
  行重叠、非法权重及有效加权单类。
- 自动建立新logloss早停callback，使用同一验证权重。
- predict_proba_up返回上涨概率；predict_margin返回2*p-1。
  不提供泛称predict()，不注册收益模型factory，不改写&-s_return。
- 持久化绑定拟合feature_pipeline文件SHA-256、schema、依赖版本和
  训练参数，保存后加载检查参数与callback元数据一致性。
- pipeline ID和原始标签单位仍由调用者如实提供；仅凭数值不能证明
  标签未被缩放，时间成熟性也由上游原生切分及审计负责。

现有收益PredictionRecord、收益排序及生产config.json不变。方向分数
不是期望收益，不能进入当前volnorm_return列；部署融合需要另行设计
方向head与收益幅度的合同，不能在本次研究里悄悄替换。

入口为tools/run_native_direction_control.py，默认读取项目config.json，
使用项目相对输入/输出路径；旧artifact脚本保留兼容入口。输入需要
本地原生训练快照和配对预测表，不会下载数据或执行交易回测。

## 重构验证

按Fowler小步重构原则，先保留原实验数值，再提取代码：

- 15个模型（9个control、6个replication）原实现与新learner的所有
  arm预测逐点完全相同，最大差0.0。
- 新CLI以默认config.json重放两阶段，同样逐点完全相同。
- 每个learner保存/加载后预测一致；模型契约重新读回通过。
- 26个方向learner合同测试，加11个既有策略合同测试，共37 passed。
  覆盖概率/方向单位、标签/权重/索引、schema、依赖/预处理ID、损坏
  参数/耐心元数据、保存加载与直接XGBoost参照实现。

原H8协议effect字段曾继承H7的fixed-budget文案，已加注释更正为只改
树数选择；change/tree_selection和实际模型一直是正确logloss方案。
该文案修正没有改变训练规则或实验结果。

## 复现

```sh
conda run -n quant python -m tools.run_native_direction_control --help
conda run -n quant python -m tools.run_native_direction_control --output artifacts/native-direction-audit/my-logloss-control
conda run -n quant python -m tools.run_native_direction_control --source artifacts/native-direction-audit/binary-replication-inputs/predictions.parquet --output artifacts/native-direction-audit/my-logloss-replication
conda run -n quant python artifacts/native-direction-audit/summarize_early_stop.py --candidate binary_logloss --baseline fixed_binary --directory artifacts/native-direction-audit/my-logloss-replication
conda run -n quant python -m pytest tests/contract/test_native_direction_learner.py tests/regression/test_strategy_contract.py -q
```

输出目录拒绝覆盖旧证据；只有重复复现时才需指定新输出目录。默认
配置、原生快照和预测输入位置均已配置，不要求每次输入所有路径。
发布的summary/protocol/audit与direction-learner-replay.json是精简证据；
本地模型及大体量原始parquet继续保留，不混入代码提交。

当前结论：提交经验证的研究方向learner与复现工具；生产收益预测器
保持原实现，不宣称稳定泛化或已经完成生产优化。
