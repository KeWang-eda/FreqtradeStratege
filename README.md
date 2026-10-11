# MyStrategy

4h 连续收益率回归策略：对 72 个有有效 4h futures 数据的 pair 独立训练模型，
在当前 K 线统一比较波动率归一化预测分数，只开 abs(score) 最大的 1 个仓位。

## 逻辑

```text
当前已收盘 4h K 线
  -> 61 个因果模型特征
  -> XGBoostRegressor
  -> 预测未来 3 根 4h 收益率 / ATR 波动率归一化
  -> prediction_return > 0.4 做多，< -0.4 做空
  -> 所有 pair 的 abs(prediction_return / recent_vol) 横向排序
  -> 只保留分数最高的一个 pair
  -> 反向预测、追踪止损或硬止损退出
```

标签通过 `config.json` 的 `my_experiment.label` 控制：

```text
raw     : future_return
volnorm : future_return / (ATR(14) / close)
```

## 文件

- `MyStrategy.py`：4h 回归、跨 pair 全局择优策略；
- `config.json`：XGBoostRegressor，72 个 4h pair，1 个最大持仓；
- `test_my_strategy.py`：阈值标签兼容性检查；
- `RESEARCH_LOG.md`：实验与跨 pair 验证记录；
- `data/futures/`：本地 futures K 线数据，不纳入 Git。

## 风控与最小下单额

当前 BTC Futures 账户使用 2x 杠杆、100 USDT stake 和 1000 USDT 模拟钱包。
原因是 Binance BTCUSDT 的 `LOT_SIZE.minQty` 为 0.001 BTC（约 100 USDT 名义价值），
2x 杠杆下 stake 低于 50 USDT 会在执行层被拒绝，和模型信号无关。

钱包必须显著大于单笔 stake：`stake_amount` 等于钱包余额时，一旦净值跌破 stake，
后续所有入场都会因余额不足静默失败（回测表现为交易数骤减、钱包长期冻结）。
1000 USDT 钱包 / 100 USDT stake = 10% 仓位，留出足够回撤空间。

## 先跑最小检查

```bash
cd /home/wangke/project/MyStrategy
/home/wangke/project/freqtrade/.venv/bin/python -m pytest -q test_my_strategy.py
```

## 回测

当前配置默认只使用 BTC/USDT:USDT，最多 1 个持仓，模拟钱包 1000 USDT。数据根目录是
`/home/wangke/project/MyStrategy/data`，Freqtrade 会自动读取其中的 `futures/` 子目录：

```bash
cd /home/wangke/project/freqtrade

.venv/bin/freqtrade backtesting \
  -c /home/wangke/project/MyStrategy/config.json \
  --userdir /home/wangke/project/MyStrategy \
  --datadir /home/wangke/project/MyStrategy/data \
  --strategy-path /home/wangke/project/MyStrategy \
  --strategy MyStrategy \
  --timerange 20250101-20250801 \
  --cache none \
  --export trades \
  --backtest-directory /tmp
```

如果要切换交易对，修改 `config.json` 的 `exchange.pair_whitelist`，并确认
`data/futures/` 中存在对应的 `*-1h-futures.feather`；使用多周期特征时还需对应的
`*-4h-futures.feather`（可用 `freqtrade download-data --timeframes 4h` 补齐）。

## 解释边界

这是“模型预测下一根方向后交易”的最小基线，不是已经证明有收益的策略。Freqtrade
在当前 K 线收盘产生信号，回测通常在下一根 K 线执行；预测准确率、手续费和反转频率
必须通过真实回测分别核对。

改特征、标签或模型参数后必须更换 `freqai.identifier`，避免复用旧预测缓存。
