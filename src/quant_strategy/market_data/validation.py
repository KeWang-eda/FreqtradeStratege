"""OHLCV inputs are never silently sorted, deduplicated or backfilled."""

import numpy as np
import pandas as pd

from quant_strategy.errors import DataContractError


def validate_ohlcv(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Validate numeric OHLCV, unique UTC dates and chronological ordering."""
    required = ["date", "open", "high", "low", "close", "volume"]
    if not dataframe.columns.is_unique or set(required) - set(dataframe):
        raise DataContractError("OHLCV requires unique date/open/high/low/close/volume columns")
    frame = dataframe[required].copy()
    dates = pd.DatetimeIndex(frame["date"])
    if dates.tz is None:
        raise DataContractError("OHLCV dates must declare a timezone (UTC preferred)")
    if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise DataContractError("OHLCV dates must be nonmissing, unique and increasing")
    frame["date"] = dates.tz_convert("UTC")
    try:
        numeric = frame[required[1:]].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise DataContractError("OHLCV fields must be numeric") from exc
    if not np.isfinite(numeric).all() or (numeric[:, :4] <= 0).any() or (numeric[:, 4] < 0).any():
        raise DataContractError("OHLCV must be finite with positive prices and nonnegative volume")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any() or (
        frame["low"] > frame[["open", "close", "high"]].min(axis=1)
    ).any():
        raise DataContractError("Inconsistent OHLC price range")
    return frame.reset_index(drop=True)
