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
enough for production promotion, but the complete-pair rerun corrects the
previous incomplete data coverage.

Reproduction configs: `configs/experiments/all_pairs_local.yaml` and
`configs/experiments/xgboost_l1_main_final.yaml`.  Artifacts:
`artifacts/experiments/{current-lag-final-allpairs,l1-main-final-allpairs}`.
