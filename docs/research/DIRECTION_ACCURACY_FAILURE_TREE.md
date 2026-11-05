# 方向准确率故障树与当前模型诊断

## 1. 当前主指标

本轮唯一主指标是逐样本方向准确率：

```text
direction = mean(sign(prediction) == sign(volnorm_future_return))
```

零值视作第三种状态，必须单独报告；`prediction_ready=0`、NaN 和缺失样本不能默认为方向错误。MAE、RMSE、Pearson、Spearman 只作为护栏和诊断，不作为本轮候选选择标准。

方向预测的基准不能只写 50%。每个窗口同时报告测试窗口事后最佳常量方向参照 `max(P(y>0), P(y<0))`（不能部署）；可部署基准的方向必须仅由训练标签多数类选定、混淆矩阵、预测正负比例、`zero_pred_rate` 和按 `|prediction|` 分箱的 coverage-accuracy。依据：Pesaran & Timmermann (1992), *A Simple Nonparametric Test of Predictive Performance*, DOI `10.1080/07350015.1992.10509922`；scikit-learn classification metrics 文档（https://scikit-learn.org/stable/modules/model_evaluation.html#classification-metrics）。

## 2. 故障树

```text
方向准确率低
├─ A 标签/评估语义
│  ├─ A1 horizon/时间索引错位
│  ├─ A2 volnorm 与 raw return 符号/分母错误
│  ├─ A3 零收益、零预测、NaN 的处理改变分母
│  └─ A4 时区、重复 candle 或 pair 对齐错误
├─ B 类别基准与样本
│  ├─ B1 正负类别比例漂移，多数类基准被忽略
│  ├─ B2 近零未来收益本身不可预测
│  ├─ B3 训练 sample_weight 改变正负类比例
│  └─ B4 horizon=3 重叠造成有效样本数被高估
├─ C 回归输出到符号
│  ├─ C1 MSE学条件均值，其符号不一定等价于 P(y>0)>.5；MAE学条件中位数
│  ├─ C2 预测接近 0 时符号容易随机
│  ├─ C3 blend/校准造成符号翻转或单边输出
│  └─ C4 训练输出恒定（early stopping 第 0 棵树）
├─ D 模型训练
│  ├─ D1 回归目标与方向目标不一致
│  ├─ D2 分类器过拟合/类别不平衡
│  ├─ D3 早停欠拟合或关闭早停过拟合
│  └─ D4 regime shift 导致符号关系失效
└─ E 推断与选择偏差
   ├─ E1 只看 pooled accuracy，掩盖 pair/fold 失败
   ├─ E2 重叠标签和时间自相关导致置信区间过窄
   ├─ E3 多次调参后挑选最高窗口
   └─ E4 交易层 0 的语义与离线评估不一致
```

## 3. 当前模型的证据

标签定义已核验：`close.shift(-3)/close - 1` 再除以因果 ATR(14)/close，符号与 raw return 一致；项目代码 `np.sign(actual)==np.sign(pred)` 也没有发现索引错位。方向链路的第一层 A 暂无证据支持。

四个原生基线窗口、每币对 48 个预测的方向诊断如下：

| 窗口 | 币对 | 准确率 | 事后常量参照 | 真实正类比例 | 预测正类比例 | `|y|<0.1` | 零预测 |
|---|---|---:|---:|---:|---:|---:|---:|
| 2024-01 | BTC | 60.4% | 58.3% | 41.7% | 60.4% | 2.1% | 0 |
| 2024-01 | ETH | 45.8% | 64.6% | 35.4% | 60.4% | 6.2% | 0 |
| 2024-01 | BNB | 41.7% | 58.3% | 58.3% | 0.0% | 8.3% | 0 |
| 2025-01 | BTC | 50.0% | 50.0% | 50.0% | 100.0% | 8.3% | 0 |
| 2025-01 | ETH | 41.7% | 52.1% | 47.9% | 18.8% | 10.4% | 0 |
| 2025-01 | BNB | 52.1% | 52.1% | 52.1% | 100.0% | 14.6% | 0 |
| 2026-01 | BTC | 66.7% | 64.6% | 64.6% | 85.4% | 10.4% | 0 |
| 2026-01 | ETH | 54.2% | 60.4% | 60.4% | 64.6% | 10.4% | 0 |
| 2026-01 | BNB | 56.3% | 58.3% | 58.3% | 97.9% | 16.7% | 0 |
| 2026-10 | BTC | 62.5% | 50.0% | 50.0% | 20.8% | 20.8% | 0 |
| 2026-10 | ETH | 52.1% | 52.1% | 52.1% | 8.3% | 10.4% | 0 |
| 2026-10 | BNB | 43.8% | 52.1% | 47.9% | 62.5% | 12.5% | 0 |

