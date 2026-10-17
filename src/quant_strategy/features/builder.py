"""Compose pure historical features, never forwarding target columns."""

from collections.abc import Iterable

import pandas as pd

from quant_strategy.errors import DataContractError

from .momentum import add_period_expanded_features
from .price import add_basic_price_features
from .technical import add_baseline_features


def build_features(
    dataframe: pd.DataFrame,
    periods: Iterable[int] = (6, 14, 24),
    enabled_features: Iterable[str] = (),
) -> pd.DataFrame:
    """Return a finite-or-missing, unique feature matrix preserving the index."""
    if not dataframe.columns.is_unique:
        raise DataContractError("Duplicate input columns")
    frame = dataframe[["date", "open", "high", "low", "close", "volume"]].copy()
    periods = tuple(periods)
    if len(set(periods)) != len(periods):
        raise DataContractError("Duplicate feature periods")
    for period in periods:
        add_period_expanded_features(frame, period)
    add_basic_price_features(frame)
    add_baseline_features(frame, enabled_features)
    return frame[[c for c in frame if c.startswith("%")]]
