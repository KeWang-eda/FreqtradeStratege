# 使用本地行情与 mihomo 的真实回测验收

后续已补齐[市场元数据快照与完全离线验收](../../offline_backtest_snapshot.md)。`offline-*` 保存断网审计、系统调用、原生日志/ZIP、回归报告及 115 项测试 JUnit；`binance-usdt-market-snapshot.json` 来自真实采集；`native-online-reference.tar.gz`、`native-offline-artifacts.tar.gz` 保存可重复比较的预测、metadata 和结果归档。本文以下联网原版/新版验收证据保持原样。

2026-10-17 已通过当前运行的 mihomo（`http://127.0.0.1:7890`）完成四次原生 Freqtrade/FreqAI 回测。行情、1h mark 和历史 funding_rate 都来自仓库本地 `data/futures/`，没有重新下载；Binance 公共接口只用于框架启动的市场规则查询，杠杆档位使用 Freqtrade 2026.7 内置配置。

| 数据窗口（UTC，结束不含） | 原版 / 新版交易数 | 汇总盈亏 USDT | 对照 |
| --- | --- | --- | --- |
| 2025-01-01 → 2025-01-15 | 13 / 13 | -7.729 | 交易、信号、4 个预测文件一致 |
| 2025-01-01 → 2025-01-22 | 25 / 25 | 2.681 | 交易、信号、6 个预测文件一致 |

两个版本的短/长窗口在重叠区间均为 13 笔相同入场，退出差异检查通过，短窗口的终点强制平仓按既定规则排除。每个训练窗口的特征 schema 均为 92 列。

模型使用原生 `XGBoostRegressorES` 及原始训练参数，只缩小币对为 BTC/ETH。四次运行各自使用新建的独立 userdir 和预测缓存，没有共用训练结果。原版代码来自 commit `22d6ee5254c899b262201277dca54c0f71a53c20`，实际交易配置为本目录上一级冻结的 config.json，附加配置只设置代理及请求超时。

`old-new-short.json`、`old-new-long.json` 对完整交易 DataFrame（含订单、价格、数量、费用、盈亏、时点和方向）、signals/rejected/exited 导出、逐窗口预测 DataFrame，以及训练特征/标签 schema 和标签统计做比较。浮点容差 `rtol=atol=1e-12`，实测预测差异为 0。`old-truncation.json`、`new-truncation.json` 记录各版本的窗口截断检查。

四个 `.zip` 为原生结果归档，包含交易、导出信号及策略入口；四个 `.log` 为运行日志。`old-source.tar.gz`、`new-source.tar.gz` 保存对应的源码；原生归档中的新版策略仅为入口，因此额外保存完整研究包及适配源码。`summary.json` 记录完整指标、输入数据/结果/源码的 SHA-256 和依赖版本。

从仓库根目录重跑完整对照：

```bash
repo_root="$PWD"
task_root=$(mktemp -d /tmp/quant-freqtrade-verify.XXXXXX)
mkdir -p "$task_root/original"
git archive 22d6ee5254c899b262201277dca54c0f71a53c20 \
  MyStrategy.py feature.py model.py util.py freqaimodels | tar -x -C "$task_root/original"

for version in old new; do
  strategy_dir="$repo_root"
  if [ "$version" = old ]; then strategy_dir="$task_root/original"; fi
  for window in short long; do
    timerange=20250101-20250115
    if [ "$window" = long ]; then timerange=20250101-20250122; fi
    run_dir="$task_root/$version-$window"
    mkdir -p "$run_dir/results"
    /home/wangke/project/freqtrade/.venv/bin/freqtrade backtesting \
      -c "$repo_root/docs/baseline/config.json" \
      -c "$repo_root/configs/environment/freqtrade-mihomo.json" \
      --userdir "$run_dir" --datadir "$repo_root/data" \
      --strategy-path "$strategy_dir" --freqaimodel-path "$strategy_dir/freqaimodels" \
      --strategy MyStrategy --timerange "$timerange" \
      --pairs BTC/USDT:USDT ETH/USDT:USDT \
      --cache none --export signals --backtest-directory "$run_dir/results"
  done
done

for window in short long; do
  PYTHONPATH=src /home/wangke/project/freqtrade/.venv/bin/python tools/verify_freqtrade_regression.py \
    "$task_root/old-$window" "$task_root/new-$window" \
    --report "$task_root/compare-$window.json"
done

/home/wangke/project/freqtrade/.venv/bin/python verify_no_lookahead.py \
  docs/baseline/acceptance/new-short.zip docs/baseline/acceptance/new-long.zip \
  --report "$task_root/new-truncation.json"
```

验证范围仅为上述两个币对、两个窗口、原始标签及模型配置；不能推广为全部 72 个交易对或所有历史时段已经验收，也不代表未来盈利保证。