已观察到的问题是**部分窗口符号输出单边化**，C1/C3仅是待验证解释，不能从该现象直接推断损失函数或组合造成错误。例如 2025-01 BTC/BNB 的预测全为正，2024-01 BNB 全为负；这些不是零预测问题，而是模型学到的条件幅度均值在符号上偏向一侧。多个币对的准确率低于测试窗口事后最佳常量方向参照，说明“回归幅度再取符号”没有稳定解决方向任务。

**C4/D3 也有证据：** BNB 2025-01 基线输出恒定，根因为早停第 0 棵树；关闭早停能恢复变化，但跨窗口和币对不稳定，不能直接接入生产。

**B2 需要继续量化：** 近零标签比例在窗口间为约 2%–21%，近零样本的符号噪声可能限制总体准确率。必须先做 `|y|` 分箱的 accuracy/coverage，不能直接用阈值删样本后宣称准确率提升。

## 4. 下一项可验证实验

优先验证 C1，而不是继续调回归超参数：在相同数据、时间切分、特征和训练窗口下，将现有 XGBoost 回归器与项目已有 `xgboost_direction` 二分类器做四窗口原生对照。主指标只看方向准确率，同时记录多数类基准、balanced accuracy、预测正类比例、零预测率和按时间 block 的区间。

分类器的概率阈值先固定为 `0.5`；项目当前把概率映射为正负条件收益均值，实际符号阈值不一定是 `0.5`，这必须作为单独的阈值诊断，不能和模型训练混在一起。只有分类器在预先固定的独立窗口中超过回归器和多数类基准，才继续考虑接入；否则回到 C2/C4 的输出符号与早停分析。


## 5. 阈值诊断结果

参见 `DIRECTION_THRESHOLD_DIAGNOSTIC.md`。同一分类器的两种阈值平均差异区间跨零，近期窗口恶化，不修改生产阈值或模型。

## 6. 冻结候选的连续样本验证

`error`早停在原576点平均+2.604个百分点，但在2529个新增预测中相对`logloss`仅+0.079个百分点，6/12/24根区块区间均跨零。不将该候选接入生产。此证据把下一项收敛到2026-01分类器随预测时间延长失效，先按周分解类别与预测符号分布，不能继续在原窗口挑指标或阈值。详见`DIRECTION_THRESHOLD_DIAGNOSTIC.md`扩窗章节。

## 7. 模型陈旧分支复验

2026-01六周预测的单边输出通过周更仅部分缓解；相同1月1日初始化下，周更50.000%对冻结48.016%，配对6/12/24/42根区块区间均跨零。不能把模型陈旧确定为唯一根因。参见`DIRECTION_ROLLING_DIAGNOSTIC.md`，后续从每周验证期到预测期的判别能力变化继续定位，不在同一756点评估段选参。

## 8. 验证判别落差与refit分支

18模型train/validation/development平均方向准确率64.46%/55.77%/50.00%，验证集用于早停不算独立证据。第3/4周开发AUC低于0.5，第5周AUC尚可但方向准确率低，不能用同一个先验修正解释。固定原best_iteration+1后合并成熟train/validation重拟合，方向降至47.35%，五周下降，拒绝该候选。18组标签成熟性审计通过；详见`DIRECTION_VALIDATION_REFIT_DIAGNOSTIC.md`。下一叶节点为长期验证汇总是否掩盖近期失效，先描述统计后实验。

## 9. 近期验证范围分支

固定最后42成熟验证行，观察到第3–5周局部失效被完整验证汇总掩盖，但第6周不一致。只缩短early-stop eval_set，训练和其它设置不变，方向50.000%降至48.148%（1周升、1周平、4周降），否决。详见`DIRECTION_RECENT_VALIDATION_DIAGNOSTIC.md`。不继续扫描该窗口长度或在同一756点挑方案。

## 10. 两个预声明特征的训练期稳定性

只检验自身单根收益、momentum14在四个训练子期的单调方向关联；未用开发标签选择。单根收益方向变号，BTC/BNB momentum14均反向，ETH末段接近无关联；尚无正式显著性或增量预测验证，不据此删除特征或新增规则。详见`DIRECTION_FEATURE_STABILITY_DIAGNOSTIC.md`。

## 11. momentum14增量信息消融

训练内部3折forward、双层label maturity purge，完整特征51.5915%对移除自身未shift momentum14的51.7189%，3927点净增5正确；6/12/24根区块区间均跨零。无可信改善，不删列。单seed且列抽样变化、已有AUC观察构成探索限制，详见`DIRECTION_MOMENTUM_ABLATION.md`。

