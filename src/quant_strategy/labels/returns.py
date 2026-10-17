"""Close-to-close labels; future values never enter the feature matrix."""

import numpy as np
import pandas as pd

from quant_strategy.config.schema import LabelConfig
from quant_strategy.market_data.time_index import timeframe_delta

FREQAI_RETURN_TARGET = "&-s_return"


def set_regression_target(
    dataframe: pd.DataFrame,
    prediction_horizon: int,
    label_scaling_mode: str,
    volatility_period: int = 14,
) -> pd.DataFrame:
    """Write the legacy target in place, keeping incomplete labels missing."""
    config = LabelConfig(label_scaling_mode, prediction_horizon, volatility_period)
    close = dataframe["close"].replace(0.0, np.nan)
    target = close.shift(-config.prediction_horizon) / close - 1.0
    if config.mode == "volnorm":
        import talib.abstract as ta

        scale = ta.ATR(dataframe, timeperiod=config.volatility_period) / close
        target = target / scale.replace(0.0, np.nan)
    dataframe[FREQAI_RETURN_TARGET] = target.replace([np.inf, -np.inf], np.nan)
    return dataframe


def build_labels(dataframe: pd.DataFrame, config: LabelConfig, timeframe: str) -> pd.DataFrame:
    """Return labels and future candle CLOSE times (inclusive end points)."""
    labeled = set_regression_target(
        dataframe.copy(), config.prediction_horizon, config.mode, config.volatility_period
    )
    return pd.DataFrame(
        {
            "target": labeled[FREQAI_RETURN_TARGET],
            "label_end_time": dataframe["date"].shift(-config.prediction_horizon)
            + timeframe_delta(timeframe),
        },
        index=dataframe.index,
    )
