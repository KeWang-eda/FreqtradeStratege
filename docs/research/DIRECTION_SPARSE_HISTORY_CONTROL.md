# 固定跨度稀疏监督对照：单历史折方向改善

## 问题与依据

早期小训练折的概率泛化损失较大，但跨折同时变化了市场时期，不能把差异直接归因样本量。本次固定H10第三折的预测时段、验证选择结果及特征表征，比较1042行监督训练与覆盖相同起止时间的344行。

依据sklearn官方learning_curve对固定测试折比较不同训练规模的定义：<https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.learning_curve.html>。不调用其默认分类交叉验证，因为默认并不保证时序安全；本项目沿用既有成熟forward。近期344会混入历史年代变化，因此选固定`rint(linspace(0,1041,344))`，不按标签选行、不扫相位或数量。

历史已有120/240天回归窗、原生90天短窗失败记录，不声称首次研究历史长度。当前不同之处是原生binary、同历史跨度、固定选树预算及learner-only监督抽稀，不是生产窗口调整。

## 冻结实验

协议在训练前写入`artifacts/native-direction-audit/sparse-history-control/protocol.json`。

- 只比较H10 fold2三个币，原train1042、validation262、test436/币。
- 两臂共享仅在原1042梯度训练拟合的原生pipeline及DI；这不是344行端到端预处理学习曲线。较老无监督X仍可用，没有引入验证或预测统计。
- 固定原seed0分类参数及原基线实际50/6/21棵树，候选不重新早停、不重新用验证标签挑轮数。预算由完整基线选择，对照是该预算条件下的比较。
- 子集保留原权重，不重新生成或归一。跨度不变，但标签重叠/样本相关、类别组成、总权重和相对正则强度都会改变；不能识别纯样本数量因果效应。
- 原基线预测必须逐点复现H10，候选save/load必须逐点相同；两臂truth/ready一致。
- 所有数据已曝光，仅单折机制诊断，不套用三折准入或称独立确认。

## 结果

| 币种 | 共同ready | 原1042行正确 | 稀疏344行正确 | 净变化 |
|---|---:|---:|---:|---:|
| BTC | 435 | 237 | 249 | +12 |
| ETH | 435 | 202 | 237 | +35 |
| BNB | 436 | 218 | 210 | -8 |
| 合计 | 1306 | 657 | 696 | +39 |

主方向准确率50.3063%→53.2925%，提升2.9862个百分点，183点由错变对、144点由对变错。2个not-ready不计错误，另报全1308点659→697，净+38。

日期同步三个币、5000次循环区块bootstrap、seed42、按实际ready数计算比率，95%区间（百分点）：6根[+0.1510,+5.8959]，12根[+0.3823,+5.8195]，24根[+0.2301,+5.9054]。区间条件于这些已拟合模型、固定coverage和既有历史；未校正累计选择或覆盖重训方差。

独立审计确认基线逐元素复现、抽样规则、原权重子集、固定树数及结果。总权重552.034→182.269，所以更强相对正则可能参与改善；不能宣布减少重叠标签就是根因。ETH贡献最大且BNB下降，尚无跨折复制。

## 提交边界与下一验证

按用户“有提升就提交push”的要求，将这个**有正配对结果的研究工具与证据**提交；不修改生产模型或配置，不把单折研究提升当成已证实的生产收益。`external_gate_passed=false`是三折门槛不适用，不是忽略本次正区间。

下一步需先冻结稀疏规则的可迁移定义，再验证其他历史折/时期，保持现结果与失败记录。不得按本折选择seed、币种、相位或样本数，不直接部署344窗口。

## 复现

```sh
conda run --no-capture-output -n quant python -m tools.run_direction_sparse_history_control
conda run --no-capture-output -n quant python -m tools.summarize_direction_control --directory artifacts/native-direction-audit/sparse-history-control --candidate sparse
conda run --no-capture-output -n quant python -m pytest tests/contract/test_direction_sparse_history_control.py tests/contract/test_direction_control_summary.py -q
```

默认相对路径，现存输出拒绝覆盖；运行器可传`--output`新目录，汇总器对应传`--directory`。依赖本地原生训练快照与H10保存baseline/pipeline，未把大型模型/市场数据纳入git；不具备这些输入时不能独立重训。提交配对预测、冻结协议、审计和summary用于复核已报告结果。8项相关测试通过，没有交易回测。
