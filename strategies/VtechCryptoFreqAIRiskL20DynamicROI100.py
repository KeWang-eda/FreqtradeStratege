"""Experiment 179: dynamic ROI multiplier 1.00."""
from freqtrade.strategy import DecimalParameter
from VtechCryptoFreqAIRiskL20VolumeShock import VtechCryptoFreqAIRiskL20VolumeShock


class VtechCryptoFreqAIRiskL20DynamicROI100(VtechCryptoFreqAIRiskL20VolumeShock):
    roi_atr_multiplier = DecimalParameter(1.00, 1.00, decimals=2, default=1.00, space="sell", optimize=False)
    ROI_ATR_MULTIPLIER = 1.00
