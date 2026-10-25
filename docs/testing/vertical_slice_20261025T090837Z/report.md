# 4h 开发级纵向实验闭环

生成时间：2026-10-25T09:08:37Z UTC。范围：BTC、ETH、BNB；4h；`NON_FORMAL_DEVELOPMENT`。

## 结论

本地行情到数据集、时间切分、Ridge 训练、预测评估和单持仓模拟回测已真实运行完成。开发测试链路 PASS；正式研究仍为 **BLOCKED**。本实验使用 raw return 诊断标签和本地固定 BTC/ETH/BNB 候选，不代表生产 volnorm 任务、历史 PIT universe、真实 Funding 成本或正式 OOS。

## 数据与切分

使用 Arrow 谓词只读取 metadata-only holdout 起点 `2025-10-17T04:00Z` 之前的数据，没有读取 final holdout 数值。数据集共 37,822 行，预测输出 15,228 行。所有 4h 数据质量检查通过，具体文件哈希、样本和排除记录见 `data_quality.json`。

时间边界：

- 训练：2020-01-02T04:00Z 至 2023-06-23T20:00Z 之前，22,594 行。
- 验证：2023-06-23T20:00Z 至 2024-08-19T20:00Z 之前，7,614 行。
- 开发测试：2024-08-19T20:00Z 至 2025-10-16T16:00Z，7,614 行。

同一 `available_at` 时间戳的三币记录整体切分，没有跨集合拆分。最后 15% final holdout 未读取。

## 模型与预测指标

实际训练了每币一个 Ridge 模型，参数 `alpha=10.0`，seed 42，6 个本地因果 pandas 特征。模型工件和配置见 `models/`、`model_parameters.json`。

开发测试指标：

- 模型 MAE：0.0145966；零收益基线 MAE：0.0144815。
- 模型 RMSE：0.0213586；零收益基线 RMSE：0.0213090。
- 方向准确率：0.5012；零收益常数预测的方向指标不具备比较意义。
- Rank IC 均值：-0.02206。

模型在该开发测试区间没有优于零收益基线，不能据此宣称预测能力或交易价值。

## 单持仓模拟

模拟按每个决策时点的绝对预测排序，最多持有一个资产，持仓 12 小时；信号来自当前可用 candle，收益使用对应 horizon=3 的目标。产生 846 笔交易。

开发假设：双边每边手续费 0.05%，滑点 0，Funding 未建模，候选 universe 固定为 BTC/ETH/BNB。结果：最终权益 1.5175，最大回撤 -35.47%，简单累计假设净收益 0.6597。该结果不是净实盘收益，也不是正式回测；缺少真实 Funding、PIT universe 和滑点证据。

预测和交易明细见 `predictions.csv`、`trades.csv`，运行参数和源文件指纹见 `run_manifest.json`。

## 首次失败与修复

第一次运行在现有 dataset builder import 阶段因 quant 环境缺少 `talib` 失败。为完成开发闭环，在本实验脚本内使用最小 pandas 因果特征适配；没有修改生产特征、标签、策略或配置。修复后完整链路退出码 0。

## 测试与正式边界

定向切分/指标测试共 65 passed，脚本编译和 `git diff --check` 通过。没有运行全量测试、正式 OOS、模型优选、final holdout 或生产更新。Funding 来源、支付语义、历史规则、PIT universe、真实成本和正式 P3–P6 仍为 BLOCKED。
