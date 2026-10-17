# Phase 0：本轮基线冻结（2026-10-17）

状态：**通过本阶段门槛**，尚不代表后续阶段或全项目完成。

## 当前状态与本轮复验

- 起始分支 `main`，HEAD `5ce05d6684345c56902b4af85a32d5889b92ac7b`；起始暂存、未暂存、未跟踪文件均为空，未重置或丢失用户修改。
- 本轮 `git fetch origin main` 成功；[本地/远程 HEAD](phase0_remote_heads.txt)一致。
- 使用 `/home/wangke/project/freqtrade/.venv/bin/python`，Python 3.13.13。shell 默认 Python 是另一个 conda 环境，所有验收明确使用上述虚拟环境。
- 实测依赖：Freqtrade 2026.7、CCXT 4.5.75、pandas 3.0.5、NumPy 2.5.2、XGBoost 3.4.1、sklearn 1.9.0、pyarrow 25.0.1、pytest 9.1.1、Ruff 0.15.22。
- 本轮基础测试：**115 passed，0 failed，0 skipped，34.01s**；[JUnit](phase0_pytest.xml)、[日志](phase0_pytest.log)。其中完整网络命名空间历史回测用例实际执行，未 skip。
- 本轮 Lint：[All checks passed](phase0_ruff.log)；格式：[73 files already formatted](phase0_format.log)。

历史报告的 115 项结论在当前未改动代码上得到独立复现。历史交易归档保持原样，本轮测试重新建立独立 userdir、训练 FreqAI，并比较历史联网参考；**本轮没有重新联网运行参考基线**。

## 数据与快照清单

| 类型 | 配置涉及交易对数 | 已有文件 | 文件缺失 | 时间重复 / 未排序 |
| --- | ---: | ---: | ---: | ---: |
| 4h futures | 72 | 72 | 0 | 0 / 0 |
| 1h mark | 72 | 72 | 0 | 0 / 0 |
| 1h funding_rate | 72 | 72 | 0 | 0 / 0 |

以上只是文件及基本时间结构检查，不能推断每个文件覆盖完整训练/回测区间。全部文件的行数、起止、时区和 SHA256 见[冻结清单](phase0_inventory.json)。文件名中的 funding `1h` 是 Freqtrade 存储键，不代表实际每小时支付资金费率；缺口分类在 Phase 3 处理。

快照 `docs/baseline/acceptance/binance-usdt-market-snapshot.json` 在本轮通过默认 30 天有效期校验；采集时间 `2026-10-17T12:04:06.169588+00:00`，范围 BTC/ETH，Freqtrade/CCXT 版本匹配。规范化载荷哈希 `c085efcfe8e2c3f62e39fb5e983e601fc89fd20d7c45893e0ade640092ac5bc2`，完整文件哈希及杠杆来源保存在清单/原快照。未联网重新采集或覆盖。

原生配置为 4h、365 天训练、7 天回测窗口、标签跨度 3、StaticPairList，相关特征交易对包含 BTC/ETH。92 列是已保存真实训练工件的 schema，后续不把该值硬编码成通用策略规则。策略、模型、标签、特征和交易参数的源文件指纹已经冻结。

## 可复现命令

```bash
git status --short
git diff --cached --stat
git branch --show-current
git log -5 --oneline
git fetch origin main
git rev-parse HEAD origin/main
/home/wangke/project/freqtrade/.venv/bin/python -m pip freeze
PYTHONPATH=src /home/wangke/project/freqtrade/.venv/bin/python -m pytest -q \
  --junitxml=docs/acceptance/phase0_pytest.xml
/home/wangke/project/freqtrade/.venv/bin/ruff check src tests tools \
  MyStrategy.py feature.py model.py util.py verify_no_lookahead.py _quant_strategy_bootstrap.py
/home/wangke/project/freqtrade/.venv/bin/ruff format --check src tests tools \
  MyStrategy.py feature.py model.py util.py verify_no_lookahead.py _quant_strategy_bootstrap.py
```

版本与数据清单通过 pandas/pyarrow 本地读取及 hashlib 生成，未下载数据。首次清单命令漏设 `PYTHONPATH=src`，在导入时失败；补上后成功，没有把该命令失败算作测试失败或成功。其余起始记录见[Git 状态](phase0_git_status.txt)、[近期提交](phase0_recent_commits.txt)、[环境冻结](phase0_environment.freeze.txt)。

## 风险与阶段输入

1. 现有成功测试主要覆盖 BTC/ETH 两周，不代表全币种/全历史或实盘验收。
2. 当前代码仍需审查原子写入、缺规则响应、资源释放、审计失败状态和比较器元数据覆盖；原测试通过不证明这些边界正确。
3. 部分交易对较晚上市或数据提前结束，须在 Phase 3 按训练预热需求检查。
4. 261 条 joblib/NumPy 弃用警告来自依赖，保留记录；未升级依赖。
5. 用户任务文本在 Phase 3 第 8 项中途截断，已请求补发；先完成已明确的工作，不推定未收到的后续验收要求。

资料：本仓库[既有方案](../offline_backtest_snapshot.md)、实际安装版本的 Freqtrade `Exchange/Backtesting` 与 CCXT `parse_market/set_markets` 源码、[Python 文件同步与发布接口](https://docs.python.org/3/library/os.html#os.fsync)。后续修复均以这份基线为输入。
