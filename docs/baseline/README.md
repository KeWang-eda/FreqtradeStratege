# 冻结基线

- 原始 Git commit：`22d6ee5254c899b262201277dca54c0f71a53c20`。
- 原始 `config.json` 和当前 Python 环境清单保存在本目录。
- 修改前运行 `python -m pytest -q test_my_strategy.py`：11 passed。
- `tests/regression/baseline.json` 由修改前的 `feature.py`、`model.py` 在当前环境运行生成，固定 80 根合成 K 线，记录三个周期特征、基础特征、raw/volnorm 标签。比较容差 `rtol=1e-10, atol=1e-14`。
- 单仓位、预测绝对值排名、白名单顺序打破同分、预测符号、换仓理由、2 倍杠杆、ROI、stoploss 和 trailing 参数保持基线。
- 历史 README 的阈值、再次除波动率、Ridge 默认模型描述不符合当前代码，不能作为已验证基线。

原版回测命令（复制原始代码和配置到独立临时 userdir 后执行）：

```bash
/home/wangke/project/freqtrade/.venv/bin/freqtrade backtesting \
  -c /tmp/quant-refactor-baseline.BW441d/config.json \
  --userdir /tmp/quant-refactor-baseline.BW441d \
  --strategy-path /tmp/quant-refactor-baseline.BW441d \
  --freqaimodel-path /tmp/quant-refactor-baseline.BW441d/freqaimodels \
  --strategy MyStrategy --timerange 20250101-20250115 \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --datadir /home/wangke/project/FreqtradeStratege/data \
  --cache none --export trades \
  --backtest-directory /tmp/quant-refactor-baseline.BW441d/results
```

实际初次尝试遗漏了 `--datadir`，在读取 K 线前就因 Binance `fapi.binance.com/fapi/v1/exchangeInfo` 多次 RequestTimeout 中断；以上命令补上明确数据路径供重跑。该次尝试未取得交易结果，曾标记为待复现。

随后使用以上完整命令重试，仅追加临时配置把 ccxt 同步/异步请求 timeout 改为 5000ms（不变更交易规则），最终退出码为 2，错误为 `Could not load markets` / Binance `api.binance.com/api/v3/exchangeInfo` RequestTimeout。完整日志保存在 `backtest-retry.log`。

之后确认本机已运行 mihomo，并通过 `configs/environment/freqtrade-mihomo.json` 显式配置代理。原版及新版均已成功完成两个窗口真实回测，补齐交易基线、完整预测/信号回归和截断报告，见 [acceptance/README.md](acceptance/README.md)。上述失败日志保留为历史记录，不再代表当前阻塞状态。
