"""Freqtrade candle timestamps denote candle OPEN times, stored in UTC."""

import re

import pandas as pd

from quant.errors import ConfigurationError, DataContractError


def timeframe_delta(timeframe: str) -> pd.Timedelta:
    """Convert fixed m/h/d/w timeframes into positive durations."""
    match = (
        re.fullmatch(r"([1-9][0-9]*)([mhdw])", timeframe) if isinstance(timeframe, str) else None
    )
    if not match:
        raise ConfigurationError(f"Unsupported fixed timeframe: {timeframe}")
    return pd.Timedelta(int(match[1]), unit={"m": "min", "h": "h", "d": "D", "w": "W"}[match[2]])


def align_closed_candles(
    base: pd.DataFrame, informative: pd.DataFrame, base_timeframe: str, informative_timeframe: str
) -> pd.DataFrame:
    """Join features only after informative close <= base candle close.

    Inputs must be UTC, sorted and unique. No backfill is ever performed.
    """
    for frame in (base, informative):
        dates = pd.DatetimeIndex(frame["date"])
        if (
            dates.tz is None
            or dates.hasnans
            or dates.has_duplicates
            or not dates.is_monotonic_increasing
        ):
            raise DataContractError("Alignment requires unique sorted timezone-aware dates")
    left = base.assign(
        available_at=(
            pd.to_datetime(base["date"], utc=True) + timeframe_delta(base_timeframe)
        ).astype("datetime64[ns, UTC]")
    )
    right = informative.drop(columns="date").assign(
        informative_available_at=(
            pd.to_datetime(informative["date"], utc=True) + timeframe_delta(informative_timeframe)
        ).astype("datetime64[ns, UTC]")
    )
    return pd.merge_asof(
        left,
        right,
        left_on="available_at",
        right_on="informative_available_at",
        direction="backward",
        suffixes=("", "_informative"),
    )
