"""Legacy basic price/volume formulas, computed from current and past rows."""

import numpy as np
import pandas as pd


def add_basic_price_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Append causal price features, including fixed lagged returns."""
    close = dataframe["close"].replace(0.0, np.nan)
    dataframe["%-return"] = close.pct_change(fill_method=None)
    dataframe["%-range"] = (dataframe["high"] - dataframe["low"]) / close
    dataframe["%-body"] = dataframe["close"] / dataframe["open"].replace(0.0, np.nan) - 1.0
    dataframe["%-volume-change"] = dataframe["volume"].pct_change(fill_method=None)
    # These use only completed candles at or before the current row.  Keep the
    # group fixed so the researched feature contract cannot drift silently.
    for lag in (1, 2, 3, 6):
        dataframe[f"%-lag-return-{lag}"] = close.pct_change(lag, fill_method=None)
    return dataframe
