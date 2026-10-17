# Phase 1：架构审查和离线边界加固

状态：**阶段门槛通过**。起点为[本轮 Phase 0](phase0_baseline.md)，不改变策略或交易参数。测试命令及原始失败记录均保留。

统一阶段状态：**PASS（含后续独立复核补修）**。

| 验收项 | 检查方式 | 预期 | 实际 | 证据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 非法快照 | 正反向真实响应合同测试 | 无默认值掩盖缺规则 | 缺/错规则、范围、版本、时间明确拒绝 | phase1_pytest.xml | PASS |
| 模式/生命周期 | preclient spy、构造/引擎失败注入 | 仅显式回测且释放资源 | 原生校验保留、loop/client 关闭 | phase1_pytest.xml、phase2_independent_review_pytest.xml | PASS |
| 网络边界 | Python 拒绝探针 + native netns | 无回退/不隐瞒拒绝 | 零网络真实回测，捕获拒绝仍非零 | phase1_pytest.xml、Phase 4 工件 | PASS |
| 严格 JSON 类型 | bool/int 市场 flags 负向复现 | 不得改变原生市场过滤 | canonical digest 对照拒绝伪装 bool/number | adapter_independent_review.md、phase2_independent_review_pytest.xml | PASS |

后续独立复核发现 Python dict 相等会把 `linear=1` 视为 `True`，而原生市场过滤使用 `is True`，这是实际阻断缺陷。已改为规范 JSON digest 对照 normalized、杠杆和恢复后的市场，并补四项类型负向测试。补修相关 **104 passed、0 failed、0 skipped**，包含完整原生断网回测。先期 82 项结果不是最终全量统计，最终全量以 Phase 6 为准。

新增/修改文件见下表和 Phase 2；无文件删除，无策略语义修改。最低原生验收仍为 13 交易、26 订单、4 预测文件、零网络。该阶段满足 Phase 2 准入；扩大币种/历史规则真实性仍是已披露限制。

## 发现、证据与修复

修复前的[可复现结果](phase1_before_fix_reproductions.json)显示：删除真实 BTC 响应中的 `PRICE_FILTER` 并重新计算解析值和哈希，旧加载器仍然接受；未知 envelope 字段也被接受。原因是 CCXT 在缺 filter 时可使用其他精度字段，单纯“重解析后相等”不能证明关键原始规则齐全。

| 边界 | 修复及验收 |
| --- | --- |
| 快照结构 | schema 1 envelope 严格字段集合，拒绝未知/缺字段；原始交易所响应允许保留其扩展字段，必需规则单独验证 |
| 范围 | 明确且唯一的 `BASE/USDT:USDT`，拒绝重复/模式表达式；raw symbol、解析 symbol 和 filter 类型不允许重复或歧义 |
| 原始规则 | 逐一检查 PRICE_FILTER、LOT_SIZE、MARKET_LOT_SIZE、最小 notional；有限正数、上下界顺序、USDT 永续身份与订单类型；不会补默认精度 |
| 合约大小 | normalized 缺失/变更会因真实重解析不一致失败；raw 若显式提供则必须有效。真实 Binance USDT 响应通常不提供此字段，保留原生 CCXT 将其解释为 1 的行为，不能要求一个真实响应不存在的字段或自行造值 |
| 杠杆 | 保留内置档位来源与文件哈希，新增非空、有限数值、有效区间验证；不连接账户接口 |
| 采集 | API 异常/超时转成明确采集失败；所有数据先完成解析、验证，再发布文件；已有文件或符号链接在请求之前拒绝 |
| 原子发布 | 同目录隐藏临时文件 → flush/fsync → `os.link` 原子且不覆盖地发布 → 同步目录；普通异常清理临时文件。进程被 SIGKILL 时可能遗留 `.tmp`，不会留下半写最终文件；加载器不扫描或自动选用临时文件 |
| 模式与客户端 | 预检先于客户端构造，拒绝非 BACKTEST、其他交易所/保证金模式、动态 PairList、模式交易对及改变 swap 范围的 CCXT 覆盖 |
| 资源 | 原生构造失败立即显式 close；同步客户端、异步客户端和独立事件循环清理，close 幂等；不依赖垃圾回收，运行中的外部事件循环明确拒绝 |
| 原生校验 | 仍执行 `super(..., validate=True, load_leverage_tiers=True)`；无效 7h 的原生校验实际失败；市场、费用、precision 和杠杆沿原路径 |

