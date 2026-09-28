"""L=20 dynamic-equity risk-budget grid.

The Stop60 control fixes the only price-risk variable at ``stoploss=-0.60``.
Each research class changes only the fraction of current wallet equity that a
single stop event may consume.  The cap is computed in pre-leverage stake
units, as required by Freqtrade's ``custom_stake_amount`` contract.

References:
  - ``docs/strategy-callbacks.md``: dynamic stake and callback return values.
  - ``docs/stoploss.md``: futures stoploss is account risk under leverage.
  - ``docs/configuration.md``: wallet-based dynamic stake semantics.
"""

import os
import sys

import numpy as np

from freqtrade.strategy import DecimalParameter, IntParameter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "strategies"))

from VtechCryptoFreqAILeverage import VtechCryptoFreqAILeverage


class _VtechCryptoFreqAIRiskL20BudgetBase(VtechCryptoFreqAILeverage):
    """Current L=20 model/risk parameters with a Stop60 floor."""

    leverage_value = IntParameter(
        1, 20, default=20, space="buy", optimize=False, load=True
    )
    long_min_utility = DecimalParameter(
        -0.060, 0.005, default=-0.060, decimals=3, space="buy", load=False
    )
    short_min_utility = DecimalParameter(
        -0.060, 0.005, default=-0.060, decimals=3, space="buy", load=False
    )
    di_max = DecimalParameter(
        0.30, 2.00, default=1.90, decimals=2, space="buy", load=False
    )
    min_stake_fraction = DecimalParameter(
        0.20, 1.00, default=0.79, decimals=2, space="buy", load=False
    )
    risk_z_center = DecimalParameter(
        -1.00, 1.00, default=0.49, decimals=2, space="buy", load=False
    )
    stoploss = -0.60

    def custom_stake_amount(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """Apply the baseline z-map, then cap stake by current equity risk."""
        try:
            baseline_stake = super().custom_stake_amount(
                pair=pair, current_time=current_time, current_rate=current_rate,
                proposed_stake=proposed_stake, min_stake=min_stake, max_stake=max_stake,
                leverage=leverage, entry_tag=entry_tag, side=side, **kwargs,
            )
        except (AttributeError, TypeError, ValueError, IndexError, OverflowError, ZeroDivisionError):
            return 0.0
        try:
            equity = float(self.wallets.get_total_stake_amount())
        except (AttributeError, TypeError, ValueError, OverflowError, ZeroDivisionError):
            # No valid wallet balance means the account-risk cap cannot be enforced.
            # docs/strategy-callbacks.md: returning zero prevents the entry.
            return 0.0
        if not np.isfinite(equity) or equity <= 0.0:
            return 0.0

        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            prediction = np.nan
            if dataframe is not None and not dataframe.empty:
                prediction = float(dataframe.iloc[-1].get("&-vtech_adverse", np.nan))
        except (AttributeError, TypeError, ValueError, IndexError, OverflowError, ZeroDivisionError):
            return 0.0
        account_risk_per_full_stake = max(
            abs(float(self.stoploss)), prediction if np.isfinite(prediction) else 0.0, 1e-6
        )
        risk_cap = equity * float(self.RISK_BUDGET) / account_risk_per_full_stake
        risk_cap = min(risk_cap, float(max_stake), float(proposed_stake))
        if min_stake is not None and risk_cap < float(min_stake):
            return 0.0
        return max(min(baseline_stake, risk_cap), 0.0)


class VtechCryptoFreqAIRiskL20Budget1(_VtechCryptoFreqAIRiskL20BudgetBase):
    """Budget 1% of current equity per full-stop event."""

    RISK_BUDGET = 0.01


class VtechCryptoFreqAIRiskL20Budget2(_VtechCryptoFreqAIRiskL20BudgetBase):
    """Budget 2% of current equity per full-stop event."""

    RISK_BUDGET = 0.02


class VtechCryptoFreqAIRiskL20Budget3(_VtechCryptoFreqAIRiskL20BudgetBase):
    """Budget 3% of current equity per full-stop event."""

    RISK_BUDGET = 0.03


class VtechCryptoFreqAIRiskL20Budget5(_VtechCryptoFreqAIRiskL20BudgetBase):
    """Budget 5% of current equity per full-stop event."""

    RISK_BUDGET = 0.05
