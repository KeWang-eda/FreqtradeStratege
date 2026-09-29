"""Causal higher-timeframe context features.

Freqtrade's informative-pair contract shifts a higher-timeframe candle to its
availability time before merging it into the base timeframe. This module keeps
that boundary explicit instead of using a plain timestamp merge.

Reference:
  https://www.freqtrade.io/en/stable/strategy-customization/
"""

from __future__ import annotations

import pandas as pd
from pandas import DataFrame


def build_causal_higher_timeframe_features(
    base_frame: DataFrame,
    higher_frame: DataFrame,
    timeframe_hours: int,
    prefix: str,
) -> DataFrame:
    """Merge closed higher-timeframe context into a base candle frame.

    ``higher_frame.date`` is the higher candle open time. The candle becomes
    available at ``date + timeframe_hours`` and is forward-filled only after
    that timestamp.
    """
    required = {"date", "high", "low", "close"}
    for name, frame in (("base_frame", base_frame), ("higher_frame", higher_frame)):
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{name} missing columns: {sorted(missing)}")
    if timeframe_hours < 1:
        raise ValueError("timeframe_hours must be positive")
    if not prefix:
        raise ValueError("prefix must not be empty")

    base = base_frame.copy()
    higher = higher_frame.copy()
    base["date"] = pd.to_datetime(base["date"], utc=True).dt.as_unit("ns")
    higher["date"] = pd.to_datetime(higher["date"], utc=True).dt.as_unit("ns")
    base = base.sort_values("date").reset_index(drop=True)
    higher = higher.sort_values("date").reset_index(drop=True)
    higher["available_at"] = higher["date"] + pd.Timedelta(
        hours=timeframe_hours
    )
    higher[f"{prefix}_return"] = higher["close"].pct_change()
    higher[f"{prefix}_range"] = (
        higher["high"] - higher["low"]
    ) / higher["close"]
    higher[f"{prefix}_close_vs_mean3"] = (
        higher["close"] / higher["close"].rolling(3).mean() - 1.0
    )
    context_columns = [
        f"{prefix}_return",
        f"{prefix}_range",
        f"{prefix}_close_vs_mean3",
    ]
    context = higher[["available_at", *context_columns]].drop_duplicates(
        "available_at", keep="last"
    )
    result = pd.merge_asof(
        base,
        context.sort_values("available_at"),
        left_on="date",
        right_on="available_at",
        direction="backward",
    ).drop(columns=["available_at"])
    return result


def build_causal_mark_basis_features(
    futures_frame: DataFrame,
    mark_frame: DataFrame,
    prefix: str = "mark_basis",
) -> DataFrame:
    """Merge closed mark/futures basis into futures candles without lookahead."""
    required = {"date", "close"}
    for name, frame in (("futures_frame", futures_frame), ("mark_frame", mark_frame)):
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{name} missing columns: {sorted(missing)}")

    futures = futures_frame.copy()
    mark = mark_frame.copy()
    futures["date"] = pd.to_datetime(futures["date"], utc=True).dt.as_unit("ns")
    mark["date"] = pd.to_datetime(mark["date"], utc=True).dt.as_unit("ns")
    futures = futures.sort_values("date").reset_index(drop=True)
    mark = mark.sort_values("date").reset_index(drop=True)
    reference = futures[["date", "close"]].rename(columns={"close": "futures_close"})
    mark = mark.merge(reference, on="date", how="left")
    mark[f"{prefix}_value"] = mark["close"] / mark["futures_close"] - 1.0
    mark["available_at"] = mark["date"] + pd.Timedelta(hours=1)
    context = mark[["available_at", f"{prefix}_value"]].dropna().drop_duplicates(
        "available_at", keep="last"
    )
    return pd.merge_asof(
        futures,
        context.sort_values("available_at"),
        left_on="date",
        right_on="available_at",
        direction="backward",
    ).drop(columns=["available_at"])



def validate_higher_timeframe_alignment(
    merged_frame: DataFrame,
    base_timestamp: object,
    feature_columns: list[str],
) -> None:
    """Reject a merge that exposes a higher candle before availability."""
    timestamp = pd.Timestamp(base_timestamp, tz="UTC")
    if "date" not in merged_frame.columns:
        raise ValueError("merged_frame requires date")
    if not feature_columns:
        raise ValueError("feature_columns must not be empty")
    row = merged_frame.loc[pd.to_datetime(merged_frame["date"], utc=True) == timestamp]
    if row.empty:
        raise ValueError("base_timestamp is not present")
    if row[feature_columns].notna().all(axis=None):
        raise ValueError("alignment check requires a timestamp before context availability")
