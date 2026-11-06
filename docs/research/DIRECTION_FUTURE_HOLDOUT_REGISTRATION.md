# Future direction confirmation registration

This file registers the next confirmation window before any numeric values are
acquired or inspected.  It does not authorize downloading, fitting, predicting
or scoring the window; the formal admission gates remain required.

| field | frozen value |
|---|---|
| pairs | BTC/USDT:USDT, ETH/USDT:USDT, BNB/USDT:USDT |
| timeframe | 4h |
| first candle | 2026-11-07 00:00 UTC |
| end exclusive | 2026-12-07 00:00 UTC |
| label horizon | 3 candles |
| primary comparison | direction head own logloss early stopping vs fixed-tree binary control |
| primary metric | unweighted `mean(sign(prediction) == sign(volnorm_return))` |
| block unit | 6-candle synchronized blocks, with 12/24-candle sensitivity reports |
| promotion gate | pooled gain ≥0.25pp, at least 2/3 fold gains, and 95% block-bootstrap lower bound >0 in both confirmation windows |
| stopping rule | score once after the complete interval matures; no interim selection |

The interval is strictly after the current local data endpoint
(`2026-10-15 20:00 UTC`) and after the previously exposed development windows.
The registration is only a protocol identity.  Numeric access remains denied
until the project's independent holdout admission, source identity receipt and
nonexposure checks pass.
