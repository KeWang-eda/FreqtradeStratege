"""Experiment 135: retrained grid for ``RECENT_DROP_RETURN``.

Only the recent single-bar return trigger changes.  The penalty magnitude is
held at 0.5, and the L=20 risk, direction budget, ROI, stoploss, model and
pairlist are inherited from the promoted Experiment 134 candidate.

References: local ``docs/freqai-running.md`` (fresh identifiers when labels or
features change), ``docs/backtesting.md`` (independent OOS timeranges), and
``VtechCrypto.py`` (four-bar recent-return trigger implementation).
"""

from VtechCryptoFreqAIRiskL20DirectionBudgetGrid import (
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI20,
)


class _VtechCryptoFreqAIRiskL20RecentDropReturnBase(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI20
):
    """Freeze Experiment 134's candidate and vary one return trigger."""

    LOOKBACK_BARS = 20
    LOOKBACK_BARS_PREV = 22
    MOMENTUM_MIN_SCORE = 0.0
    RECENT_DROP_PENALTY = 0.5
    use_exit_signal = False


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg005(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.005


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg010(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.010


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg015(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.015


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg020(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    """Control: current trigger."""

    RECENT_DROP_RETURN = -0.020


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg025(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.025


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg030(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.030


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg040(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.040


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg050(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.050


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg075(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.075


class VtechCryptoFreqAIRiskL20RecentDropReturnNeg100(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    RECENT_DROP_RETURN = -0.100
