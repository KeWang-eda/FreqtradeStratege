# 离线适配器与比较器独立复核

状态：**PASS（独立复核范围）**。本复核从提交 `106f0fc` 开始，只读检查核心实现，在临时目录执行下列两项负向实验；没有修改策略、模型、历史行情、快照来源或依赖。两项缺陷由主 Agent 在共享文件中统一修复后，已独立重放并确认拒绝。此结论不替代 Phase 4 的完整系统隔离验收。

## 实际发现

| 验收项 | 检查或复现 | 预期 | 修复前实际结果 | 状态 |
| --- | --- | --- | --- | --- |
| normalized JSON 类型与真实解析一致 | 读取冻结快照，仅把 BTC `contractSize` 从 `1.0` 改成 `true`，重新计算 envelope SHA256；保留真实 raw 响应 | 明确拒绝 | `load_snapshot` 成功返回 `contractSize=True` | FAIL |
| normalized 市场身份不会改变原生过滤 | 仅把 BTC `linear` 从 `true` 改成 `1`，重算 envelope SHA256，再创建 `SnapshotBinance` | 明确拒绝 | 构造成功；`market_is_future(BTC)=False`，ETH 仍为 True | FAIL |
| 语义配置不同不能通过回归 | 使用现有 `make_run` fixture 生成两份相同工件；分别写入 `result_config.json`，唯一差异为 `freqai.train_period_days=365` 与 `1` | 比较失败 | `compare_runs` 返回 `passed: true`、`differences: []` | FAIL |

这三项记录来自本轮实际 Python 执行输出，并非仅根据代码推断。前两项是同一个类型校验缺陷的两个实验。

下列命令在仓库根目录复现比较器缺口；`PYTHON` 指向已经安装锁定依赖的解释器。这里构造的是明确标记的负向测试工件，不是回测数据或交易所响应验收。

```bash
PYTHONPATH=src "$PYTHON" - <<'PY'
import json, runpy, tempfile, zipfile
from pathlib import Path
from tools.verify_freqtrade_regression import compare_runs
helpers = runpy.run_path("tests/integration/test_freqtrade_regression_report.py")
with tempfile.TemporaryDirectory() as directory:
    old, new = Path(directory) / "old", Path(directory) / "new"
    for root, period in ((old, 365), (new, 1)):
        helpers["make_run"](root)
        with zipfile.ZipFile(root / "result.zip") as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        # 兼容复核前不带配置的 fixture；始终只保留一个配置文件。
        config = json.loads(contents.get("result_config.json", "{}"))
        config.setdefault("freqai", {})["train_period_days"] = period
        contents["result_config.json"] = json.dumps(config)
        with zipfile.ZipFile(root / "result.zip", "w") as archive:
            for name, content in contents.items():
                archive.writestr(name, content)
    result = compare_runs(old, new)
    print(result["passed"], result["differences"])
PY
```

修复前本轮输出为 `True []`；修复后应拒绝或报告配置差异。

第一项根因是 `market_snapshot.load_snapshot` 用 Python 字典相等比较真实解析与记录的 normalized 规则：Python 中 `True == 1 == 1.0`。`SnapshotBinance._api_reload_markets` 当时也使用相同相等比较。原生 Freqtrade `Exchange.market_is_future` 却对 `linear` 和 `swap` 使用 `is True`，因此这种类型变化能通过快照校验，却改变交易对可用性。建议使用规范化 JSON 的严格散列比较或保留 JSON 类型的递归比较；`leverage_rules` 也应保留类型。

第二项根因是 `verify_freqtrade_regression.compare_runs` 当时只读取结果 JSON、信号、预测与模型 metadata，没有读取归档中的 `*_config.json`。实际归档确实包含配置；仅比较结果参数不能证明 FreqAI 配置相同。建议要求唯一配置归档并比较所有语义字段，仅对独立 userdir 路径和经过论证的在线/离线传输配置作明确、可追溯的规范化。

## 已核对且未发现新的阻断项

