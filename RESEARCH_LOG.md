# 迭代依据台账（RESEARCH_LOG）

每次改动记录：改了什么、依据来源（论文/文档/仓库/博客）、实测数据、结论。
原则：**先有依据再改，改完必须回测，回测结果必须与同窗口基线对照。**

回测口径：`--fee 0`（隔离信号质量与成本），生产 `config.json` 的 `fee` 保持 `0.0005`。
指标计算：`/home/wangke/project/freqtrade/scripts/calc_metrics.py`
（注意：该脚本默认 `initial_capital=100`，本项目钱包初值为 1000，必须显式传入，否则收益虚高 10 倍）。

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

- 阈值曲线**非单调**（0.4→7.62%、0.6→6.69%、0.8→9.47%、1.2→6.05%），
  0.8 的峰值可能含噪声成分。
- 待验证：2023 全年（此前从未用于任何实验的纯样本外期）上 0.8 是否仍优于 0.4。
- 所有配置仍远跑输 BTC 买入持有（+73.63%）；策略定位是**低回撤、近市场中性**，
  不是跑赢基准的 alpha。

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
