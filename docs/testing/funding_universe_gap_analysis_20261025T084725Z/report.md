# Funding / Point-in-Time Universe 真实证据缺口分析

生成时间：2026-10-25T08:47:25Z UTC。

## 基线

- 实际仓库路径：`/home/wangke/project/FreqtradeStratege`。
- 分支：`main`。
- HEAD 与 `origin/main`：`6c3b515876b612e659668b41594e826f348ed74c`。
- 工作区原有修改和未跟踪文件均保留。
- 未训练、未运行正式 OOS/P3–P6、未访问 final holdout、未执行 Git 发布。

用户给出的 `/data/wangke/project/FreqtradeStratege` 在当前环境不存在，因此使用实际存在的 `/home/wangke/project/FreqtradeStratege`。

## 官方来源检索结果

已核查的官方来源：

1. Binance Public Data README：`https://github.com/binance/binance-public-data/blob/master/README.md`
2. Binance Vision Funding 静态归档：BTCUSDT 2020-01、ETHUSDT 2020-01、BNBUSDT 2020-02。
3. Binance 当前 `exchangeInfo` 快照来源说明：`https://fapi.binance.com/fapi/v1/exchangeInfo`。
4. Binance 官方公告入口：`https://www.binance.com/en/support/announcement`。

README 明确说明 Binance Public Data 按 daily/monthly 聚合，并说明月度数据的发布节奏，但没有定义 Funding `calc_time` 是支付完成时间，也没有给出历史 Funding 规则变更或完整覆盖证明。Binance Support 页面在本环境 TLS 连接被重置；S3 对象前缀清单请求超时，未将失败请求当成覆盖证据。

## Funding 缺口

上一轮保存的三份官方 ZIP/CSV 已复核，字段为 `calc_time`、`funding_interval_hours`、`last_funding_rate`，共 245 条记录。原始哈希和 CSV 记录一致性仍通过。

对三币的结论均相同：

- 来源文件完整性：`PASS`。
- 费率字段和记录时间可解析：`PASS`。
- 实际支付事件语义：`BLOCKED`。官方静态 CSV 没有支付确认字段，README 未定义 `calc_time` 为支付完成时间。
- 历史结算规则：`BLOCKED`。`funding_interval_hours=8` 是记录字段，不能单独证明历史规则版本或规则生效区间。
- 独立历史覆盖：`BLOCKED`。只保存一个月样本，未获得官方归档文件清单或独立范围证明。
- 未证明窗口：BTC/ETH 的本地 Funding 研究窗口为 2020-01-01 至 2026-10-12；BNB 为 2020-02-10 至 2026-10-12。

详细矩阵见 [funding_gap_matrix.json](funding_gap_matrix.json)。

## Point-in-Time Universe 缺口

现有 Binance 快照只证明 2026-10-17 快照时的状态和 onboard 字段。未找到能够在不调用 API 的约束下覆盖 BTCUSDT、ETHUSDT、BNBUSDT 全历史的官方静态上市、暂停、恢复、迁移和下架状态档案。

使用本地 4h candle 日期列逐点做 as-of 检查：

- BTCUSDT：14880 个 candle，2020-01-01 至 2026-10-15，历史状态未知。
- ETHUSDT：14880 个 candle，2020-01-01 至 2026-10-15，历史状态未知。
- BNBUSDT：14638 个 candle，2020-02-10 至 2026-10-15，历史状态未知。

当前快照、行情文件存在、当前 pair whitelist 均未被用于填补历史状态。详细矩阵见 [universe_gap_matrix.json](universe_gap_matrix.json)。

## 验证器与回归

- `tests/unit/test_evidence_packages.py`：22 passed。
- `tests/unit/test_controlled_governance.py`：21 passed。
- Python 编译检查：退出码 0。
- `git diff --check`：退出码 0。
- Ruff：UNAVAILABLE，本地没有 Ruff。

验证器的结构、哈希、权威性和历史覆盖状态仍被分开；来源搜索完成不会自动生成 `FORMAL_ADMISSION_READY`。

## 最终状态

| 项目 | 状态 |
|---|---|
| Funding 来源权威性 | BLOCKED |
| Funding 支付事件语义 | BLOCKED |
| Funding 历史规则 | BLOCKED |
| Funding 独立覆盖 | BLOCKED |
| Universe 来源权威性 | BLOCKED |
| Universe 历史状态 | BLOCKED |
| Universe candle 覆盖 | BLOCKED |
| 验证器回归 | PASS |
| 正式研究准入 | BLOCKED |

当前没有足够官方材料把任何一个证据域升级为正式可用。下一步必须取得可验证的历史支付语义/规则材料和逐合约历史状态档案；在此之前不能解除正式研究锁定。

命令和网络行为见 [commands.json](commands.json)，测试回执见 [test_results.json](test_results.json)，来源与原始文件索引见 [source_inventory.json](source_inventory.json)。
