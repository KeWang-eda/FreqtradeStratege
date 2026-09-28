"""Experiment 135R: activate the recent-drop variable before re-running OOS.

The original Experiment 135 audit showed that ``MOMENTUM_MIN_SCORE=0`` made
the penalty inert: negative raw momentum was clipped to zero, while FreqAI
features and targets ignored the penalized score.  This layer fixes that
semantic path without changing the production strategy.

References:
  - ``docs/freqai-feature-engineering.md``: standard features and ``&``
    targets are the model's explicit input/output hooks.
  - ``docs/strategy-customization.md``: entry signals must use the indicators
    that they intend to gate.
  - ``VtechCrypto.py`` and ``VtechCryptoFreqAI.py``: original indicator,
    candidate, feature, and label paths audited in Experiment 135.
"""

import numpy as np
from pandas import DataFrame, Series

from VtechCryptoFreqAIRiskL20RecentDropReturnGrid import (
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase,
)


class _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase(
    _VtechCryptoFreqAIRiskL20RecentDropReturnBase
):
    """Correct the zero-threshold direction and expose the penalty to FreqAI."""

    def _recent_drop_penalty_series(self, dataframe: DataFrame) -> Series:
        returns = dataframe["close"].pct_change()
        drop_flag = returns.rolling(4, min_periods=1).min()
        return Series(
            np.where(
                drop_flag < self.RECENT_DROP_RETURN,
                self.RECENT_DROP_PENALTY,
                1.0,
            ),
            index=dataframe.index,
            dtype=float,
        )

    def _candidate_direction(self, dataframe: DataFrame) -> Series:
        """Require the raw Vtech score to have the requested direction.

        The base implementation clips negative long scores to zero and then
        compares against a zero threshold.  That turns a zero threshold into
        an MA-only gate.  The sign requirement restores the documented
        positive-long/negative-short semantics while retaining the frozen
        score threshold as a separate condition.
        """
        long_candidate = (
            (dataframe["raw_mom_score"] > 0.0)
            & (dataframe["mom_score"] >= self.MOMENTUM_MIN_SCORE)
            & (dataframe["close"] > dataframe["ma20"])
            & (dataframe["ma20"] > 0)
            & (dataframe["volume"] > 0)
        )
        short_candidate = (
            (dataframe["raw_mom_score"] < 0.0)
            & (dataframe["short_mom_score"] >= self.MOMENTUM_MIN_SCORE)
            & (dataframe["close"] < dataframe["ma20"])
            & (dataframe["ma20"] > 0)
            & (dataframe["volume"] > 0)
        )
        return long_candidate.astype(float) - short_candidate.astype(float)

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe = super().feature_engineering_standard(dataframe, metadata, **kwargs)
        penalty = self._recent_drop_penalty_series(dataframe)
        dataframe["%-vtech-recent-drop-penalty"] = penalty
        dataframe["%-vtech-score-penalized"] = (
            self._compress_score(dataframe["raw_mom_score"]) * penalty
        )
        dataframe["%-vtech-short-score-penalized"] = (
            self._compress_score(-dataframe["raw_mom_score"].clip(upper=0.0))
            * penalty
        )
        return dataframe

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe = super().set_freqai_targets(dataframe, metadata, **kwargs)
        penalty = self._recent_drop_penalty_series(dataframe)
        # The L=20 risk branch predicts adverse movement, so a 0.5 signal
        # penalty is represented as 1.5x predicted adverse risk.  This keeps
        # the variable in the actual risk/stake path rather than lowering risk
        # after a recent drop.
        dataframe["&-vtech_adverse"] = dataframe["&-vtech_adverse"] * (
            2.0 - penalty
        )
        return dataframe


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg005(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.005


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg010(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.010


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg015(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.015


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg020(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.020


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg025(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.025


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg030(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.030


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg040(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.040


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg050(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.050


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg075(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.075


class VtechCryptoFreqAIRiskL20RecentDropReturnActivatedNeg100(
    _VtechCryptoFreqAIRiskL20RecentDropReturnActivatedBase
):
    RECENT_DROP_RETURN = -0.100