## 网络审计的三层边界

1. 运行适配层：普通 CCXT 子类在同步/异步 `fetch` 处拒绝 HTTP。全局 CCXT、Freqtrade 类不变，原装 backtesting 和 trade 不自动使用该子类。强制刷新只加载已验证内存快照，无联网回退。
2. Python 审计：requests/aiohttp HTTP，DNS 正/反向解析，connect、sendto、sendmsg 和子进程创建。即使被测任务捕获拒绝异常并返回 0，审计器也返回 **3**，不会冒充成功；安装失败、异常退出、完成状态有明确报告。任何报告写入失败本身也使进程失败。
3. OS 验收：Python hook 不能覆盖 C 库直接系统调用或被允许子进程内部的行为。完整回测使用独立 network namespace，并用 `strace -f` 检查所有线程/子进程；缺工具/权限的环境必须报告 skip/未验收。本机这次实际运行成功，无 skip。

新增“拒绝所有子进程”的第一次尝试产生 **1 failed / 81 passed**，原因是研究引擎正常的 Git 工件溯源被拦。没有删测试、忽略拒绝事件或放开所有子进程：现在只许可仓库自身三个固定只读 Git 命令，使用绝对可执行路径、`--no-pager`、禁用 fsmonitor，以及 diff 的 `--no-ext-diff --no-textconv`；其他 argv/子进程继续拒绝并记录。研究默认交易/模型行为不变，Git 溯源也不再执行用户配置的外部工具。原始[失败 JUnit](phase1_failed_attempt.xml)和[日志](phase1_failed_attempt.log)保留。

这不是针对恶意 Python/C 扩展的通用安全沙箱。要证明其不联网，仍必须使用 OS 网络隔离和跟踪；不能把 Python 零事件单独当作全进程无网络证据。

## 实际测试

```bash
PYTHONPATH=src "$FREQTRADE_PYTHON" -m pytest \
  tests/unit/test_snapshot_contract.py \
  tests/integration/test_offline_lifecycle.py \
  tests/integration/test_network_audit_boundary.py \
  tests/integration/test_offline_freqtrade.py \
  tests/integration/test_local_data_network.py -q \
  --junitxml=docs/acceptance/phase1_pytest.xml
```

结果：**82 passed，0 failed，0 skipped，37.79s**；[JUnit](phase1_pytest.xml)、[日志](phase1_pytest.log)。其中真实 BTC/ETH 原生离线回测重新训练并与联网历史参考逐项比较；没有重新请求市场快照。

测试覆盖真实响应缺 filters、未知字段、版本/时效/范围、原子写入中断、已有目标/并发发布、普通交易类保持原样、运行模式、预检前无客户端、构造失败释放、重复刷新，以及捕获 HTTP/DNS/socket/子进程拒绝后仍不得成功。

## 接口与升级规则

继续使用现有 `Backtesting(config, exchange=...)` 依赖注入；当前框架没有外部 Exchange 类路径配置，resolver 不支持通过配置注册本模块。内部 `_init_ccxt/_api_reload_markets` 只属于版本绑定的独立适配层，仍锁定 Freqtrade 2026.7 / CCXT 4.5.75。升级需审查原生构造/验证/共享市场/精度/档位/cleanup，再完整执行负向矩阵及真实断网交易回归，不能只更新版本常量。

参考：[Freqtrade 回测](https://www.freqtrade.io/en/stable/backtesting/)、安装版本的 Exchange/Binance/Backtesting 与 CCXT parse_market 源码、[Python audit events](https://docs.python.org/3/library/audit_events.html)、[os.link/fsync](https://docs.python.org/3/library/os.html#os.link)。SHA256 仍仅用于完整性，不证明交易所签名或历史时点规则真实性。
