# Alpha#12-inspired interaction redundancy audit

The candidate was fixed before reading the result as
`-sign(volume[t] - volume[t-1]) * (close[t] - close[t-1])`, inspired by
Kakushadze (2016), *101 Formulaic Alphas*, Alpha#12.  In this repository it
is only a time-series heuristic: the original paper is cross-sectional.

The audit used only the frozen native training snapshots from the existing
rolling development run.  Each pair was split into four chronological blocks;
label maturity was purged at the next block boundary.  No outer/development
truth was read and no model was changed.  The reproducible protocol and output
are `tools/diagnose_alpha12_redundancy.py`,
`artifacts/direction-feature-study/alpha12-redundancy-protocol.json`, and
`artifacts/direction-feature-study/alpha12-redundancy.csv`.

The candidate is highly redundant with the existing return feature (blockwise
Spearman correlation `0.83` to `1.00`) and has near-zero additional relation
to volume-change.  Its direction AUC is not stable across the four blocks; for
example ETH changes from `0.474` to `0.512` to `0.496` to `0.421`.  This does
not establish a deployable signal or a model improvement, so the feature is
rejected and no production change is made.

The result supports investigating conditional relationship drift (D4) before
adding another correlated formula.  The correlation check is a screening
diagnostic only; the promotion metric remains paired out-of-sample direction
accuracy.
