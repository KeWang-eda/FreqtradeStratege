"""模型 I/O 层。

只负责 FreqAI 回归 target、预测读取和阈值判断；不计算技术特征、不直接训练 XGBoost。
"""

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

FREQAI_RETURN_TARGET = "&-s_return"


def set_regression_target(
    dataframe: DataFrame,
    prediction_horizon: int,
    label_scaling_mode: str,
) -> DataFrame:
    """写入 FreqAI 回归标签，支持 raw 和 volnorm 两种尺度。"""
    future_close = dataframe["close"].shift(-prediction_horizon)
    future_return = future_close / dataframe["close"] - 1.0

    if label_scaling_mode == "volnorm":
        atr_ratio = ta.ATR(dataframe, timeperiod=14) / dataframe["close"]
        dataframe[FREQAI_RETURN_TARGET] = future_return / atr_ratio.replace(0.0, np.nan)
    elif label_scaling_mode == "raw":
        dataframe[FREQAI_RETURN_TARGET] = future_return
    else:
        raise ValueError(f"Unsupported regression label mode: {label_scaling_mode}")

    return dataframe


def read_model_prediction(dataframe: DataFrame):
    """读取 FreqAI 输出的回归预测列。"""
    return dataframe[FREQAI_RETURN_TARGET]


def should_enter_long(model_prediction, prediction_ready, entry_threshold: float):
    """返回做多入场条件：预测收益高于入场阈值。"""
    return prediction_ready & (model_prediction > entry_threshold)


def should_enter_short(model_prediction, prediction_ready, entry_threshold: float):
    """返回做空入场条件：预测收益低于负的入场阈值。"""
    return prediction_ready & (model_prediction < -entry_threshold)


def should_exit_long(model_prediction, prediction_ready):
    """返回多仓退出条件：预测转负（阈值 0，不要求超过入场阈值）。"""
    return prediction_ready & (model_prediction < 0)


def should_exit_short(model_prediction, prediction_ready):
    """返回空仓退出条件：预测转正（阈值 0，不要求超过入场阈值）。"""
    return prediction_ready & (model_prediction > 0)
