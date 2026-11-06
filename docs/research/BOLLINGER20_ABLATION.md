# Bollinger(20) position feature

Bollinger (2001) describes standardized position inside a rolling price band.
The causal candidate was `(close - mean20) / (2 * std20)` and was added only to
the candidate arm; the baseline replay remained byte-for-byte feature-equivalent.

On 756 paired ready predictions:

- baseline: `406/756 = 53.704%`
- Bollinger candidate: `402/756 = 53.175%`
- change: **-0.529pp**
- 12-candle block bootstrap: `[-2.778pp, +1.587pp]`

The candidate is rejected. The runner also fixed an initial bug that had added
the new column to both arms; the corrected v3 result above is the only valid
comparison.

