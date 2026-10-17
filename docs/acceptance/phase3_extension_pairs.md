# 原始历史数据逐交易对覆盖表

生成时间：2026-10-17T13:09:29.250013+00:00。区间：`20250101-20250122`；停止时间不含。

`raw` 包含训练预热、相关币对对齐、标签边界与 funding/mark 对齐。metadata 单列，不把行情文件存在当作可离线回测。

| 交易对 | raw | metadata | 离线可用 | 缺口或限制 |
|---|---|---|---|---|
| BTC/USDT:USDT | True | True | True | 无窗口缺口 |
| ETH/USDT:USDT | True | True | True | 无窗口缺口 |
| BNB/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |

## 文件范围与全历史质量

| 文件 | 行数 | 起始 UTC | 最后 UTC | 重复 | 全历史缺失行/事件间隔 | SHA与Phase0一致 |
|---|---:|---|---|---:|---|---|
| data/futures/BTC_USDT_USDT-4h-futures.feather | 14880 | 2020-01-01T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BTC_USDT_USDT-1h-mark.feather | 59443 | 2020-01-01T00:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BTC_USDT_USDT-1h-funding_rate.feather | 7429 | 2020-01-01T00:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7428} | True |
| data/futures/ETH_USDT_USDT-4h-futures.feather | 14880 | 2020-01-01T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ETH_USDT_USDT-1h-mark.feather | 59443 | 2020-01-01T00:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ETH_USDT_USDT-1h-funding_rate.feather | 7429 | 2020-01-01T00:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7428} | True |
| data/futures/BNB_USDT_USDT-4h-futures.feather | 14638 | 2020-02-10T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BNB_USDT_USDT-1h-mark.feather | 59443 | 2020-01-01T00:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BNB_USDT_USDT-1h-funding_rate.feather | 7308 | 2020-02-10T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7307} | True |

Funding 文件名 1h 是原生存储键，不表示每小时付款。变频事件明确待核实，不补造缺失事件。精确区间、非法值、标签及 SHA 见配套 JSON。
