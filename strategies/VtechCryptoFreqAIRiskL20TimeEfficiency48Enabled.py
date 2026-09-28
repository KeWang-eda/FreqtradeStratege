"""Experiment 181: enable custom_exit and apply the 48h stale-trade rule."""
from VtechCryptoFreqAIRiskL20TimeEfficiency48 import VtechCryptoFreqAIRiskL20TimeEfficiency48


class VtechCryptoFreqAIRiskL20TimeEfficiency48Enabled(VtechCryptoFreqAIRiskL20TimeEfficiency48):
    use_exit_signal = True
