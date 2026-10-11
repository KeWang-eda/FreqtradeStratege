# MyStrategy

最小的 1h 下一根方向分类策略。

## 逻辑

```text
输入当前已收盘 1h K 线
  -> 118 个模型特征（1h + 4h 两个周期，各含 2 根历史滞后）
  -> XGBoostClassifier
  -> 预测 3 根 1h K 线之后的收盘方向
  -> up: 做多 / down: 做空（仅当最高类别概率 >= 0.55）
  -> 反向预测或 1.5% 回撤后 0.5% 追踪止损平仓
```

特征分为：

- 1h 与 4h 两个周期各自展开：RSI、EMA 乖离、SMA 乖离、ATR/close、相对成交量（周期 6、14、24，当前及前 2 根）；
- 收益率、振幅、实体、成交量变化：当前及前 2 根；
- 6 根和 24 根波动率、小时、星期几。

标签（`label_period_candles: 3`）：

```text
3 根之后 close > 当前 close -> up
否则                       -> down
```

末尾 3 根没有未来 K 线，标签为 NaN，不参与训练。

## 文件

- `MyStrategy.py`：1h 下一根方向策略；
- `config.json`：1h futures + XGBoostClassifier 配置，当前只跑 BTC；
- `test_my_strategy.py`：下一根方向标签的最小检查；
- `data/futures/`：已有本地 futures K 线数据，不覆盖。

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
