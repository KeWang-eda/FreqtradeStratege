# 特征与标签目录

研究核心特征名包含真实周期（默认 6、14、24），顺序为配置周期顺序、基础价量、波动/时间、按名称排序的可选技术指标。

| 类别 | 公式 / 字段 |
| --- | --- |
| RSI | TA-Lib RSI(period) |
| EMA/SMA 距离 | EMA(close, period)/close − 1；SMA 同理 |
| ATR 比率 | ATR(period)/close |
| 相对成交量 | volume / rolling_mean(volume, period) |
| 累计动量 | close / close.shift(period) − 1 |
| 单根收益 | close.pct_change(fill_method=None) |
| 振幅 / 实体 | (high − low)/close；close/open − 1 |
| 成交量变化 | volume.pct_change(fill_method=None) |
| 波动率 | 单根收益 rolling(6/24).std() |
| 时间 | UTC hour/23；dayofweek/6 |
| 可选 technical | laguerre、vwmacd + hist、tke + ema、vfi + hist、rmi |

所有指标仅用当前和历史行。输入索引保持不变，Inf 转缺失只作用于特征列；未知指标和计算失败直接报错。technical 仅在实际启用可选特征时导入。

FreqAI 2026.7 自身把周期追加到特征名，`add_freqai_period_features` 因此把研究核心列名转换为旧回调输出，最终框架列名与旧版本相同。基线回归样本验证数值及回调列序。

标签 raw = close[t+h]/close[t] − 1；volnorm = raw / (ATR(14)[t]/close[t])，可配置 ATR 周期。TA-Lib RSI/ATR 最小支持 period=2，因此当前 schema 最小值为 2；不会接受 1 后在计算时崩溃。零价格和非有限标签转为缺失，尾部 h 行不可训练。

日期为 UTC K 线开盘时间。特征在该 K 线收盘可用，标签结束时间为第 t+h 根 K 线收盘。预测的 candle_timestamp 仍记录信号 K 线的开盘时间；成交时间交给 Freqtrade。
