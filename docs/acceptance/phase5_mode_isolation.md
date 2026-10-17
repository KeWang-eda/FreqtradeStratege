# Phase 5：研究引擎与原生交易边界验收

阶段状态：**PASS（本地研究与原生客户端边界）**。在 Phase 4 最低范围 PASS 后，于 2026-10-17 13:06 UTC 实际执行；不代表真实账户、订单或长期 dry-run 已验收。

## 验收表

| 验收项 | 命令或检查方式 | 预期 | 实际 | 证据 | 状态 |
|---|---|---|---|---|---|
| 真实研究配置/数据 | base→local 的 validate、dataset-build | BTC/ETH 本地文件可用 | 29706 样本、26 特征 | [dataset 日志](phase5_dataset_build.log)、[summary](phase5_summary.json) | PASS |
| 训练/CV/预测评估 | 原配置 ridge、xgboost 两次 `run` | 完整训练、3 folds | 每个模型 3 folds、18934 预测行、manifest complete | [summary](phase5_summary.json)、[工件](phase5_artifacts.tar.gz) | PASS |
| 模型比较 | `compare ridge xgboost` | 两个真实实验、各 3 folds | 完整 metrics 与 dataset/input/folds 指纹 | [compare](phase5_compare.log) | PASS |
| 研究无交易所初始化依赖 | 每个进程 audit imports | 不导入 FT/CCXT | 全部 false | [summary](phase5_summary.json) | PASS |
| 研究系统级断网 | 全部命令 unshare+strace+deny-all | HTTP/DNS/IP/外部发送均 0 | 全为 0 | 各 `phase5_*_network.json/.strace` | PASS |
| 原装回测未注入快照 | native backtesting，网络拒绝 | 原生 fapi 初始化明确失败 | exit 2、1 个被拒 fapi 请求、无 ZIP | [native audit](phase5_native_network.json)、[日志](phase5_native.log) | PASS |
| LIVE/DRY_RUN 原生链路 | ExchangeResolver 实际构造，在市场加载前 test spy 截止 | Binance、原生 sync/pro async 与凭证路径保留 | 两种模式均 native；LIVE 保留占位凭证、DRY_RUN 原生移除 | [JUnit](phase5_boundary_pytest.xml) | PASS |
| 导入无全局副作用 | 独立 Python 前后 class/method identity | FT/CCXT/resolver identity 不变 | 一致 | [JUnit](phase5_boundary_pytest.xml) | PASS |
| CLI 覆盖/userdir | 原生 Arguments+setup 函数 | 后配置/CLI 优先，独立 userdir | 参数顺序、pairs、cache none、export signals、RunMode 正确 | [JUnit](phase5_boundary_pytest.xml) | PASS |
| syscall/gate 负测 | IP/其他 Unix/成功 nscd connect、wrong scope | 明确拒绝 | 均触发异常 | [JUnit](phase5_boundary_pytest.xml) | PASS |

## 运行模式矩阵

| 入口 | 数据/市场加载 | 本轮实际覆盖 | 限制 |
|---|---|---|---|
| 独立研究 `validate/dataset-build/run/compare` | 本地行情；无 FT/CCXT import | 真实 BTC/ETH、ridge/xgboost、3fold，OS 断网 | 未验收其他后端与全币种 |
| 显式 `offline_backtest backtesting` | 本地行情+可信快照；guard 拒绝 HTTP | Phase 4 全生命周期 | 只支持指定版本与 Binance USDT futures isolated 静态 pairs |
| 原装 `freqtrade backtesting` | 原生市场初始化 | deny-all 下真实 fapi 请求被拒并安全退出 | 未在本轮重新联网跑参考 |
| 原装 `freqtrade trade` LIVE | 原生 Binance+CCXT+凭证路径 | 受控构造边界 test spy，市场加载前截止 | 没有账户或订单接口实际验收 |
| 原装 `freqtrade trade` DRY_RUN | 原生 Binance+CCXT；保留原生凭证处理 | 同上 | 未运行长期模拟交易 |

离线适配器仅由显式专用入口创建。该模块导入前后，原生 `Binance._init_ccxt/_api_reload_markets`、CCXT sync/pro class/fetch 以及 ExchangeResolver 方法保持相同对象。LIVE、DRY_RUN 和 HYPEROPT 拒绝离线构造的用例在 Phase 1–2 已覆盖，本阶段补充普通路径客户端/凭证观察。

## 审计范围与本地 IPC

