"""Vtech 1h 多空规则的 FreqAI/XGBoost 风险过滤版本.

Vtech 决定交易方向，FreqAI 只判断候选是否值得执行。训练标签是未来 8 根
K 线的方向收益，扣除最大不利波动和往返手续费，避免重复旧实验中已证明
接近随机的“直接预测下一根涨跌”路径。

实现参考:
  - freqtrade/templates/FreqaiExampleStrategy.py
  - docs/freqai-feature-engineering.md 与 docs/freqai-running.md
  - VtechCrypto.py、VtechCryptoShort.py、VtechCryptoLongShort.py
"""
import os
import sys

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame, Series

from freqtrade.strategy import DecimalParameter

# Hyperopt 的 loky worker 反序列化继承链时不会自动加入策略目录。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from VtechCryptoLongShort import VtechCryptoLongShort
from VtechCryptoShort import VtechCryptoShort


class VtechCryptoFreqAI(VtechCryptoLongShort):
    """使用 XGBoost 过滤高风险 Vtech 候选，保留原策略退出逻辑."""

    timeframe = "1h"
    startup_candle_count = 50

    LABEL_RISK_PENALTY = 1.0
    DEFAULT_FEE = 0.0005
    SCORE_CLIP = 1_000_000.0

    long_min_utility = DecimalParameter(
        -0.060, 0.005, default=-0.030, decimals=3, space="buy"
    )
    short_min_utility = DecimalParameter(
        -0.060, 0.005, default=-0.030, decimals=3, space="buy"
    )
    di_max = DecimalParameter(0.20, 1.00, default=0.70, decimals=2, space="buy")

    plot_config = {
        "main_plot": {},
        "subplots": {
            "utility": {"&-vtech_utility": {"color": "blue"}},
            "prediction": {"do_predict": {"color": "brown"}},
        },
    }

    @classmethod
    def _compress_score(cls, score: Series) -> Series:
        """把可能指数放大的年化动量分数压到稳定、保留符号的尺度."""
        clipped = score.clip(lower=-cls.SCORE_CLIP, upper=cls.SCORE_CLIP).fillna(0.0)
        return np.sign(clipped) * np.log1p(clipped.abs())

    def _ensure_vtech_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """保证 FreqAI 独立构造训练表时也拥有 Vtech 指标列."""
        required = {
            "raw_mom_score",
            "raw_mom_score_prev",
            "mom_score",
            "mom_score_prev",
            "short_mom_score",
            "short_mom_score_prev",
            "ma20",
        }
        if required.issubset(dataframe.columns):
            return dataframe
        return VtechCryptoShort.populate_indicators(self, dataframe, metadata)

    def _candidate_direction(self, dataframe: DataFrame) -> Series:
        """返回 Vtech 候选方向：多头 1、空头 -1、无候选 0."""
        long_candidate = (
            (dataframe["mom_score"] >= self.MOMENTUM_MIN_SCORE)
            & (dataframe["close"] > dataframe["ma20"])
            & (dataframe["ma20"] > 0)
            & (dataframe["volume"] > 0)
        )
        short_candidate = (
            (dataframe["short_mom_score"] >= self.MOMENTUM_MIN_SCORE)
            & (dataframe["close"] < dataframe["ma20"])
            & (dataframe["ma20"] > 0)
            & (dataframe["volume"] > 0)
        )
        return long_candidate.astype(float) - short_candidate.astype(float)

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """加入旧实验中相对稳定的动量、资金流和波动率特征."""
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-mfi-period"] = ta.MFI(dataframe, timeperiod=period)
        dataframe["%-roc-period"] = ta.ROC(dataframe, timeperiod=period)
        dataframe["%-atr-ratio-period"] = (
            ta.ATR(dataframe, timeperiod=period) / dataframe["close"]
        )
        dataframe["%-relative-volume-period"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )
        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """加入单根价格、振幅和成交量变化特征."""
        dataframe["%-return"] = dataframe["close"].pct_change()
        dataframe["%-candle-body"] = dataframe["close"] / dataframe["open"] - 1.0
        dataframe["%-candle-range"] = dataframe["high"] / dataframe["low"] - 1.0
        dataframe["%-volume-change"] = dataframe["volume"].pct_change()
        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """加入 Vtech 状态、市场时钟和 8 小时资金费率特征."""
        dataframe = self._ensure_vtech_indicators(dataframe, metadata)
        current_score = self._compress_score(dataframe["raw_mom_score"])
        previous_score = self._compress_score(dataframe["raw_mom_score_prev"])
        dataframe["%-vtech-score"] = current_score
        dataframe["%-vtech-score-change"] = current_score - previous_score
        dataframe["%-vtech-ma-distance"] = dataframe["close"] / dataframe["ma20"] - 1.0
        dataframe["%-vtech-direction"] = self._candidate_direction(dataframe)

        returns = dataframe["close"].pct_change()
        dataframe["%-volatility-8"] = returns.rolling(8).std()
        dataframe["%-volatility-24"] = returns.rolling(24).std()
        dataframe["%-hour"] = dataframe["date"].dt.hour
        dataframe["%-day-of-week"] = dataframe["date"].dt.dayofweek

        funding = pd.Series(0.0, index=dataframe.index)
        try:
            from freqtrade.data.history import load_pair_history
            from freqtrade.enums import CandleType

            funding_data = load_pair_history(
                pair=metadata["pair"],
                timeframe=self.timeframe,
                datadir=self.config["datadir"],
                timerange=None,
                candle_type=CandleType.FUNDING_RATE,
            )
            if funding_data is not None and not funding_data.empty:
                funding_history = funding_data.set_index(
                    pd.to_datetime(funding_data["date"], utc=True)
                )["open"]
                candle_dates = pd.to_datetime(dataframe["date"], utc=True)
                funding = pd.Series(
                    funding_history.reindex(candle_dates, method="ffill").fillna(0.0).to_numpy(),
                    index=dataframe.index,
                )
        except (KeyError, OSError, ValueError):
            funding = pd.Series(0.0, index=dataframe.index)

        dataframe["%-funding"] = funding
        dataframe["%-funding-ma-8h"] = funding.rolling(8, min_periods=1).mean()
        dataframe["%-funding-deviation"] = (
            funding - dataframe["%-funding-ma-8h"]
        )
        return dataframe

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """仅用 Vtech 候选训练未来收益减最大不利波动的效用标签."""
        dataframe = self._ensure_vtech_indicators(dataframe, metadata)
        period = self.freqai_info["feature_parameters"]["label_period_candles"]
        direction = self._candidate_direction(dataframe)

        # shift(-N).rolling(N) 在位置 t 聚合 t+1...t+N，仅用于训练标签。
        future_mean = dataframe["close"].shift(-period).rolling(period).mean()
        future_low = dataframe["low"].shift(-period).rolling(period).min()
        future_high = dataframe["high"].shift(-period).rolling(period).max()
        directional_return = direction * (future_mean / dataframe["close"] - 1.0)
        long_adverse = (1.0 - future_low / dataframe["close"]).clip(lower=0.0)
        short_adverse = (future_high / dataframe["close"] - 1.0).clip(lower=0.0)
        adverse_move = pd.Series(
            np.where(direction > 0, long_adverse, short_adverse),
            index=dataframe.index,
        )

        fee = float(self.config.get("fee", self.DEFAULT_FEE))
        round_trip_cost = 2.0 * fee
        utility = self.LEVERAGE * (
            directional_return
            - self.LABEL_RISK_PENALTY * adverse_move
            - round_trip_cost
        )
        dataframe["&-vtech_utility"] = utility.where(direction != 0.0, np.nan)
        return dataframe

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """先生成规则指标，再由 FreqAI 训练或返回风险调整效用预测."""
        dataframe = VtechCryptoShort.populate_indicators(self, dataframe, metadata)
        self.freqai_info = self.config["freqai"]
        return self.freqai.start(dataframe, metadata, self)

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """Vtech 决定方向；预测效用和 DI 只做准入过滤."""
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        direction = self._candidate_direction(dataframe)
        model_ready = dataframe["do_predict"] == 1
        within_distribution = dataframe["DI_values"] <= self.di_max.value

        dataframe.loc[
            model_ready
            & within_distribution
            & (direction == 1.0)
            & (dataframe["&-vtech_utility"] >= self.long_min_utility.value),
            ["enter_long", "enter_tag"],
        ] = (1, "vtech_ml_long")
        dataframe.loc[
            model_ready
            & within_distribution
            & (direction == -1.0)
            & (dataframe["&-vtech_utility"] >= self.short_min_utility.value),
            ["enter_short", "enter_tag"],
        ] = (1, "vtech_ml_short")
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """保留基线的多空动量衰减退出，隔离 ML 的唯一作用为入场过滤."""
        return VtechCryptoLongShort.populate_exit_trend(self, dataframe, metadata)
