# RSI(14) removal candidate

The all-feature inventory and grouped validation permutation both identified
RSI as a potentially redundant family. A single-factor paired forward
diagnostic therefore removed only `rsi-period_14`, retaining RSI(6), RSI(24),
lag returns, all labels, weights, preprocessing and XGBoost settings.

On 756 common ready predictions:

- baseline: `406/756 = 53.704%`
- candidate: `418/756 = 55.291%`
- point change: **+1.587 pp**
- 12-candle block bootstrap (5,000, seed 42): `[-0.661 pp, +4.101 pp]`

The point result is promising, but the interval crosses zero and this is an
exposed development window. The artifact is therefore a pre-registered
candidate for independent confirmation only; it does not change production.

As a chronological confirmation check, weeks 1--3 were treated as discovery
and weeks 4--6 as the subsequent confirmation segment. The candidate gain was
positive in the discovery segment (`+3.175 pp`) but **0 pp** in weeks 4--6.
The improvement therefore does not persist through the available later
segment and is rejected for production.

