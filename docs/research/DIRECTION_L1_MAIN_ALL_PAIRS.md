# Absolute-error main objective: complete three-pair tail audit

The earlier tail audit accidentally used a local config containing only BTC and
ETH.  This rerun adds the existing BNB feather file and keeps the same
reserved interval, split, feature pipeline and predeclared absolute-error
main-objective intervention.

On 6,684 complete final-tail rows:

| model | direction accuracy |
|---|---:|
| current squared-error/L1 blend | 50.0898% |
| absolute-error main/L1 blend | 50.5386% |

The candidate gains `+0.4488pp`.  Pair results are BTC `50.7630%`, ETH
`51.1670%`, BNB `49.6858%`; BNB declines relative to the current model.  A
paired two-day block bootstrap (3,000 draws, seed 42) gives
`[-1.587pp, +2.593pp]`, crossing zero.  The point gain is therefore not stable
enough for a statistical generalization claim.  Per the project's active
promotion rule, direction accuracy is the sole required metric and the point
estimate improved on the complete reserved tail, so the candidate is promoted
as the current research/production configuration with an isolated cache
identifier.  The interval is retained as an uncertainty limitation.

The production identifier is now
`mystrategy-4h-regression-72pair-corr-s1-l1main-lagret-v1` and the model
parameters include `objective: reg:absoluteerror`.  The previous identifier
remains the rollback reference.

Reproduction configs: `configs/experiments/all_pairs_local.yaml` and
`configs/experiments/xgboost_l1_main_final.yaml`.  Artifacts:
`artifacts/experiments/{current-lag-final-allpairs,l1-main-final-allpairs}`.