## 12. 分类标签契约分支

发现并局部修复非有限标签静默编码、class0均值遗漏零收益两个问题，26个相关测试通过。四窗576点映射前后方向正确数321→321，未证明方向收益；修复留本地、不push。详见`DIRECTION_LABEL_CONTRACT_AUDIT.md`。不能把这两个低层问题归因为当前预测能力差的主因。

## 13. 固定低容量分类对照

保持相同训练内forward样本与purge，Logistic(C1)51.6679%对XGB51.5915%，3927点净增3正确、6/12/24根区块区间均跨零。不切换此模型，也不据此否定所有容量解释。详见`DIRECTION_LINEAR_CONTROL_DIAGNOSTIC.md`。下一项先明确相对可部署训练多数类参照的增益，不扫描C。

## 14. 可部署基线与历史先验proxy

相同训练内3927点主基线(inner-train多数类)47.263%，成熟past多数类50.700%，XGB51.592%。主基线差支持该研究时期存在相对常量参照的增益，不证明独立泛化。只用预测前成熟历史的prior odds修正，XGB升至52.916%，净增52正确，但6/12/24根区块区间均跨零。保持候选定义，不push或扫先验窗口；详见`DIRECTION_MAJORITY_PRIOR_DIAGNOSTIC.md`。

## 15. 历史先验proxy跨时期复核

冻结odds修正在2024-01提高0.637pp，在2025-01/2026-10分别下降0.280/0.407pp，合并略降；各时期时间区块区间均跨零。否决该proxy的推广，不证明label shift假设不存在。详见`DIRECTION_PRIOR_CROSS_PERIOD_DIAGNOSTIC.md`。

## 16. 原生方向学习器与跨时期失效（2026-11-05）

以真实原生预处理、原始收益符号和样本权重训练独立分类头，H8仅把固定树数改为自身验证logloss早停。新增两个历史开发复制窗口合计817/1512（54.03%），固定binary为762/1512（50.40%）；这是已复用开发数据的机制证据，尚非生产确认。分类margin不属于收益预测，未接入生产回归输出。详见`NATIVE_DIRECTION_LOGLOSS_LEARNER.md`。

进一步分解：2023复制窗456/756（60.32%），2024复制窗361/756（47.75%）。当前故障树聚焦后者：

```text
2024方向准确率47.75%
├─ A 模型、币对、日期、预处理映射错误 → 逐点重放一致，未见支持
├─ B 训练/验证标签未成熟 → 截止时间审计通过，未见支持
├─ C 统一阈值偏移
│  ├─ C1 验证期已偏正 → 有观察证据，尤其BNB
│  └─ C2 足以解释所有周失败 → 不支持；第2周AUC仅0.282
├─ D 局部判别关系失效
│  ├─ D1 第2周方向准确率33.33%、AUC0.282 → 描述证据
│  └─ D2 第6周AUC0.609但准确率45.24% → 另有边界失配迹象
└─ E 最新73天仅作验证导致陈旧
   ├─ E1 协议事实 → 已确认，不等于因果
   └─ E2 合并重训可改善 → 同机制既往实验50%→47.35%，不重复盲试
```

下一项只诊断概率边界失配与判别反转的区别；在选择具体调整前，检查独立时间内切分及确认数据使用记录，不能在已观察的forecast上搜索最佳阈值。`python -m tools.diagnose_native_direction`在conda quant中可复现6模型、12周诊断；准确率保留真零收益，AUC仅对非零真值计算。完整证据见`NATIVE_DIRECTION_2024_FAILURE_DIAGNOSTIC.md`和`artifacts/native-direction-audit/h8-failure-diagnostic.json`。

2026-11-06 D4 train/validation 条件漂移诊断已完成：固定重放 H8 learner，训练4块、早停验证6块，逐块 maturity purge，未读 outer forecast truth。两段验证平均逐币 AUC 分别0.5509/0.5940，均高于0.5；验证真实上涨率约48.70%/52.68%，但预测上涨率39.87%/71.10%，表现更接近时期相关的边界偏移，而非普遍排序反转。短块 AUC 波动不足以证实条件反转。D4 当前不支持，不能据此加 regime feature 或修改模型。详见`NATIVE_DIRECTION_CONDITION_DRIFT_DIAGNOSTIC.md`及`artifacts/native-direction-audit/condition-drift-diagnostic.json`。

## 17. H9：独立成熟样本的截距校准被否决

预先固定原valid尾84成熟样本校准，早停部分purge后351点，重新拟合同一binary模型；两臂仅区别为b=0与logit+b单截距MLE。初始1917点1027→1033（+6），复制1512点828→748（-80），复制两个时期均下降。复制6/12/24根同步日期区块区间分别[-9.987,-0.395]、[-10.053,-0.265]、[-10.516,+0.132]个百分点。15组截距均满足校准目标且成熟/映射审计通过，失败不能归为求解错误。

