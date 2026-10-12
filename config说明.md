# config.json 配置说明

`config.json` 使用严格 JSON，不能写 `//` 或 `/* */` 注释，否则 Freqtrade 无法解析。因此这里逐项说明，不污染可执行配置。

## 顶层交易配置

| 字段 | 当前值 | 作用 |
|---|---|---|
| `trading_mode` | `futures` | 使用合约模式。 |
| `margin_mode` | `isolated` | 使用逐仓保证金。 |
| `max_open_trades` | `1` | 全局最多一个持仓；择优逻辑通过 `confirm_trade_entry` 拒绝非最强 pair。 |
| `stake_currency` | `USDT` | 保证金币种。 |
| `stake_amount` | `100` | 每笔保证金 100 USDT。 |
| `dry_run` | `true` | 当前为模拟交易。 |
| `dry_run_wallet` | `1000` | 模拟钱包初始余额。 |
| `timeframe` | `4h` | 主策略 K 线周期。 |
| `fee` | `0.0005` | 回测单边手续费口径。 |
| `datadir` | `/home/wangke/project/FreqtradeStratege/data` | 本地市场数据目录；原 `MyStrategy/data` 已于 2026-10-12 被清空，数据改放仓库内。不要改成仓库相对路径。 |

## 价格与订单

| 字段 | 当前值 | 作用 |
|---|---|---|
| `entry_pricing.price_side` | `same` | 入场按同侧报价。 |
| `exit_pricing.price_side` | `same` | 出场按同侧报价。 |
| `use_order_book` | `true` | 使用订单簿价格逻辑。 |
| `order_types.entry` | `limit` | 入场限价单。 |
| `order_types.exit` | `limit` | 普通出场限价单。 |
| `order_types.stoploss` | `market` | 止损类型配置；策略当前用 `stoploss=-1.0` 表示不设实际保护性止损，主要退出由预测轮换完成。 |

## 止盈止损

```text
minimal_roi = {"0": 999.0}
strategy.stoploss = -1.0
strategy.trailing_stop = false
```

含义：

- 不使用普通 ROI 止盈；
- 不使用 trailing stop；
- 不依赖固定止损退出；
- 由预测反转和跨 pair 最强性变化触发退出。

`-1.0` 不是交易所层面的“删除订单保护”开关，而是把固定止损放到极远位置；实盘 dry-run 前应确认账户级强平风险和交易所规则。

## FreqAI

| 字段 | 当前值 | 作用 |
|---|---|---|
| `freqaimodel` | `XGBoostRegressor` | 连续收益率回归模型。 |
| `identifier` | `mystrategy-4h-regression-72pair-v1` | FreqAI 模型/预测缓存命名空间；改特征、标签、模型时必须更换。 |
| `train_period_days` | `365` | 每个 pair 使用 365 天历史训练。 |
| `backtest_period_days` | `7` | 回测滚动训练周期。 |
| `include_timeframes` | `["4h"]` | 只用 4h FreqAI 特征。 |
| `label_period_candles` | `3` | 预测未来 3 根 4h K 线。 |
| `include_shifted_candles` | `2` | 保留前 2 根历史特征。 |
| `DI_threshold` | `2.0` | FreqAI 数据可信度过滤阈值。 |
| `indicator_periods_candles` | `[6,14,24]` | 特征展开周期。 |
| `eval_metric` | `rmse` | 回归训练验证指标；不能使用 `mlogloss`。 |

## 回归实验开关

```json
"my_experiment": {
  "label": "volnorm",
  "features": [],
  "entry_threshold": 0.4,
  "probe": false
}
```

- `label=raw`：标签为未来收益率；
- `label=volnorm`：标签为未来收益率除以 ATR/close；
- `features`：独立 `feature_engineering.py` 中的 technical 指标开关；
- `entry_threshold=0.4`：volnorm 预测阈值；raw 标签时应使用另一尺度；
- `probe`：写入 `/tmp/reg_rank_probe.jsonl`，用于审计跨 pair 时间对齐；生产应关闭。

## Pair 池

当前配置列出 72 个有有效 4h futures 数据且可用于 365 天训练的 pair。JST、PAXG 和没有有效 4h 文件的标的没有放入配置。

每个 pair 由 FreqAI 独立训练模型；`MyStrategy.py` 在 `confirm_trade_entry` 中读取各 pair 的 analyzed dataframe，用共同时间锚点比较 `abs(prediction_return / recent_vol)`，只允许最强 pair 开仓。
