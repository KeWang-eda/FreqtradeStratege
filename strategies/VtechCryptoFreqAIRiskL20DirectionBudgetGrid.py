"""L=20 direction-specific collateral-ratio diagnostic.

The inherited candidate budgets each stop event at 0.45% of current equity.
These leaves keep that risk-budget implementation and scale only the proposed
stake by a long/short collateral ratio.  A 50/50 class is therefore an exact
control; 25/75 and 75/25 shift exposure between directions while keeping the
same signal, FreqAI model, ROI, stoploss, and leverage.

References:
  - ``docs/strategy-callbacks.md``: ``custom_stake_amount`` receives the
    proposed pre-leverage stake and may return a bounded value.
  - ``docs/freqai-running.md``: unchanged features/identifier reuse saved
    predictions.
  - ``docs/leverage.md``: collateral and liquidation must be audited with the
    leveraged stop policy.
"""

import numpy as np

from freqtrade.strategy import DecimalParameter

from VtechCryptoFreqAIRiskL20BudgetGrid import (
    _VtechCryptoFreqAIRiskL20BudgetBase,
)
from VtechCryptoFreqAIRiskL20BudgetROI30Grid import (
    VtechCryptoFreqAIRiskL20Budget045ROI30,
)


class _VtechCryptoFreqAIRiskL20DirectionBudgetBase(
    VtechCryptoFreqAIRiskL20Budget045ROI30
):
    """Apply a direction-specific account-risk budget."""

    LONG_SHARE = 0.50
    # Existing classes already predict leveraged account risk.  A price-risk
    # label research class can set this to 20 when converting its prediction.
    PREDICTION_ACCOUNT_MULTIPLIER = 1.0
    # When set, the multiplier is applied only to predictions at or above this
    # account-risk threshold.  None preserves the global-multiplier behavior.
    PREDICTION_RISK_THRESHOLD = None

    def custom_stake_amount(
        self,
        pair,
        current_time,
        current_rate,
        proposed_stake,
        min_stake,
        max_stake,
        leverage,
        entry_tag,
        side,
        **kwargs,
    ):
        long_share = float(self.LONG_SHARE)
        side_share = long_share if side == "long" else 1.0 - long_share

        # Call the inherited z-score map only.  The next parent method also
        # applies the global risk cap, so reproducing that small calculation
        # here is necessary to make the direction ratio affect the cap.
        try:
            baseline_stake = super(_VtechCryptoFreqAIRiskL20BudgetBase, self).custom_stake_amount(
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
        prediction_multiplier = float(self.PREDICTION_ACCOUNT_MULTIPLIER)
        threshold = self.PREDICTION_RISK_THRESHOLD
        if threshold is not None and (
            not np.isfinite(prediction) or prediction < float(threshold)
        ):
            prediction_multiplier = 1.0
        account_risk_per_full_stake = max(
            abs(float(self.stoploss)),
            (
                prediction * prediction_multiplier
                if np.isfinite(prediction)
                else 0.0
            ),
            1e-6,
        )
        direction_budget = float(self.RISK_BUDGET) * 2.0 * side_share
        risk_cap = equity * direction_budget / account_risk_per_full_stake
        risk_cap = min(risk_cap, float(max_stake), float(proposed_stake))
        if min_stake is not None and risk_cap < float(min_stake):
            return 0.0
        return max(min(baseline_stake, risk_cap), 0.0)


class VtechCryptoFreqAIRiskL20DirectionBudget5050(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Control: equal long/short collateral ratio."""

    LONG_SHARE = 0.50


class VtechCryptoFreqAIRiskL20DirectionBudget2575(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Research: 25% long collateral and 75% short collateral."""

    LONG_SHARE = 0.25


class VtechCryptoFreqAIRiskL20DirectionBudget7525(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Research: 75% long collateral and 25% short collateral."""

    LONG_SHARE = 0.75


class VtechCryptoFreqAIRiskL20DirectionBudget4060(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Supplement: 40% long collateral and 60% short collateral."""

    LONG_SHARE = 0.40


class VtechCryptoFreqAIRiskL20DirectionBudget3070(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Supplement: 30% long collateral and 70% short collateral."""

    LONG_SHARE = 0.30


class VtechCryptoFreqAIRiskL20DirectionBudget2080(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Supplement: 20% long collateral and 80% short collateral."""

    LONG_SHARE = 0.20


class VtechCryptoFreqAIRiskL20DirectionBudget225775(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Fine-grid point: 22.5% long collateral and 77.5% short collateral."""

    LONG_SHARE = 0.225


class VtechCryptoFreqAIRiskL20DirectionBudget275725(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Fine-grid point: 27.5% long collateral and 72.5% short collateral."""

    LONG_SHARE = 0.275


class VtechCryptoFreqAIRiskL20DirectionBudget225775Center075(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Single-variable follow-up: move the z-score center from 0.49 to 0.75."""

    risk_z_center = DecimalParameter(
        -1.00, 1.00, default=0.75, decimals=2, space="buy", load=False
    )


class VtechCryptoFreqAIRiskL20DirectionBudget225775Stop45(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Stop-distance follow-up: 45% account-risk stop at 20x leverage."""

    stoploss = -0.45


class VtechCryptoFreqAIRiskL20DirectionBudget225775Stop75(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Stop-distance follow-up: 75% account-risk stop at 20x leverage."""

    stoploss = -0.75


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget040(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Risk-budget follow-up: 0.40% of current equity per stop event."""

    RISK_BUDGET = 0.0040


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Risk-budget follow-up: 0.50% of current equity per stop event."""

    RISK_BUDGET = 0.0050


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget055(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Risk-budget follow-up: 0.55% of current equity per stop event."""

    RISK_BUDGET = 0.0055


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget0505(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Fine-grid point: 0.505% of current equity per stop event."""

    RISK_BUDGET = 0.00505


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget0510(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Fine-grid point: 0.510% of current equity per stop event."""

    RISK_BUDGET = 0.00510


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget0515(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Fine-grid point: 0.515% of current equity per stop event."""

    RISK_BUDGET = 0.00515


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget0520(
    VtechCryptoFreqAIRiskL20DirectionBudget225775
):
    """Fine-grid point: 0.520% of current equity per stop event."""

    RISK_BUDGET = 0.00520


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Risk125(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Risk-calibration follow-up: multiply predicted account risk by 1.25."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.25


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Risk150(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Risk-calibration follow-up: multiply predicted account risk by 1.50."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Risk200(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Risk-calibration follow-up: multiply predicted account risk by 2.00."""

    PREDICTION_ACCOUNT_MULTIPLIER = 2.00


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Ratio2000(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Fine-grid point: 20.00% long and 80.00% short collateral."""

    LONG_SHARE = 0.2000


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Ratio2125(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Fine-grid point: 21.25% long and 78.75% short collateral."""

    LONG_SHARE = 0.2125


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Ratio2275(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Fine-grid point: 22.75% long and 77.25% short collateral."""

    LONG_SHARE = 0.2275


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Ratio2300(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Fine-grid point: 23.00% long and 77.00% short collateral."""

    LONG_SHARE = 0.2300


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Ratio2325(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Fine-grid point: 23.25% long and 76.75% short collateral."""

    LONG_SHARE = 0.2325


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Ratio2350(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Fine-grid point: 23.50% long and 76.50% short collateral."""

    LONG_SHARE = 0.2350


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050DI075(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Research: reject candidates with DI values above 0.75."""

    di_max = DecimalParameter(
        0.30, 2.00, default=0.75, decimals=2, space="buy", optimize=False, load=False
    )


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050DI100(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Research: reject candidates with DI values above 1.00."""

    di_max = DecimalParameter(
        0.30, 2.00, default=1.00, decimals=2, space="buy", optimize=False, load=False
    )


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050DI150(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Research: reject candidates with DI values above 1.50."""

    di_max = DecimalParameter(
        0.30, 2.00, default=1.50, decimals=2, space="buy", optimize=False, load=False
    )


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050DI175(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Research: reject candidates with DI values above 1.75."""

    di_max = DecimalParameter(
        0.30, 2.00, default=1.75, decimals=2, space="buy", optimize=False, load=False
    )


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Ratio2375(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Fine-grid point: 23.75% long and 76.25% short collateral."""

    LONG_SHARE = 0.2375


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Ratio2500(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Fine-grid point: 25.00% long and 75.00% short collateral."""

    LONG_SHARE = 0.2500


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail150TINF(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Control: a 1.5x tail multiplier with an unreachable activation threshold."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = np.inf


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail150T060(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: activate 1.5x predicted risk at 0.60."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = 0.60


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail150T075(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: activate 1.5x predicted risk at 0.75."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = 0.75


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail150T090(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: activate 1.5x predicted risk at 0.90."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = 0.90


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail150T100(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: activate 1.5x predicted risk at 1.00."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = 1.00


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail150T0925(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: activate 1.5x predicted risk at 0.925."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = 0.925


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail150T0950(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: activate 1.5x predicted risk at 0.950."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = 0.950


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail150T0975(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: activate 1.5x predicted risk at 0.975."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = 0.975


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail090M100(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Control: fixed 0.90 risk threshold with a neutral 1.00x multiplier."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.00
    PREDICTION_RISK_THRESHOLD = 0.90


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail090M110(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: apply 1.10x predicted risk at the 0.90 threshold."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.10
    PREDICTION_RISK_THRESHOLD = 0.90


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail090M125(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: apply 1.25x predicted risk at the 0.90 threshold."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.25
    PREDICTION_RISK_THRESHOLD = 0.90


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Tail090M150(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Tail calibration: apply 1.50x predicted risk at the 0.90 threshold."""

    PREDICTION_ACCOUNT_MULTIPLIER = 1.50
    PREDICTION_RISK_THRESHOLD = 0.90


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Span150(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Risk-map sensitivity: narrow z-score span to 1.50."""

    RISK_Z_SPAN = 1.50


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Span225(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Risk-map sensitivity: widen z-score span to 2.25."""

    RISK_Z_SPAN = 2.25


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050Span300(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """Risk-map sensitivity: widen z-score span to 3.00."""

    RISK_Z_SPAN = 3.00


class VtechCryptoFreqAIRiskL20DirectionBudget1090(
    _VtechCryptoFreqAIRiskL20DirectionBudgetBase
):
    """Supplement: 10% long collateral and 90% short collateral."""

    LONG_SHARE = 0.10


class _VtechCryptoFreqAIRiskL20ROIFineBase(
    VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050
):
    """ROI-only sensitivity on the current L=20 pseudo-Huber control.

    Freqtrade applies ``minimal_roi`` independently of strategy exit signals;
    this family therefore changes only the immediate ROI threshold while
    reusing the same prediction files and dynamic risk-cap callback.
    See ``docs/strategy-customization.md`` and ``docs/backtesting.md``.
    """


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI00(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: disable the ROI exit."""

    minimal_roi = {}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI01(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 1%."""

    minimal_roi = {"0": 0.01}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI02(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 2%."""

    minimal_roi = {"0": 0.02}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI03(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 3%."""

    minimal_roi = {"0": 0.03}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI04(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 4%."""

    minimal_roi = {"0": 0.04}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI05(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 5%."""

    minimal_roi = {"0": 0.05}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI06(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 6%."""

    minimal_roi = {"0": 0.06}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI08(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 8%."""

    minimal_roi = {"0": 0.08}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI10(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 10%."""

    minimal_roi = {"0": 0.10}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI12(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 12%."""

    minimal_roi = {"0": 0.12}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI15(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 15%."""

    minimal_roi = {"0": 0.15}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI20(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 20%."""

    minimal_roi = {"0": 0.20}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI25(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 25%."""

    minimal_roi = {"0": 0.25}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI30(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Control: immediate ROI threshold of 30%."""

    minimal_roi = {"0": 0.30}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI35(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 35%."""

    minimal_roi = {"0": 0.35}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI40(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 40%."""

    minimal_roi = {"0": 0.40}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI50(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 50%."""

    minimal_roi = {"0": 0.50}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI60(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 60%."""

    minimal_roi = {"0": 0.60}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI80(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 80%."""

    minimal_roi = {"0": 0.80}


class VtechCryptoFreqAIRiskL20DirectionBudget225775Budget050ROI100(
    _VtechCryptoFreqAIRiskL20ROIFineBase
):
    """Research: immediate ROI threshold of 100%."""

    minimal_roi = {"0": 1.00}
