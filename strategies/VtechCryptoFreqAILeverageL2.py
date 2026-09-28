"""Fixed 2x leverage control for the preregistered leverage grid."""

from freqtrade.strategy import IntParameter

from VtechCryptoFreqAILeverage import VtechCryptoFreqAILeverage


class VtechCryptoFreqAILeverageL2(VtechCryptoFreqAILeverage):
    """Keep the leverage experiment's only changed variable at 2x."""

    leverage_value = IntParameter(1, 20, default=2, space="buy", optimize=False, load=True)
