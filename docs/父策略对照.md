# EXP-184 parent comparison

## Parent identity

The historical production parent is `VtechCryptoFreqAIRiskL20TimeEfficiency36Enabled` from EXP-184. Its real import chain and configuration are recorded on the historical `main` branch and in the local `experience61` archive.

The parent is not equivalent to the clean-room control:

| Item | EXP-184 parent | Clean-room control |
|---|---|---|
| Model | FreqAI `XGBoostRegressorES` | Standalone layer model, not connected to entry |
| Leverage | 20x | Fixed 2x |
| Target | Historical Vtech adverse utility | Clean-room adverse-risk / utility experiments |
| Exit | 36-hour stale exit plus inherited exits | Opposite-edge exit in the control |
| Feature path | Historical FreqAI inheritance chain | 89-feature causal layer |
| Identifier | `vtech-exp184-time36-enabled-main-volume` | `not-used-control-feature-only` |

## Stored parent evidence

Source ZIP:

```text
/home/wangke/project/freqtrade/user_data/experiences/experience61/control184long/user_data/backtest_results/backtest-result-2026-09-17_18-05-03.zip
```

The ZIP records:

- Strategy: `VtechCryptoFreqAIRiskL20TimeEfficiency36Enabled`.
- Timerange: `20220701-20260901`.
- Trades: 34,624.
- Starting wallet: 100 USDT.
- Ending wallet: 30,316,622.238 USDT.
- Wallet Sharpe: 6.107000.
- Wallet Calmar: 15,964,165.972.
- Wallet Sharpe × Calmar: approximately 97,493,162.
- Maximum relative drawdown: 19.4681%.

These are the stored Freqtrade `wallet_stats` values. They must not be mixed with the clean-room validation layer's daily-resampled metric convention without an explicit metric mapping.

The stored parent trade distribution is also asymmetric:

- Long: 14,083 trades, profit approximately 2.52 million USDT.
- Short: 20,541 trades, profit approximately 27.79 million USDT.
- Average holding time: approximately 3.58 hours long and 2.69 hours short.
- Largest negative exit buckets: `exit_signal`, `stop_loss`, and `stale_36h`.

## Current recheck

The parent loaded successfully from the original `experience61` strategy chain and ran a 3-pair, 9-day smoke on the current local data:

- 15 trades.
- Closed-trade result: -1.073 USDT.
- Closed-trade Sharpe: -3.55.
- This short smoke is not a long-term parent result.

A one-year current-data re-run was attempted with the same parent configuration, but Binance market metadata returned HTTP 418 during exchange initialization. The run was stopped rather than retried. The stored parent ZIP remains the authoritative historical evidence until a same-data re-run is possible.

## Decision

The clean-room branch must compare against EXP-184 as a named parent, but it must not claim equivalence or promotion from the current control results. The next valid comparison requires identical data, identifier/model availability, leverage, fees, exit semantics, and wallet metric definitions.
