# Phase 4：原生回测完全离线端到端验收

阶段状态：**PASS（最低 BTC/ETH 范围）**。本轮实际执行于 2026-10-17 13:03 UTC；只有在 Phase 2 严格配置比较修复和 Phase 3 最低范围门槛通过之后才启动。全币种和更长区间未验收。

## 验收表

| 验收项 | 执行命令或检查方式 | 预期 | 实际 | 证据 | 状态 |
|---|---|---|---|---|---|
| 数据/快照范围准入 | runner 校验 Phase 3 exact scope、配置/快照/行情 SHA | BTC/ETH、20250101-20250115 原始数据完整 | scope、哈希一致 | [数据清单](phase3_data_coverage.json)、[summary](phase4_summary.json) | PASS |
| 空缓存与原生生命周期 | 新建空 userdir，`--cache none --export signals` | 重新训练、预测、交易及导出 | 4 次 Done training、4 metadata、4 prediction | [完整日志](phase4_backtest.log) | PASS |
| 系统级断网 | `unshare --user --map-root-user --net` | 不依赖宿主网络 | 完整回测退出 0 | [summary](phase4_summary.json) | PASS |
| Python 审计 | `audit_local_network.py --policy deny-all` | HTTP/DNS/IP socket/拒绝事件均 0 | 全为 0；无子进程事件 | [审计](phase4_backtest_network.json) | PASS |
| 系统调用审计 | `strace -f -e trace=network` | 无外部 connect/send | 全部 connect/send 为 0 | [strace](phase4_backtest_network.strace) | PASS |
| 完整回归 | 原始参考与本轮原始工件 `compare_runs` | 交易、嵌套订单、signals/rejected/exited、预测、全部 metadata/结果配置/指标相同 | `passed=true`，differences=[] | [原始比较报告的脱敏副本](phase4_regression.json) | PASS |
| 发布工件可复验 | 两侧采用相同根路径脱敏后重新严格比较 | 发布不会掩盖或引入语义差异 | 再次 differences=[] | [发布后复验](phase4_published_replay.json) | PASS |

aiohttp 导入阶段仅创建一次 IPv6 socket、尝试 `bind(::1)` 并返回 EADDRNOTAVAIL；没有 connect、DNS 或发送数据。命名空间隔离、Python 拦截和系统调用观察各自作用不同，本报告没有把 Python mock 当作系统级验收。

## 结果与参考

| 项目 | 历史真实联网参考 | 本轮全新离线运行 |
|---|---:|---:|
| 交易 / 订单 | 13 / 26 | 13 / 26 |
| 总盈亏 USDT | -7.72891548 | -7.72891548 |
| 最终余额 USDT | 992.27108452 | 992.27108452 |
| Sharpe | -2.4156875909722673 | -2.4156875909722673 |
| 最大账户回撤 | 0.019077787162898503 | 0.019077787162898503 |
| 模型 metadata / 预测文件 | 4 / 4 | 4 / 4 |
| 各模型特征数 | 92 | 92 |

92 从本轮和参考真实 metadata 推导，未作为策略默认值写入验收工具。每个预测文件 42 行，四份预测文件 SHA 与参考全部一致。标签、训练窗口和逐列特征顺序也完整比较。

参考来自原有 `native-online-reference.tar.gz`，其历史网络审计明确记录一个真实 `fapi exchangeInfo` 请求。本轮**没有重新联网生成参考**，也没有将参考缓存用于训练。runner 从可信归档解出参考到独立目录，仅供结果比较。未经信任的 joblib/模型归档不可用此工具加载。

严格比较保留原容差 `rtol=atol=1e-12`；完整嵌套交易/订单、全部模型 metadata 和有效配置严格比较。仅排除与历史交易无关的 `backtest_run_start_ts/end_ts`。`config_files` 仅规范 checkout 根，保留原生记录顺序；metadata 先验证 `data_path` 后只规范独立 userdir 根。无额外 transport 参数豁免。

