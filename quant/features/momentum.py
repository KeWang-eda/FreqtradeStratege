"""Period-specific legacy indicators with unambiguous column names."""

import numpy as np
import pandas as pd
import talib.abstract as ta

from quant.config.schema import positive_int


def add_period_expanded_features(dataframe: pd.DataFrame, period: int) -> pd.DataFrame:
    """Append indicators for one period; different periods cannot overwrite."""
    positive_int(period, "indicator period", 2)
    close = dataframe["close"].replace(0.0, np.nan)
    dataframe[f"%-rsi-period-{period}"] = ta.RSI(dataframe, timeperiod=period)
    dataframe[f"%-ema-distance-period-{period}"] = (
        ta.EMA(dataframe, timeperiod=period) / close - 1.0
    )
    dataframe[f"%-sma-distance-period-{period}"] = (
        ta.SMA(dataframe, timeperiod=period) / close - 1.0
    )
    dataframe[f"%-atr-ratio-period-{period}"] = ta.ATR(dataframe, timeperiod=period) / close
    dataframe[f"%-relative-volume-period-{period}"] = dataframe["volume"] / dataframe[
        "volume"
    ].rolling(period).mean().replace(0.0, np.nan)
    dataframe[f"%-momentum-period-{period}"] = close / close.shift(period) - 1.0
    return dataframe
