"""Deterministic optional indicators; critical computation failures propagate."""

from collections.abc import Iterable

import numpy as np
import pandas as pd

from quant.config.schema import validate_features


def add_baseline_features(dataframe: pd.DataFrame, enabled_features: Iterable[str]) -> pd.DataFrame:
    """Add historical volatility, UTC calendar fields and requested indicators."""
    names = tuple(enabled_features)
    validate_features(names)
    returns = dataframe["close"].pct_change(fill_method=None)
    dataframe["%-volatility-6"] = returns.rolling(6).std()
    dataframe["%-volatility-24"] = returns.rolling(24).std()
    dataframe["%-hour"] = dataframe["date"].dt.hour / 23.0
    dataframe["%-day-of-week"] = dataframe["date"].dt.dayofweek / 6.0
    if names:
        import technical.indicators as indicators

        ohlcv = dataframe[["open", "high", "low", "close", "volume"]]
        for name in sorted(set(names)):
            if name == "laguerre":
                dataframe["%-laguerre"] = indicators.laguerre(ohlcv)
            elif name == "vwmacd":
                values = indicators.vwmacd(ohlcv)
                dataframe["%-vwmacd"] = values["vwmacd"]
                dataframe["%-vwmacd-hist"] = values["hist"]
            elif name == "tke":
                dataframe["%-tke"], dataframe["%-tke-ema"] = indicators.TKE(ohlcv)
            elif name == "vfi":
                dataframe["%-vfi"], _, dataframe["%-vfi-hist"] = indicators.vfi(ohlcv)
            elif name == "rmi":
                dataframe["%-rmi"] = indicators.RMI(ohlcv)
    columns = [c for c in dataframe if c.startswith("%")]
    dataframe[columns] = dataframe[columns].replace([np.inf, -np.inf], np.nan)
    return dataframe