| 边界 | 源码与既有测试证据 | 结论范围 |
| --- | --- | --- |
| 运行模式 | `offline_backtest.check_config` 在任何客户端构造之前拒绝非 BACKTEST；限制 Binance、isolated、USDT、StaticPairList 和明确交易对 | 当前版本、当前支持的配置范围 |
| 原生校验 | `SnapshotBinance` 保留 `super(..., validate=True, load_leverage_tiers=True)`，未绕过 Freqtrade 配置校验 | 已安装 Freqtrade 2026.7 |
| 强制刷新 | 只把已验证内存快照交给 CCXT `set_markets`；同步/异步 `fetch` 明确拒绝 HTTP | 不声称这构成针对恶意 C 扩展的安全沙箱 |
| 普通交易隔离 | 原生 Binance/Exchange 和全局 CCXT 类没有被修改；离线客户端是独立子类 | 未进行账户或订单联网测试 |
| 原子发布 | 同目录临时文件、flush/fsync、原子 no-clobber `os.link`，最后同步目录；普通异常清理临时文件 | SIGKILL 可以遗留显式 `.tmp`；不会自动采用它 |
| 生命周期 | 构造失败显式 close；异步、同步客户端及 loop 清理；关闭幂等；运行中的外部事件循环拒绝 | 已有故障注入测试覆盖，不等于所有硬件 I/O 故障枚举 |
| 网络审计 | HTTP/DNS/socket 与子进程拒绝有记录；即便组件捕获拒绝并返回 0，最终仍返回 3 | Python 层不能代替 network namespace 和 strace |
| Git 溯源例外 | 只放行固定仓库的三个精确只读 argv；禁用 pager、fsmonitor、external diff 与 textconv | 不放行任意 git 命令或任意子进程 |

原始市场响应允许保留交易所新增字段，envelope 则严格限制字段集合。SHA256 证明文件载荷完整性，不证明交易所数字签名，也不证明采集时规则就是历史回测时点的真实规则。

## 修复后的独立验收

主 Agent 改为规范化 JSON 散列比较 normalized、leverage_rules 和 CCXT 恢复后的规则，保留 JSON 类型；比较器要求唯一 `*_config.json` 并精确比较全部导出的有效配置，`config_files` 仅规范化 checkout 根目录，保留文件名与合并顺序，未豁免代理或 timeout。

独立执行：

```bash
PYTHONPATH=src "$PYTHON" -m pytest -q \
  tests/unit/test_snapshot_contract.py \
  tests/integration/test_offline_lifecycle.py \
  tests/integration/test_freqtrade_regression_report.py \
  --junitxml=docs/acceptance/adapter_independent_review_pytest.xml
```

结果：**105 passed、0 failed、0 skipped，11.51s**，见 [JUnit](adapter_independent_review_pytest.xml)。660 条 warning 来自 joblib 与 NumPy 的已知弃用提示，没有屏蔽或改依赖。此命令没有执行完整原生回测。

独立逐项重放初始缺陷，实际结果：

| 实验 | 修复后实际输出 | 状态 |
| --- | --- | --- |
| `contractSize=true` | `SnapshotError: Normalized rules differ from genuine response parsed by CCXT` | PASS |
| `linear=1` | 相同 SnapshotError，构造前拒绝，不能再改变原生市场过滤 | PASS |
| `swap=1` | 相同 SnapshotError，构造前拒绝 | PASS |
| 仅改变训练窗口 365 → 1 | `passed:false`、`configuration/freqai: differs or missing` | PASS |

网络请求、交易数量、订单数量、预测文件数量：本独立负向复核不执行真实行情交易生命周期，不产生对应计数；这些指标应引用 Phase 4 的真实端到端证据，不应将本处 105 项测试当作该生命周期已经完成。

本报告未删除文件，未改生产实现，未产生行情下载或真实账户操作。下一阶段准入：两个独立发现的阻断已修复且复验通过，可以继续完整离线回测、严格配置与交易工件比较；其最终状态由主 Agent 集成验收。
