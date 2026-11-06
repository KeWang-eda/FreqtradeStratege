# Close Location Value (CLV) candidate

Following Williams (1985) and the existing CLV research branch, the causal
candidate was `(2*close-high-low)/(high-low)`, with zero-range candles mapped
to missing. It was added only to the candidate arm; all lag features, labels,
weights, preprocessing and XGBoost settings were fixed.

- baseline: `406/756 = 53.704%`
- CLV candidate: `402/756 = 53.175%`
- change: **-0.529pp**
- 12-candle block bootstrap: `[-3.042pp, +1.720pp]`

The candidate is rejected. The runner now supports this causal feature for
future research without changing the production schema.