本轮离线也加载 `configs/environment/freqtrade-mihomo.json`，使 exported config 与可信在线参考完全一致。该 overlay 的代理/timeout 只用于保持对照条件，离线客户端传输拒绝与网络命名空间仍生效；离线使用不依赖代理服务。

## 工件与脱敏

- [本轮 native ZIP、全部预测及 metadata 归档](phase4_artifacts.tar.gz)
- [相同脱敏规则的参考副本](phase4_reference_artifacts.tar.gz)
- [运行/训练/网络/版本/原始与发布 SHA 清单](phase4_summary.json)

原始工件上严格比较先通过，随后仅替换 UTF-8 日志、JSON 和 ZIP config 中的本机根路径。交易字段、数值、信号 pickle、预测 Feather 均保留；每项原始/发布 SHA 和是否脱敏逐项公开。发布后的两侧归档再次通过完整比较。旧参考与历史证据保留原样，未删除。

发布检查重新核验 Phase 4–5 共 78 项 SHA，并解包扫描全部新归档内的文本/ZIP config，没有本机私有根路径泄漏，见[工件校验](phase5_evidence_validation.json)。

## 从项目根重新执行

先将 `FREQTRADE_PYTHON` 设置为当前已安装 Freqtrade 2026.7 / CCXT 4.5.75 的 Python 可执行文件。命令创建全新输出目录；已有证据不会覆盖。

```bash
export PYTHONPATH=src:.
ACCEPTANCE_OUTPUT=$(mktemp -d)
"$FREQTRADE_PYTHON" tools/run_offline_acceptance.py phase4 \
  --coverage docs/acceptance/phase3_data_coverage.json \
  --output "$ACCEPTANCE_OUTPUT"
```

runner 自动创建另一空 userdir，使用真实 `data/`，显式禁用结果缓存，并调用原生 `Backtesting.start()`。快照固定验收时效显式为 36500 天；这是冻结实验输入，生产入口默认仍为 30 天，不应把长期验收例外当作生产规则。

持久工件复验可在任意全新目录进行：

```bash
REPLAY_ROOT=$(mktemp -d)
mkdir "$REPLAY_ROOT/reference" "$REPLAY_ROOT/offline"
tar -xzf docs/acceptance/phase4_reference_artifacts.tar.gz -C "$REPLAY_ROOT/reference"
tar -xzf docs/acceptance/phase4_artifacts.tar.gz -C "$REPLAY_ROOT/offline"
"$FREQTRADE_PYTHON" tools/verify_freqtrade_regression.py \
  "$REPLAY_ROOT/reference" "$REPLAY_ROOT/offline" \
  --report "$REPLAY_ROOT/regression.json"
```

## 变更、测试统计与准入

新增 `tools/run_offline_acceptance.py`，只编排验收，不修改交易所/CCXT/策略全局状态。新增发布工件、日志和本报告；未删除文件。策略与模型语义无变化。

本阶段 E2E：1 次运行通过、0 失败、0 skipped；系统级隔离实际执行。Phase 5 共用边界工具的最终单元/集成统计见下一阶段 JUnit，全量统计由 Phase 6 汇总。HTTP/DNS/外部 socket 请求 0；13 笔交易、26 个订单、4 个预测文件，严格回归差异 0。

发布重放首次把脱敏离线工件与未脱敏旧参考直接比较，准确报告 `configuration/datadir` 路径差异；没有弱化比较器，改为发布相同根脱敏的参考副本后重放通过。原始回归一直严格通过。

未验收：其他交易对、更长窗口、不同机器/CPU/版本的数值重现；当前快照不代表 2025 年历史真实市场规则。本阶段最低门槛通过，允许进入 Phase 5。

资料：Linux `unshare(1)`、`strace(1)`，Python `sys.addaudithook`，仓库 [既有离线设计](../offline_backtest_snapshot.md) 及实际安装的原生 `Backtesting`。