研究训练为保存 provenance，仅准许三个固定只读 Git 子进程；每次 run 均记录 3 个准许事件，无其他被准许 child。`strace -f` 跟踪父子进程；Python 审计不宣称覆盖 C 库系统调用。

每次研究 `run` 记录 4 次 `AF_UNIX /var/run/nscd/socket → ENOENT`。这是 Python `tarfile.gettarinfo()` 在快照源码时调用 `pwd/grp`，glibc 查询本地姓名缓存失败；不是外部 DNS/IP 发送。已用最小 `tarfile.add(config.json)` 在独立网络命名空间中复现，[原始系统调用副本](phase5_attempt1_nscd_probe.strace)。仅此路径且仅 ENOENT 被单列解释；成功连接 nscd、其他 Unix socket 和所有 IP connect/send 仍导致验收失败。每个研究任务的 HTTP、Python DNS/IP events 和外部 connect/send 均为 0。

首次 Phase 5 runner 过度严格地把这些本地失败探测当作外部网络而标 FAIL；原始失败证据完整保留为 `phase5_attempt1_*`，包括 [失败 summary](phase5_attempt1_summary.json)。修复的是验收工具分类，未修改研究数据、训练、策略、网络客户端或生产逻辑。第二轮重新建立全新实验目录、重新训练并完成全部任务，没有复用失败轮缓存。

## 可复制命令

在项目根将 `FREQTRADE_PYTHON` 指向已安装指定版本的 Python：

```bash
export PYTHONPATH=src:.
ACCEPTANCE_OUTPUT=$(mktemp -d)
"$FREQTRADE_PYTHON" tools/run_offline_acceptance.py phase5 --output "$ACCEPTANCE_OUTPUT"
"$FREQTRADE_PYTHON" -m pytest -q \
  tests/integration/test_mode_isolation_acceptance.py \
  --junitxml="$ACCEPTANCE_OUTPUT/mode-isolation.xml"
```

runner 实际对子进程分别执行系统隔离+Python audit，而不是在联网的 runner 内直接训练。普通回测的非零退出是模式边界的预期结果，不能解释为离线入口失败。固定配置、每个具体命令、时间、依赖版本、SHA、研究指标与网络事件均在 [summary](phase5_summary.json) 中。

## 变更、真实测试与下一阶段

新增 `tests/integration/test_mode_isolation_acceptance.py`；新增 runner 和 Phase 5 证据/报告；未删除旧测试或证据。生产策略、模型、标签、特征、风险参数和交易逻辑均未变。

最终边界测试 **16 passed、0 failed、0 skipped**；[日志](phase5_boundary_pytest.log)、[JUnit](phase5_boundary_pytest.xml)。[Lint](phase5_lint.log) 与[格式](phase5_format.log)通过。开发期两次测试分别 9 passed/1 failed，原因是测试漏传原生 FreqAI 所需 timerange、误认为 config_files 正序；按真实源码修正断言后通过，没有放宽生产校验。

真实命令验收：5 个研究任务成功；1 个 native backtest 按预期拒绝联网；0 skipped。研究网络请求数 0，普通原生启动 1 个被拒 HTTP；本阶段没有交易或订单（Phase 4 为 13/26）。研究产出两份 predictions.parquet，各 18934 行；native 逐窗口预测数量见 Phase 4 的 4 文件。研究输入哈希、dataset/folds 哈希一致可追踪，无跨不同配置误称数值回归一致。

工件归档保存研究 manifest、folds、预测与 metrics 等可审阅输出，未把研究模型二进制当作原生交易验收；公开归档仅替换本机根路径，逐项 raw/published SHA 记在 summary。策略源文件最终完整指纹检查与全量测试由 Phase 6 汇总。

[发布工件校验](phase5_evidence_validation.json)实际重新校验 78 项 Phase 4–5 文件/归档成员 SHA，并扫描归档内 JSON/YAML/ZIP config，无私有根路径泄漏。

剩余未验证：真实账户认证、账户/订单接口、长期 dry-run、全币种/更长历史、多机器数值重现。没有实际下单、打印或使用 API Secret。边界门槛通过，可进入 Phase 6；上述未验证项不冒充实盘验收。

资料：Python `tarfile.gettarinfo` 的 pwd/grp 元数据行为、Linux `unshare(1)` 与 `strace(1)`，实际 Freqtrade 2026.7 `Exchange.__init__/_init_ccxt` 与 `load_from_files` 源码。
