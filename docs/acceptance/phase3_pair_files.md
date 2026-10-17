# 原始历史数据逐交易对覆盖表

生成时间：2026-10-17T13:09:50.988994+00:00。区间：`20250101-20250115`；停止时间不含。

`raw` 包含训练预热、相关币对对齐、标签边界与 funding/mark 对齐。metadata 单列，不把行情文件存在当作可离线回测。

| 交易对 | raw | metadata | 离线可用 | 缺口或限制 |
|---|---|---|---|---|
| 1INCH/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| AAVE/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ADA/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ALGO/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| AR/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ATOM/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| AVAX/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| AXS/USDT:USDT | False | False | False | data/futures/AXS_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| BAND/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| BAT/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| BCH/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| BEL/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| BNB/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| BSV/USDT:USDT | False | False | False | data/futures/BSV_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| BTC/USDT:USDT | True | True | True | 无窗口缺口 |
| CAKE/USDT:USDT | False | False | False | data/futures/CAKE_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| CFX/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| COMP/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| CRV/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| DASH/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| DOGE/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| DOT/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| EGLD/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ENJ/USDT:USDT | False | False | False | data/futures/ENJ_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| ENS/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ETC/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ETH/USDT:USDT | True | True | True | 无窗口缺口 |
| FET/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| FIL/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| GRT/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| HBAR/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ICP/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| INJ/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| IOST/USDT:USDT | False | False | False | data/futures/IOST_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| IOTA/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| JASMY/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| KAVA/USDT:USDT | False | False | False | data/futures/KAVA_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| KNC/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| KSM/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| LDO/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| LINK/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| LTC/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| NEAR/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| NEO/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ONT/USDT:USDT | False | False | False | data/futures/ONT_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| PENDLE/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| QNT/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| QTUM/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| RENDER/USDT:USDT | False | False | False | data/futures/RENDER_USDT_USDT-4h-futures.feather: incomplete_requested_window；缺 [2023-12-16T08:00:00+00:00, 2024-07-26T08:00:00+00:00)，1338行；data/futures/RENDER_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| RLC/USDT:USDT | False | False | False | data/futures/RLC_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| RSR/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| RUNE/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| SKL/USDT:USDT | False | False | False | data/futures/SKL_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| SNX/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| SOL/USDT:USDT | False | False | False | data/futures/SOL_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| STX/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| SUN/USDT:USDT | False | False | False | data/futures/SUN_USDT_USDT-4h-futures.feather: incomplete_requested_window；缺 [2023-12-16T08:00:00+00:00, 2024-08-22T12:00:00+00:00)，1501行；data/futures/SUN_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| SUSHI/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| THETA/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| TRB/USDT:USDT | False | False | False | data/futures/TRB_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| TRX/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| UNI/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| VET/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| XLM/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| XMR/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| XRP/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| XTZ/USDT:USDT | False | False | False | data/futures/XTZ_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| YFI/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ZEC/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ZEN/USDT:USDT | True | False | False | 不在当前可信市场快照范围 |
| ZIL/USDT:USDT | False | False | False | data/futures/ZIL_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |
| ZRX/USDT:USDT | False | False | False | data/futures/ZRX_USDT_USDT-1h-funding_rate.feather: funding_schedule_requires_verification；不在当前可信市场快照范围 |

## 文件范围与全历史质量

