"""Small, auditable feature diagnostics for the layered framework."""

from __future__ import annotations

from typing import Sequence

import pandas as pd
from pandas import DataFrame


def calculate_cross_sectional_rank_ic(
    panel: DataFrame,
    feature_columns: Sequence[str],
    target_column: str,
    minimum_assets: int = 5,
) -> DataFrame:
    """Calculate timestamp-wise Spearman rank IC for a feature panel.

    The panel must contain ``timestamp``, one row per pair and timestamp, the
    feature columns, and one future target column. This function does not fit
    parameters and does not use future values except for the supplied target.
    """
    required_columns = {"timestamp", "pair", target_column, *feature_columns}
    missing_columns = required_columns.difference(panel.columns)
    if missing_columns:
        raise ValueError(f"panel is missing columns: {sorted(missing_columns)}")

    rows: list[dict[str, float | int | str]] = []
    for feature_name in feature_columns:
        correlations: list[float] = []
        for _, timestamp_frame in panel.groupby("timestamp", sort=True):
            valid = timestamp_frame[[feature_name, target_column]].dropna()
            if len(valid) < minimum_assets:
                continue
            feature_rank = valid[feature_name].rank(method="average")
            target_rank = valid[target_column].rank(method="average")
            correlation = feature_rank.corr(target_rank)
            if pd.notna(correlation):
                correlations.append(float(correlation))
        if correlations:
            rows.append(
                {
                    "feature": feature_name,
                    "rank_ic_mean": sum(correlations) / len(correlations),
                    "rank_ic_positive_fraction": sum(value > 0 for value in correlations)
                    / len(correlations),
                    "timestamp_count": len(correlations),
                }
            )
        else:
            rows.append(
                {
                    "feature": feature_name,
                    "rank_ic_mean": float("nan"),
                    "rank_ic_positive_fraction": float("nan"),
                    "timestamp_count": 0,
                }
            )

    return DataFrame(rows).sort_values("rank_ic_mean", ascending=False).reset_index(
        drop=True
    )


def calculate_time_split_rank_ic(
    panel: DataFrame,
    feature_columns: Sequence[str],
    target_column: str,
    split_timestamp: object,
    minimum_assets: int = 5,
) -> DataFrame:
    """Compare Rank IC before and after a fixed time split."""
    early_panel = panel.loc[panel["timestamp"] < split_timestamp]
    late_panel = panel.loc[panel["timestamp"] >= split_timestamp]
    early = calculate_cross_sectional_rank_ic(
        early_panel, feature_columns, target_column, minimum_assets
    ).rename(
        columns={
            "rank_ic_mean": "early_rank_ic_mean",
            "rank_ic_positive_fraction": "early_positive_fraction",
            "timestamp_count": "early_timestamp_count",
        }
    )
    late = calculate_cross_sectional_rank_ic(
        late_panel, feature_columns, target_column, minimum_assets
    ).rename(
        columns={
            "rank_ic_mean": "late_rank_ic_mean",
            "rank_ic_positive_fraction": "late_positive_fraction",
            "timestamp_count": "late_timestamp_count",
        }
    )
    return early.merge(late, on="feature", how="outer")
