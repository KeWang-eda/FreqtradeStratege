"""Experiment 174: causal rolling volume-change z-score feature."""

from typing import Any

from freqtrade.strategy import DecimalParameter
from pandas import DataFrame

from VtechCryptoFreqAIRiskL20DynamicROI import VtechCryptoFreqAIRiskL20DynamicROI10


class VtechCryptoFreqAIRiskL20VolumeShock(VtechCryptoFreqAIRiskL20DynamicROI10):
    """Parent 156 plus one normalized volume-shock feature."""

    # Single Hyperopt variable; all signal/features and risk logic stay frozen.
    roi_atr_multiplier = DecimalParameter(0.75, 1.25, decimals=2, default=0.84, space="sell")

    def custom_roi(self, *args: Any, **kwargs: Any) -> float | None:
        self.ROI_ATR_MULTIPLIER = float(self.roi_atr_multiplier.value)
        return super().custom_roi(*args, **kwargs)

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs: Any
    ) -> DataFrame:
        dataframe = super().feature_engineering_standard(dataframe, metadata, **kwargs)
        change = dataframe["volume"].pct_change()
        mean = change.rolling(48, min_periods=24).mean()
        std = change.rolling(48, min_periods=24).std(ddof=0)
        dataframe["%-volume-change-zscore-48"] = (change - mean) / std.replace(0.0, float("nan"))
        return dataframe