否决此具体概率边界修正，不扫描新校准长度/阈值，不推广或push。此前H5和prior odds失败也保留为相关反证；不能换名重复。下一层回到训练期内部成熟forward的跨期判别稳定性，先定位明确失效关系，再选择训练干预。见`NATIVE_DIRECTION_INTERCEPT_CONTROL.md`及`artifacts/native-direction-audit/intercept-control/summary.json`。

## 18. H10：随机边界敏感性存在，固定种子均值未达门槛

实际H8树种子为默认0，split配置42不是模型种子。只在2024复制窗的原train1746点内部进行三折成熟forward，每折fresh原生pipeline，预先固定seed0..4概率均值对seed0；共9个pipeline/45模型，不读取外部预测标签。ready3919点1949→1961，净+12(+0.3062pp)，三fold+8/-2/+6；6/12/24根日期同步区块区间[-0.3316,+0.9677]/[-0.2811,+0.9441]/[-0.2552,+0.8917]pp均跨零。

14.72%的ready样本在五seed之间方向分歧，支持存在随机敏感性，但不足以支持均值改善。未达到预先固定的全部区间下界>0门槛，停止外部扩展，不挑seed3、不修改集合或权重、不推广或push。34项相关测试通过，两位独立源数据/统计审计通过。详见`NATIVE_DIRECTION_SEED_CONTROL.md`及`artifacts/native-direction-audit/seed-control-inner/summary.json`。

## 19. H11：补充当前收盘区间位置未达门槛

构造两根当前native输入完全相同但CLV不同的合法K线，合同测试证实信息表达缺口；TA-Lib官方AD源码提供CLV公式。按预先冻结协议只追加own current CLV一列，维持H10 seed0、原pipeline/DI/双层purge/权重，baseline逐点复现。ready3919点1949→1960，净+11(+0.2807pp)，三fold+12/+1/-2；6/12/24根同步日期区块区间[-0.4338,+0.9711]/[-0.4085,+1.0201]/[-0.4081,+0.9451]pp均跨零。BNB+15、BTC-1、ETH-3，不能择币推广。

新增列还改变colsample随机路径，不能将点值变化称纯信息因果贡献。未达事先全部下界>0门槛，停止外扩、不调CLV版本、不提交或push模型候选。65项相关测试通过；当前OHLCV与旧snapshot自身return/range/body逐点一致，两位独立审计通过。见`NATIVE_DIRECTION_CLV_CONTROL.md`及`artifacts/native-direction-audit/clv-control-inner/summary.json`。另修主配置datadir为相对data，仅属可移植性，不计入模型提升。

## 20. H13：mark-to-trade close spread未达门槛

严格使用`t..t+3h`已闭合1h mark close与4h trade close比值减一，H10三折fresh native forward中ready3919点1949→1959，净+10(+0.2552pp)，fold+6/-2/+6；6/12/24根同步区块区间[-0.4595,+1.0196]/[-0.4588,+1.0196]/[-0.4851,+1.0201]pp均跨零。所有区间跨零，停止外扩，不修改数据聚合规则，不push。Binance官方字段正文未在本轮稳定取得，报告明确不作外部API语义背书。见`NATIVE_DIRECTION_MARK_SPREAD_CONTROL.md`及`artifacts/native-direction-audit/mark-spread-control-inner-v2/summary.json`。

## 21. 固定344行下的总权重尺度控制

四时期fold2中，将344个稀疏样本的权重乘以`full_weight_sum/sparse_weight_sum`，使总量匹配1042行训练。依据XGBoost梯度/Hessian加权和与正则项的尺度关系；这一单因素机制控制在样本、pipeline、seed、树数、参数不变时运行。full/sparse/sparse_mass正确数2708/2700/2692（5232点）；质量匹配相对原稀疏少8点，区块区间跨零。

没有发现该权重尺度修正能稳定提升方向准确率，不提交此改动，不改变生产训练。它也不能确定样本相关性或抽样组成的因果作用。详见`DIRECTION_SPARSE_WEIGHT_MASS_CONTROL.md`。

## 22. margin边界收缩诊断未支持

对full、sparse、sparse_mass三臂固定margin距离分箱，准确率没有随距离边界单调增加；full最窄桶反而54.92%，非零AUC分别0.5178/0.5243/0.5234。不能据此设计margin收缩、扩张或新阈值，下一层回到跨时期条件判别关系。详见`DIRECTION_MARGIN_BOUNDARY_DIAGNOSTIC.md`。
