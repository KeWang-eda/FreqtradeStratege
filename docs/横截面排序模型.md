# Cross-sectional rank model

`strategies/cross_sectional_rank_model.py` implements the proper same-timestamp XGBoost ranking path.

## Contract

- One timestamp-and-side pair is one XGBoost query group (`qid`).
- The rows inside a query group are the tradable pairs for that side.
- The model receives the existing causal feature set and learns pair ordering directly.
- The target is converted to an integer relevance rank inside each timestamp-and-side query because XGBoost's ranking objective requires non-negative integer relevance labels.
- Training and validation split on complete timestamp groups; no timestamp is split across both sides.
- Validation is the only evaluation set used for early stopping.

## Two-year smoke

The two-year train/OOS protocol used:

- Train data from 2022-08-17 through the 8-hour purge boundary before 2024-08-17.
- OOS data from 2024-08-17 through 2026-09-27.
- 15 pairs and 89 causal features.
- Train rows: 262,725.
- Validation rows: 51,825.
- Train queries: 24,447.
- Validation queries: 6,016.
- Best iteration: 185.
- OOS rows: 277,440.
- OOS queries: 18,496.
- Overall OOS Rank IC: 0.03379 when measured within timestamp-and-side query groups.
- Top-3-per-side gross target lift over all candidates: `-0.0112%` in decimal-return units.

The ranker has weak statistical ordering information but failed the economic Top-K test; it remains research-only and is not connected to the Freqtrade entry point.

## Reference

The implementation follows XGBoost's official learning-to-rank contract: samples are sorted into query groups and `qid` identifies the group.[41]

## Sources

[41] https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html
