"""模型 I/O 层。

只负责 FreqAI 回归 target、预测读取和阈值判断；不计算技术特征、不直接训练 XGBoost。
"""

import numpy as np
import talib.abstract as ta
from pandas import DataFrame, Series

RETURN_LABEL = "&-s_return"


def make_next_direction_labels(
    close: Series, horizon: int = 1, threshold: float = 0.002
) -> Series:
    """保留的三分类兼容标签函数，回归主链不调用。"""
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    future_close = close.shift(-horizon)
    future_return = future_close / close - 1.0
    labels = Series(
        np.select(
            [future_return > threshold, future_return < -threshold],
            ["up", "down"],
            default="flat",
        ),
        index=close.index,
        dtype="object",
    )
    labels.loc[future_close.isna()] = np.nan
    return labels


def set_return_target(
    dataframe: DataFrame,
    horizon: int,
    label_mode: str,
) -> DataFrame:
    """写入 FreqAI 回归标签，支持 raw 和 volnorm 两种尺度。"""
    future_close = dataframe["close"].shift(-horizon)
    future_return = future_close / dataframe["close"] - 1.0

    if label_mode == "volnorm":
        atr_ratio = ta.ATR(dataframe, timeperiod=14) / dataframe["close"]
        dataframe[RETURN_LABEL] = future_return / atr_ratio.replace(0.0, np.nan)
    elif label_mode == "raw":
        dataframe[RETURN_LABEL] = future_return
    else:
        raise ValueError(f"Unsupported regression label mode: {label_mode}")

    return dataframe


def read_prediction_return(dataframe: DataFrame):
    """读取 FreqAI 输出的回归预测列。"""
    return dataframe[RETURN_LABEL]


def long_signal(prediction_return, ready, threshold: float):
    """返回做多条件。"""
    return ready & (prediction_return > threshold)


def short_signal(prediction_return, ready, threshold: float):
    """返回做空条件。"""
    return ready & (prediction_return < -threshold)


def exit_long_signal(prediction_return, ready):
    return ready & (prediction_return < 0)


def exit_short_signal(prediction_return, ready):
    return ready & (prediction_return > 0)
