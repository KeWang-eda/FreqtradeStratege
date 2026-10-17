"""Legacy basic price/volume formulas, computed from current and past rows."""

import numpy as np
import pandas as pd


def add_basic_price_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Append single-candle returns, range, body and volume change in place."""
    close = dataframe["close"].replace(0.0, np.nan)
    dataframe["%-return"] = close.pct_change(fill_method=None)
    dataframe["%-range"] = (dataframe["high"] - dataframe["low"]) / close
    dataframe["%-body"] = dataframe["close"] / dataframe["open"].replace(0.0, np.nan) - 1.0
    dataframe["%-volume-change"] = dataframe["volume"].pct_change(fill_method=None)
    return dataframe
