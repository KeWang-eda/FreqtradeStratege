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

## Same-window recheck (2026-09-30)

Previous attempts against current local data: a 3-pair 9-day smoke ran (15 trades, −1.073 USDT, closed-trade Sharpe −3.55), and a 15-pair 1-year re-run was stopped by Binance HTTP 418 during exchange initialization. The 418 block has since cleared (the exchange API answers again), but a fresh training run is not required for this comparison: the stored EXP-184 ZIP already carries walk-forward behavior because its model store holds 51 per-pair snapshots trained every 30 days (`backtest_period_days: 30`) across the entire 2022-2026 run. The window 2025-09-01 → 2026-09-01 can be sliced directly from it.

All three runs below were recomputed with one shared convention: hourly equity curve, window return = final/initial − 1, maximum relative drawdown inside the window, daily-resampled Sharpe.

| Metric (2025-09-01 → 2026-09-01) | EXP-184 parent | Clean-room max3 | Clean-room 5-slot (reference) |
|---|---:|---:|---:|
| Wallet return | +152.96% | −1.77% | −1.29% |
| Max relative drawdown | 3.29% | 22.20% | 34.07% |
| Daily-resampled Sharpe | 5.70 | 0.054 | 0.168 |
| Trades | 4,857 | 1,175 | 1,943 |
| Win rate | 67.4% | 32.6% | 34.5% |
| Duration-0 trades | 1,598 (32.9%) | 0 | 0 |

### The parent window is dominated by same-candle ROI trades

- The 1,598 duration-0 trades have a 99.75% win rate and sum to +19.76M USDT — 107.8% of the window's total trade PnL. Excluding them, the remaining 3,259 trades (win rate 51.6%, median hold 360 minutes) sum to −1.44M USDT.
- Full stored run: 16,530 of 34,624 trades (47.7%) are duration-0 and carry 118.9% of total PnL.
- Root cause, already established on 2026-09-22 (EXP190): with `trade_duration == 0`, freqtrade's `_get_close_rate_for_roi` evaluates ROI against the entry candle's own high/low, which the live engine cannot reproduce.
- This ZIP predates that fix, and the chain it used still carries the unfixed `_DynamicROIBase` (`minimal_roi = {"0": 0.20}`, `custom_roi` without a duration guard) at `experience61/roi075long/user_data/strategies/VtechCryptoFreqAIRiskL20DynamicROI.py`. No patched copy exists anywhere under `experience61`.
- Post-fix archive evidence: after the duration guard was applied, the family returned −3.22% with 62.02% drawdown on the EXP190 window (`EXP190-ROI-SAMEBAR-REAL-RETURN-REVEALED-20260922.md`).

### Control context (stored stats, full window to 2026-09-10)

- Clean-room max3: wallet 100 → 101.056 USDT (+1.06%), trade-sum +1.76%, wallet Sharpe 0.185, max drawdown 22.20%, 1,205 trades, zero duration-0 trades.
- Clean-room 5-slot reference: wallet 100 → 105.518 USDT (+5.52%), trade-sum +6.78%, wallet Sharpe 0.373, max drawdown 34.07%, 1,987 trades, zero duration-0 trades.
- Funding is included in both wallet curves; both use fee 0.0005 per side.

## Decision

- The stored EXP-184 window cannot serve as a positive benchmark: more than 100% of its profit is produced by same-candle ROI trades that are not reproducible live, and the run predates the EXP190 fix.
- The clean-room control shows no promotable edge on the same window: +1.06% wallet return with 22.2% drawdown and 0.185 Sharpe on the aligned 3-slot run.
- Neither side justifies promotion, model-entry connection, dry-run, or deployment.
- A clean same-window parent re-run with the duration guard re-applied stays possible (cost: walk-forward training, hours), but the patched chain is not preserved in the archive; it is deferred until a parent-equivalence claim is actually needed.