| 文件 | 行数 | 起始 UTC | 最后 UTC | 重复 | 全历史缺失行/事件间隔 | SHA与Phase0一致 |
|---|---:|---|---|---:|---|---|
| data/futures/1INCH_USDT_USDT-4h-futures.feather | 12724 | 2020-12-25T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/1INCH_USDT_USDT-1h-mark.feather | 50819 | 2020-12-25T08:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/1INCH_USDT_USDT-1h-funding_rate.feather | 6350 | 2020-12-25T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6349} | True |
| data/futures/AAVE_USDT_USDT-4h-futures.feather | 13145 | 2020-10-16T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/AAVE_USDT_USDT-1h-mark.feather | 52504 | 2020-10-16T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/AAVE_USDT_USDT-1h-funding_rate.feather | 6561 | 2020-10-16T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6560} | True |
| data/futures/ADA_USDT_USDT-4h-futures.feather | 14698 | 2020-01-31T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ADA_USDT_USDT-1h-mark.feather | 59002 | 2020-01-19T09:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ADA_USDT_USDT-1h-funding_rate.feather | 7373 | 2020-01-19T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7372} | True |
| data/futures/ALGO_USDT_USDT-4h-futures.feather | 13876 | 2020-06-16T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ALGO_USDT_USDT-1h-mark.feather | 55928 | 2020-05-26T11:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ALGO_USDT_USDT-1h-funding_rate.feather | 6989 | 2020-05-26T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6988} | True |
| data/futures/AR_USDT_USDT-4h-futures.feather | 11064 | 2021-09-28T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/AR_USDT_USDT-1h-mark.feather | 44201 | 2021-09-27T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/AR_USDT_USDT-1h-funding_rate.feather | 5523 | 2021-09-27T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 5522} | True |
| data/futures/ATOM_USDT_USDT-4h-futures.feather | 14655 | 2020-02-07T12:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ATOM_USDT_USDT-1h-mark.feather | 58571 | 2020-02-06T08:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ATOM_USDT_USDT-1h-funding_rate.feather | 7319 | 2020-02-06T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7318} | True |
| data/futures/AVAX_USDT_USDT-4h-futures.feather | 13283 | 2020-09-23T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/AVAX_USDT_USDT-1h-mark.feather | 53074 | 2020-09-22T09:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/AVAX_USDT_USDT-1h-funding_rate.feather | 6632 | 2020-09-22T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6631} | True |
| data/futures/AXS_USDT_USDT-4h-futures.feather | 12935 | 2020-11-20T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/AXS_USDT_USDT-1h-mark.feather | 51664 | 2020-11-20T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/AXS_USDT_USDT-1h-funding_rate.feather | 7416 | 2020-11-20T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 5654, "14400": 1553, "3600": 208} | True |
| data/futures/BAND_USDT_USDT-4h-futures.feather | 13619 | 2020-07-29T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BAND_USDT_USDT-1h-mark.feather | 54400 | 2020-07-29T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BAND_USDT_USDT-1h-funding_rate.feather | 6798 | 2020-07-29T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6797} | True |
| data/futures/BAT_USDT_USDT-4h-futures.feather | 14620 | 2020-02-13T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BAT_USDT_USDT-1h-mark.feather | 58407 | 2020-02-13T04:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BAT_USDT_USDT-1h-funding_rate.feather | 7299 | 2020-02-13T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7298} | True |
| data/futures/BCH_USDT_USDT-4h-futures.feather | 14880 | 2020-01-01T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BCH_USDT_USDT-1h-mark.feather | 59443 | 2020-01-01T00:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BCH_USDT_USDT-1h-funding_rate.feather | 7429 | 2020-01-01T00:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7428} | True |
| data/futures/BEL_USDT_USDT-4h-futures.feather | 12947 | 2020-11-18T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BEL_USDT_USDT-1h-mark.feather | 51713 | 2020-11-18T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BEL_USDT_USDT-1h-funding_rate.feather | 6462 | 2020-11-18T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6461} | True |
| data/futures/BNB_USDT_USDT-4h-futures.feather | 14638 | 2020-02-10T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BNB_USDT_USDT-1h-mark.feather | 59443 | 2020-01-01T00:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BNB_USDT_USDT-1h-funding_rate.feather | 7308 | 2020-02-10T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7307} | True |
| data/futures/BSV_USDT_USDT-4h-futures.feather | 6549 | 2023-10-20T12:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BSV_USDT_USDT-1h-mark.feather | 26125 | 2023-10-20T06:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BSV_USDT_USDT-1h-funding_rate.feather | 6528 | 2023-10-20T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"14400": 6525, "28800": 2} | True |
| data/futures/BTC_USDT_USDT-4h-futures.feather | 14880 | 2020-01-01T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/BTC_USDT_USDT-1h-mark.feather | 59443 | 2020-01-01T00:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/BTC_USDT_USDT-1h-funding_rate.feather | 7429 | 2020-01-01T00:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7428} | True |
| data/futures/CAKE_USDT_USDT-4h-futures.feather | 6471 | 2023-11-02T12:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/CAKE_USDT_USDT-1h-mark.feather | 25811 | 2023-11-02T08:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/CAKE_USDT_USDT-1h-funding_rate.feather | 6449 | 2023-11-02T16:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"14400": 6447, "28800": 1} | True |
| data/futures/CFX_USDT_USDT-4h-futures.feather | 8001 | 2023-02-20T12:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/CFX_USDT_USDT-1h-mark.feather | 31933 | 2023-02-20T06:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/CFX_USDT_USDT-1h-funding_rate.feather | 3990 | 2023-02-20T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 3989} | True |
| data/futures/COMP_USDT_USDT-4h-futures.feather | 13792 | 2020-06-30T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/COMP_USDT_USDT-1h-mark.feather | 55097 | 2020-06-30T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/COMP_USDT_USDT-1h-funding_rate.feather | 6885 | 2020-06-30T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6884} | True |
| data/futures/CRV_USDT_USDT-4h-futures.feather | 13415 | 2020-09-01T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/CRV_USDT_USDT-1h-mark.feather | 53584 | 2020-09-01T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/CRV_USDT_USDT-1h-funding_rate.feather | 6696 | 2020-09-01T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6695} | True |
| data/futures/DASH_USDT_USDT-4h-futures.feather | 14674 | 2020-02-04T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/DASH_USDT_USDT-1h-mark.feather | 58622 | 2020-02-04T05:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/DASH_USDT_USDT-1h-funding_rate.feather | 7326 | 2020-02-04T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7325} | True |
| data/futures/DOGE_USDT_USDT-4h-futures.feather | 13732 | 2020-07-10T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/DOGE_USDT_USDT-1h-mark.feather | 54856 | 2020-07-10T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/DOGE_USDT_USDT-1h-funding_rate.feather | 6855 | 2020-07-10T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6854} | True |
| data/futures/DOT_USDT_USDT-4h-futures.feather | 13475 | 2020-08-22T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/DOT_USDT_USDT-1h-mark.feather | 53873 | 2020-08-20T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/DOT_USDT_USDT-1h-funding_rate.feather | 6732 | 2020-08-20T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6731} | True |
| data/futures/EGLD_USDT_USDT-4h-futures.feather | 13337 | 2020-09-14T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/EGLD_USDT_USDT-1h-mark.feather | 53288 | 2020-09-13T11:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/EGLD_USDT_USDT-1h-funding_rate.feather | 6659 | 2020-09-13T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6658} | True |
| data/futures/ENJ_USDT_USDT-4h-futures.feather | 13247 | 2020-09-29T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ENJ_USDT_USDT-1h-mark.feather | 52913 | 2020-09-29T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ENJ_USDT_USDT-1h-funding_rate.feather | 7507 | 2020-09-29T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 5989, "14400": 1156, "3600": 359, "10800": 1, "7200": 1} | True |
| data/futures/ENS_USDT_USDT-4h-futures.feather | 10686 | 2021-11-30T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ENS_USDT_USDT-1h-mark.feather | 42683 | 2021-11-29T08:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ENS_USDT_USDT-1h-funding_rate.feather | 5333 | 2021-11-29T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 5332} | True |
| data/futures/ETC_USDT_USDT-4h-futures.feather | 14788 | 2020-01-16T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ETC_USDT_USDT-1h-mark.feather | 59077 | 2020-01-16T06:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ETC_USDT_USDT-1h-funding_rate.feather | 7383 | 2020-01-16T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7382} | True |
| data/futures/ETH_USDT_USDT-4h-futures.feather | 14880 | 2020-01-01T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ETH_USDT_USDT-1h-mark.feather | 59443 | 2020-01-01T00:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ETH_USDT_USDT-1h-funding_rate.feather | 7429 | 2020-01-01T00:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7428} | True |
| data/futures/FET_USDT_USDT-4h-futures.feather | 8208 | 2023-01-17T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/FET_USDT_USDT-1h-mark.feather | 32773 | 2023-01-16T06:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/FET_USDT_USDT-1h-funding_rate.feather | 4095 | 2023-01-16T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 4094} | True |
| data/futures/FIL_USDT_USDT-4h-futures.feather | 13145 | 2020-10-16T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/FIL_USDT_USDT-1h-mark.feather | 52505 | 2020-10-16T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/FIL_USDT_USDT-1h-funding_rate.feather | 6561 | 2020-10-16T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6560} | True |
| data/futures/GRT_USDT_USDT-4h-futures.feather | 12761 | 2020-12-19T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/GRT_USDT_USDT-1h-mark.feather | 50966 | 2020-12-19T05:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/GRT_USDT_USDT-1h-funding_rate.feather | 6369 | 2020-12-19T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6368} | True |
| data/futures/HBAR_USDT_USDT-4h-futures.feather | 12233 | 2021-03-17T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/HBAR_USDT_USDT-1h-mark.feather | 48856 | 2021-03-17T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/HBAR_USDT_USDT-1h-funding_rate.feather | 6105 | 2021-03-17T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6104} | True |
| data/futures/ICP_USDT_USDT-4h-futures.feather | 8880 | 2022-09-27T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ICP_USDT_USDT-1h-mark.feather | 47537 | 2021-05-11T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ICP_USDT_USDT-1h-funding_rate.feather | 5940 | 2021-05-11T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 5939} | True |
| data/futures/INJ_USDT_USDT-4h-futures.feather | 9126 | 2022-08-17T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/INJ_USDT_USDT-1h-mark.feather | 36443 | 2022-08-16T08:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/INJ_USDT_USDT-1h-funding_rate.feather | 4553 | 2022-08-16T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 4552} | True |
| data/futures/IOST_USDT_USDT-4h-futures.feather | 14572 | 2020-02-21T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/IOST_USDT_USDT-1h-mark.feather | 58256 | 2020-02-19T11:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/IOST_USDT_USDT-1h-funding_rate.feather | 7477 | 2020-02-21T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 7178, "14400": 160, "3600": 137, "10800": 1} | True |
| data/futures/IOTA_USDT_USDT-4h-futures.feather | 14626 | 2020-02-12T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/IOTA_USDT_USDT-1h-mark.feather | 58431 | 2020-02-12T04:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/IOTA_USDT_USDT-1h-funding_rate.feather | 7302 | 2020-02-12T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7301} | True |
| data/futures/JASMY_USDT_USDT-4h-futures.feather | 9840 | 2022-04-20T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/JASMY_USDT_USDT-1h-mark.feather | 39304 | 2022-04-19T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/JASMY_USDT_USDT-1h-funding_rate.feather | 4911 | 2022-04-19T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 4910} | True |
| data/futures/KAVA_USDT_USDT-4h-futures.feather | 13625 | 2020-07-28T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/KAVA_USDT_USDT-1h-mark.feather | 54424 | 2020-07-28T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/KAVA_USDT_USDT-1h-funding_rate.feather | 8559 | 2020-07-28T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 5791, "14400": 1772, "3600": 994, "7200": 1} | True |
| data/futures/KNC_USDT_USDT-4h-futures.feather | 13840 | 2020-06-22T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/KNC_USDT_USDT-1h-mark.feather | 55285 | 2020-06-22T06:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/KNC_USDT_USDT-1h-funding_rate.feather | 6909 | 2020-06-22T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6908} | True |
| data/futures/KSM_USDT_USDT-4h-futures.feather | 13157 | 2020-10-14T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/KSM_USDT_USDT-1h-mark.feather | 52552 | 2020-10-14T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/KSM_USDT_USDT-1h-funding_rate.feather | 6567 | 2020-10-14T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6566} | True |
| data/futures/LDO_USDT_USDT-4h-futures.feather | 8907 | 2022-09-22T12:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/LDO_USDT_USDT-1h-mark.feather | 35561 | 2022-09-22T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/LDO_USDT_USDT-1h-funding_rate.feather | 4443 | 2022-09-22T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 4442} | True |
| data/futures/LINK_USDT_USDT-4h-futures.feather | 14782 | 2020-01-17T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/LINK_USDT_USDT-1h-mark.feather | 59052 | 2020-01-17T07:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/LINK_USDT_USDT-1h-funding_rate.feather | 7380 | 2020-01-17T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7379} | True |
| data/futures/LTC_USDT_USDT-4h-futures.feather | 14830 | 2020-01-09T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/LTC_USDT_USDT-1h-mark.feather | 59247 | 2020-01-09T04:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/LTC_USDT_USDT-1h-funding_rate.feather | 7404 | 2020-01-09T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7403} | True |
| data/futures/NEAR_USDT_USDT-4h-futures.feather | 13150 | 2020-10-15T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/NEAR_USDT_USDT-1h-mark.feather | 52546 | 2020-10-14T09:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/NEAR_USDT_USDT-1h-funding_rate.feather | 6566 | 2020-10-14T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6565} | True |
| data/futures/NEO_USDT_USDT-4h-futures.feather | 14596 | 2020-02-17T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/NEO_USDT_USDT-1h-mark.feather | 58311 | 2020-02-17T04:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/NEO_USDT_USDT-1h-funding_rate.feather | 7287 | 2020-02-17T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7286} | True |
| data/futures/ONT_USDT_USDT-4h-futures.feather | 14632 | 2020-02-11T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ONT_USDT_USDT-1h-mark.feather | 58454 | 2020-02-11T05:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ONT_USDT_USDT-1h-funding_rate.feather | 8644 | 2020-02-11T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 6440, "14400": 1573, "3600": 628, "7200": 2} | True |
| data/futures/PENDLE_USDT_USDT-4h-futures.feather | 7056 | 2023-07-28T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/PENDLE_USDT_USDT-1h-mark.feather | 28210 | 2023-07-25T09:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/PENDLE_USDT_USDT-1h-funding_rate.feather | 3524 | 2023-07-25T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 3523} | True |
| data/futures/QNT_USDT_USDT-4h-futures.feather | 8742 | 2022-10-20T00:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/QNT_USDT_USDT-1h-mark.feather | 34890 | 2022-10-20T01:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/QNT_USDT_USDT-1h-funding_rate.feather | 4359 | 2022-10-20T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 4358} | True |
| data/futures/QTUM_USDT_USDT-4h-futures.feather | 14578 | 2020-02-20T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/QTUM_USDT_USDT-1h-mark.feather | 58256 | 2020-02-19T11:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/QTUM_USDT_USDT-1h-funding_rate.feather | 7280 | 2020-02-19T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7279} | True |
| data/futures/RENDER_USDT_USDT-4h-futures.feather | 4870 | 2024-07-26T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/RENDER_USDT_USDT-1h-mark.feather | 19402 | 2024-07-26T09:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/RENDER_USDT_USDT-1h-funding_rate.feather | 4848 | 2024-07-26T12:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"14400": 4846, "28800": 1} | True |
| data/futures/RLC_USDT_USDT-4h-futures.feather | 13607 | 2020-07-31T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/RLC_USDT_USDT-1h-mark.feather | 54353 | 2020-07-31T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/RLC_USDT_USDT-1h-funding_rate.feather | 6874 | 2020-07-31T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 6772, "3600": 80, "14400": 21} | True |
| data/futures/RSR_USDT_USDT-4h-futures.feather | 13127 | 2020-10-19T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/RSR_USDT_USDT-1h-mark.feather | 52430 | 2020-10-19T05:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/RSR_USDT_USDT-1h-funding_rate.feather | 6552 | 2020-10-19T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6551} | True |
| data/futures/RUNE_USDT_USDT-4h-futures.feather | 13397 | 2020-09-04T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/RUNE_USDT_USDT-1h-mark.feather | 53512 | 2020-09-04T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/RUNE_USDT_USDT-1h-funding_rate.feather | 6687 | 2020-09-04T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6686} | True |
| data/futures/SKL_USDT_USDT-4h-futures.feather | 12827 | 2020-12-08T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/SKL_USDT_USDT-1h-mark.feather | 51231 | 2020-12-08T04:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/SKL_USDT_USDT-1h-funding_rate.feather | 7554 | 2020-12-08T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 5453, "14400": 1832, "3600": 268} | True |
| data/futures/SNX_USDT_USDT-4h-futures.feather | 13523 | 2020-08-14T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/SNX_USDT_USDT-1h-mark.feather | 54016 | 2020-08-14T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/SNX_USDT_USDT-1h-funding_rate.feather | 6750 | 2020-08-14T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6749} | True |
| data/futures/SOL_USDT_USDT-4h-futures.feather | 13337 | 2020-09-14T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/SOL_USDT_USDT-1h-mark.feather | 53288 | 2020-09-13T11:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/SOL_USDT_USDT-1h-funding_rate.feather | 6734 | 2020-09-13T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6632, "7200": 98, "14400": 3} | True |
| data/futures/STX_USDT_USDT-4h-futures.feather | 7995 | 2023-02-21T12:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/STX_USDT_USDT-1h-mark.feather | 31912 | 2023-02-21T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/STX_USDT_USDT-1h-funding_rate.feather | 3987 | 2023-02-21T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 3986} | True |
| data/futures/SUN_USDT_USDT-4h-futures.feather | 4707 | 2024-08-22T12:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/SUN_USDT_USDT-1h-mark.feather | 18751 | 2024-08-22T12:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/SUN_USDT_USDT-1h-funding_rate.feather | 4685 | 2024-08-22T16:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"14400": 4683, "28800": 1} | True |
| data/futures/SUSHI_USDT_USDT-4h-futures.feather | 13397 | 2020-09-04T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/SUSHI_USDT_USDT-1h-mark.feather | 53512 | 2020-09-04T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/SUSHI_USDT_USDT-1h-funding_rate.feather | 6687 | 2020-09-04T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6686} | True |
| data/futures/THETA_USDT_USDT-4h-futures.feather | 13996 | 2020-05-27T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/THETA_USDT_USDT-1h-mark.feather | 55928 | 2020-05-26T11:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/THETA_USDT_USDT-1h-funding_rate.feather | 6989 | 2020-05-26T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6988} | True |
| data/futures/TRB_USDT_USDT-4h-futures.feather | 13403 | 2020-09-03T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/TRB_USDT_USDT-1h-mark.feather | 53537 | 2020-09-03T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/TRB_USDT_USDT-1h-funding_rate.feather | 9979 | 2020-09-03T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"14400": 6575, "28800": 3403} | True |
| data/futures/TRX_USDT_USDT-4h-futures.feather | 14794 | 2020-01-15T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/TRX_USDT_USDT-1h-mark.feather | 59104 | 2020-01-15T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/TRX_USDT_USDT-1h-funding_rate.feather | 7386 | 2020-01-15T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7385} | True |
| data/futures/UNI_USDT_USDT-4h-futures.feather | 13313 | 2020-09-18T04:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/UNI_USDT_USDT-1h-mark.feather | 53196 | 2020-09-17T07:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/UNI_USDT_USDT-1h-funding_rate.feather | 6648 | 2020-09-17T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6647} | True |
| data/futures/VET_USDT_USDT-4h-futures.feather | 14614 | 2020-02-14T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/VET_USDT_USDT-1h-mark.feather | 58384 | 2020-02-14T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/VET_USDT_USDT-1h-funding_rate.feather | 7296 | 2020-02-14T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7295} | True |
| data/futures/XLM_USDT_USDT-4h-futures.feather | 14764 | 2020-01-20T08:00:00+00:00 | 2026-10-15T20:00:00+00:00 | 0 | 0 | True |
| data/futures/XLM_USDT_USDT-1h-mark.feather | 59002 | 2020-01-19T09:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/XLM_USDT_USDT-1h-funding_rate.feather | 7373 | 2020-01-19T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7372} | True |
| data/futures/XMR_USDT_USDT-4h-futures.feather | 12474 | 2020-02-03T08:00:00+00:00 | 2025-10-13T04:00:00+00:00 | 0 | 0 | True |
| data/futures/XMR_USDT_USDT-1h-mark.feather | 59002 | 2020-01-19T09:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/XMR_USDT_USDT-1h-funding_rate.feather | 7373 | 2020-01-19T16:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7372} | True |
| data/futures/XRP_USDT_USDT-4h-futures.feather | 12474 | 2020-01-06T08:00:00+00:00 | 2025-09-15T04:00:00+00:00 | 0 | 0 | True |
| data/futures/XRP_USDT_USDT-1h-mark.feather | 59320 | 2020-01-06T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/XRP_USDT_USDT-1h-funding_rate.feather | 7413 | 2020-01-06T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7412} | True |
| data/futures/XTZ_USDT_USDT-4h-futures.feather | 12474 | 2020-02-06T08:00:00+00:00 | 2025-10-16T04:00:00+00:00 | 0 | 0 | True |
| data/futures/XTZ_USDT_USDT-1h-mark.feather | 58622 | 2020-02-04T05:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/XTZ_USDT_USDT-1h-funding_rate.feather | 8713 | 2020-02-04T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 5980, "14400": 2680, "3600": 52} | True |
| data/futures/YFI_USDT_USDT-4h-futures.feather | 11476 | 2020-08-31T04:00:00+00:00 | 2025-11-25T16:00:00+00:00 | 0 | 0 | True |
| data/futures/YFI_USDT_USDT-1h-mark.feather | 53606 | 2020-08-31T05:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/YFI_USDT_USDT-1h-funding_rate.feather | 6699 | 2020-08-31T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6698} | True |
| data/futures/ZEC_USDT_USDT-4h-futures.feather | 12474 | 2020-02-05T08:00:00+00:00 | 2025-10-15T04:00:00+00:00 | 0 | 0 | True |
| data/futures/ZEC_USDT_USDT-1h-mark.feather | 58622 | 2020-02-04T05:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ZEC_USDT_USDT-1h-funding_rate.feather | 7326 | 2020-02-04T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 7325} | True |
| data/futures/ZEN_USDT_USDT-4h-futures.feather | 10977 | 2020-11-24T04:00:00+00:00 | 2025-11-27T12:00:00+00:00 | 0 | 0 | True |
| data/futures/ZEN_USDT_USDT-1h-mark.feather | 51568 | 2020-11-24T03:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ZEN_USDT_USDT-1h-funding_rate.feather | 6444 | 2020-11-24T08:00:00+00:00 | 2026-10-12T00:00:00+00:00 | 0 | {"28800": 6443} | True |
| data/futures/ZIL_USDT_USDT-4h-futures.feather | 11476 | 2020-06-18T08:00:00+00:00 | 2025-09-12T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ZIL_USDT_USDT-1h-mark.feather | 55404 | 2020-06-17T07:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ZIL_USDT_USDT-1h-funding_rate.feather | 7848 | 2020-06-17T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 6170, "14400": 1453, "3600": 224} | True |
| data/futures/ZRX_USDT_USDT-4h-futures.feather | 11476 | 2020-06-24T08:00:00+00:00 | 2025-09-18T20:00:00+00:00 | 0 | 0 | True |
| data/futures/ZRX_USDT_USDT-1h-mark.feather | 55241 | 2020-06-24T02:00:00+00:00 | 2026-10-12T18:00:00+00:00 | 0 | 0 | True |
| data/futures/ZRX_USDT_USDT-1h-funding_rate.feather | 7894 | 2020-06-24T08:00:00+00:00 | 2026-10-12T12:00:00+00:00 | 0 | {"28800": 6046, "14400": 1671, "3600": 176} | True |

Funding 文件名 1h 是原生存储键，不表示每小时付款。变频事件明确待核实，不补造缺失事件。精确区间、非法值、标签及 SHA 见配套 JSON。
