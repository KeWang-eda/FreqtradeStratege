"""L=20 equity-risk budget sensitivity at the ROI30 candidate.

ROI30 and Stop60 are frozen from the preceding single-variable ROI study.
Only the current-equity budget per stop event changes, testing whether the
large-window drawdown is caused by compounding exposure rather than signal
direction.

References:
  - ``docs/configuration.md``: dynamic stake compounds with wallet equity.
  - ``docs/strategy-callbacks.md``: ``custom_stake_amount`` is pre-leverage.
  - ``docs/leverage.md``: liquidation buffer and leveraged stop risk.
"""

from VtechCryptoFreqAIRiskL20BudgetGrid import (
    _VtechCryptoFreqAIRiskL20BudgetBase,
)


class _VtechCryptoFreqAIRiskL20BudgetROI30Base(
    _VtechCryptoFreqAIRiskL20BudgetBase
):
    """Keep Stop60 and ROI30 while varying only risk budget."""

    minimal_roi = {"0": 0.30}


class VtechCryptoFreqAIRiskL20Budget05ROI30(
    _VtechCryptoFreqAIRiskL20BudgetROI30Base
):
    """Budget 0.5% of current equity per stop event."""

    RISK_BUDGET = 0.005


class VtechCryptoFreqAIRiskL20Budget1ROI30(
    _VtechCryptoFreqAIRiskL20BudgetROI30Base
):
    """Budget 1% of current equity per stop event."""

    RISK_BUDGET = 0.01


class VtechCryptoFreqAIRiskL20Budget15ROI30(
    _VtechCryptoFreqAIRiskL20BudgetROI30Base
):
    """Budget 1.5% of current equity per stop event."""

    RISK_BUDGET = 0.015


class VtechCryptoFreqAIRiskL20Budget2ROI30(
    _VtechCryptoFreqAIRiskL20BudgetROI30Base
):
    """Control: budget 2% of current equity per stop event."""

    RISK_BUDGET = 0.02


class VtechCryptoFreqAIRiskL20Budget04ROI30(
    _VtechCryptoFreqAIRiskL20BudgetROI30Base
):
    """Research: budget 0.4% of current equity per stop event."""

    RISK_BUDGET = 0.004


class VtechCryptoFreqAIRiskL20Budget045ROI30(
    _VtechCryptoFreqAIRiskL20BudgetROI30Base
):
    """Research: budget 0.45% of current equity per stop event."""

    RISK_BUDGET = 0.0045
