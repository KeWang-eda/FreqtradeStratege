"""Experiment 136: single-variable recent-drop penalty grid.

Only ``RECENT_DROP_PENALTY`` changes.  The activated direction semantics and
``RECENT_DROP_RETURN=-0.020`` are frozen from Experiment 135R.

References:
  - ``docs/strategy-customization.md``: entry columns must represent the
    signal being tested.
  - ``docs/strategy-callbacks.md``: signal, ROI, and stoploss callbacks have
    separate responsibilities; this experiment does not change exits.
  - ``docs/freqai-feature-engineering.md``: ``%`` features and ``&`` labels
    are explicit FreqAI hooks.
"""

from VtechCryptoFreqAIRiskL20RecentDropReturnActivated import (
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase,
)


class _VtechCryptoFreqAIRiskL20RecentDropPenaltyBase(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    """Freeze the 135R trigger and vary only the penalty magnitude."""

    RECENT_DROP_RETURN = -0.020


class VtechCryptoFreqAIRiskL20RecentDropPenaltyP000(
    _VtechCryptoFreqAIRiskL20RecentDropPenaltyBase
):
    RECENT_DROP_PENALTY = 0.0


class VtechCryptoFreqAIRiskL20RecentDropPenaltyP025(
    _VtechCryptoFreqAIRiskL20RecentDropPenaltyBase
):
    RECENT_DROP_PENALTY = 0.25


class VtechCryptoFreqAIRiskL20RecentDropPenaltyP050(
    _VtechCryptoFreqAIRiskL20RecentDropPenaltyBase
):
    """Control inherited from Experiment 135R."""

    RECENT_DROP_PENALTY = 0.5


class VtechCryptoFreqAIRiskL20RecentDropPenaltyP075(
    _VtechCryptoFreqAIRiskL20RecentDropPenaltyBase
):
    RECENT_DROP_PENALTY = 0.75


class VtechCryptoFreqAIRiskL20RecentDropPenaltyP100(
    _VtechCryptoFreqAIRiskL20RecentDropPenaltyBase
):
    RECENT_DROP_PENALTY = 1.0
