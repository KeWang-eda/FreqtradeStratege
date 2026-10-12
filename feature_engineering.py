"""纯特征工程层。

只负责把 OHLCV DataFrame 转成 FreqAI 的 % 特征；不读取 config、不训练模型、不下单。
"""

import logging
from collections.abc import Iterable

import numpy as np
import talib.abstract as ta
import technical.indicators as ftt
from pandas import DataFrame

logger = logging.getLogger(__name__)


def add_period_expanded_features(dataframe: DataFrame, period: int) -> DataFrame:
    """添加按 indicator_periods_candles 逐周期展开的指标特征。

    含累计动量：动量是实测中唯一稳定的方向性信号（IC 约 +0.09），
    而原特征集只有单根收益 %-return，模型无法自行构造多周期累计收益。
    """
    close_series = dataframe["close"].replace(0.0, np.nan)
    dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
    dataframe["%-ema-distance-period"] = (
        ta.EMA(dataframe, timeperiod=period) / close_series - 1.0
    )
    dataframe["%-sma-distance-period"] = (
        ta.SMA(dataframe, timeperiod=period) / close_series - 1.0
    )
    dataframe["%-atr-ratio-period"] = ta.ATR(dataframe, timeperiod=period) / close_series
    dataframe["%-relative-volume-period"] = (
        dataframe["volume"]
        / dataframe["volume"].rolling(period).mean().replace(0.0, np.nan)
    )
    # 累计动量：过去 period 根 K 线的已实现收益（因果，只用已收盘数据）
    dataframe["%-momentum-period"] = close_series / close_series.shift(period) - 1.0
    return dataframe


def add_basic_price_features(dataframe: DataFrame) -> DataFrame:
    """添加当前周期的基础价量特征，不按 period 展开。"""
    close_series = dataframe["close"].replace(0.0, np.nan)
    dataframe["%-return"] = close_series.pct_change()
    dataframe["%-range"] = (dataframe["high"] - dataframe["low"]) / close_series
    dataframe["%-body"] = dataframe["close"] / dataframe["open"].replace(0.0, np.nan) - 1.0
    dataframe["%-volume-change"] = dataframe["volume"].pct_change()
    return dataframe


def _select_ohlcv_columns(dataframe: DataFrame) -> DataFrame:
    """给 technical 库只传数值 OHLCV，避免 date/特征列干扰。"""
    return dataframe[["open", "high", "low", "close", "volume"]]


def add_baseline_features(dataframe: DataFrame, enabled_features: Iterable[str]) -> DataFrame:
    """添加标准波动/时间特征，并按实验开关追加 technical 候选指标。"""
    price_returns = dataframe["close"].pct_change()
    dataframe["%-volatility-6"] = price_returns.rolling(6).std()
    dataframe["%-volatility-24"] = price_returns.rolling(24).std()
    dataframe["%-hour"] = dataframe["date"].dt.hour / 23.0
    dataframe["%-day-of-week"] = dataframe["date"].dt.dayofweek / 6.0

    ohlcv_frame = _select_ohlcv_columns(dataframe)
    for feature_name in set(enabled_features or []):
        try:
            if feature_name == "laguerre":
                dataframe["%-laguerre"] = ftt.laguerre(ohlcv_frame)
            elif feature_name == "vwmacd":
                feature_values = ftt.vwmacd(ohlcv_frame)
                dataframe["%-vwmacd"] = feature_values["vwmacd"]
                dataframe["%-vwmacd-hist"] = feature_values["hist"]
            elif feature_name == "tke":
                tke, tke_ema = ftt.TKE(ohlcv_frame)
                dataframe["%-tke"] = tke
                dataframe["%-tke-ema"] = tke_ema
            elif feature_name == "vfi":
                vfi, _vfi_ma, vfi_hist = ftt.vfi(ohlcv_frame)
                dataframe["%-vfi"] = vfi
                dataframe["%-vfi-hist"] = vfi_hist
            elif feature_name == "rmi":
                dataframe["%-rmi"] = ftt.RMI(ohlcv_frame)
            else:
                logger.warning("Unknown technical feature ignored: %s", feature_name)
        except Exception as exc:
            # 单个候选失败不应破坏基础特征链；实验日志会保留原因。
            logger.warning("Technical feature %s failed: %s", feature_name, exc)

    dataframe.replace([np.inf, -np.inf], np.nan, inplace=True)
    return dataframe
