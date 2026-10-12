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


def add_expanded_all_features(dataframe: DataFrame, period: int) -> DataFrame:
    """添加按 indicator_periods_candles 展开的周期特征。"""
    close = dataframe["close"].replace(0.0, np.nan)
    dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
    dataframe["%-ema-distance-period"] = ta.EMA(dataframe, timeperiod=period) / close - 1.0
    dataframe["%-sma-distance-period"] = ta.SMA(dataframe, timeperiod=period) / close - 1.0
    dataframe["%-atr-ratio-period"] = ta.ATR(dataframe, timeperiod=period) / close
    dataframe["%-relative-volume-period"] = (
        dataframe["volume"]
        / dataframe["volume"].rolling(period).mean().replace(0.0, np.nan)
    )
    return dataframe


def add_basic_features(dataframe: DataFrame) -> DataFrame:
    """添加当前周期的基础价量特征。"""
    close = dataframe["close"].replace(0.0, np.nan)
    dataframe["%-return"] = close.pct_change()
    dataframe["%-range"] = (dataframe["high"] - dataframe["low"]) / close
    dataframe["%-body"] = dataframe["close"] / dataframe["open"].replace(0.0, np.nan) - 1.0
    dataframe["%-volume-change"] = dataframe["volume"].pct_change()
    return dataframe


def _pure_ohlcv(dataframe: DataFrame) -> DataFrame:
    """给 technical 库只传数值 OHLCV，避免 date/特征列干扰。"""
    return dataframe[["open", "high", "low", "close", "volume"]]


def add_standard_features(dataframe: DataFrame, enabled_features: Iterable[str]) -> DataFrame:
    """添加标准特征与按实验开关启用的 technical 特征。"""
    returns = dataframe["close"].pct_change()
    dataframe["%-volatility-6"] = returns.rolling(6).std()
    dataframe["%-volatility-24"] = returns.rolling(24).std()
    dataframe["%-hour"] = dataframe["date"].dt.hour / 23.0
    dataframe["%-day-of-week"] = dataframe["date"].dt.dayofweek / 6.0

    ohlcv = _pure_ohlcv(dataframe)
    for feature_name in set(enabled_features or []):
        try:
            if feature_name == "laguerre":
                dataframe["%-laguerre"] = ftt.laguerre(ohlcv)
            elif feature_name == "vwmacd":
                result = ftt.vwmacd(ohlcv)
                dataframe["%-vwmacd"] = result["vwmacd"]
                dataframe["%-vwmacd-hist"] = result["hist"]
            elif feature_name == "tke":
                tke, tke_ema = ftt.TKE(ohlcv)
                dataframe["%-tke"] = tke
                dataframe["%-tke-ema"] = tke_ema
            elif feature_name == "vfi":
                vfi, _vfi_ma, vfi_hist = ftt.vfi(ohlcv)
                dataframe["%-vfi"] = vfi
                dataframe["%-vfi-hist"] = vfi_hist
            elif feature_name == "rmi":
                dataframe["%-rmi"] = ftt.RMI(ohlcv)
            else:
                logger.warning("Unknown technical feature ignored: %s", feature_name)
        except Exception as exc:
            # 单个候选失败不应破坏基础特征链；实验日志会保留原因。
            logger.warning("Technical feature %s failed: %s", feature_name, exc)

    dataframe.replace([np.inf, -np.inf], np.nan, inplace=True)
    return dataframe
