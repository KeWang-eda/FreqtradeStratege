# 迭代依据台账（RESEARCH_LOG）

每次改动记录：改了什么、依据来源（论文/文档/仓库/博客）、实测数据、结论。
原则：**先有依据再改，改完必须回测，回测结果必须与同窗口基线对照。**

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

