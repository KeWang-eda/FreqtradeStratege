"""Vtech FreqAI risk strategy with a user-configurable futures leverage.

The leverage value is the only model/trading variable introduced by this
experiment.  It is an ``IntParameter`` in the pre-registered range 1..20;
each selected value must use its own FreqAI identifier because the continuous
adverse-risk target is expressed in leveraged account-risk units.

Risk controls inherited from the validated baseline remain frozen: isolated
margin, a 15% leveraged stoploss, dynamic risk stake mapping, and the
configured ``liquidation_buffer``.  A later experiment may add an explicit
volatility/risk-budget stake cap, but that is intentionally not mixed into
this first leverage comparison.

References:
  - docs/leverage.md and docs/strategy-callbacks.md (leverage callback and
    liquidation buffer semantics)
  - Moreira and Muir (2017), NBER 10.3386/w22208
  - Frazzini and Pedersen (2014), JFE 10.1016/j.jfineco.2013.10.005
"""

import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IntParameter

from VtechCryptoFreqAIRisk import VtechCryptoFreqAIRisk


class VtechCryptoFreqAILeverage(VtechCryptoFreqAIRisk):
    """Expose leverage 1..20 while keeping the baseline risk policy fixed."""

    leverage_value = IntParameter(
        1, 20, default=1, space="buy", optimize=False, load=True
    )

    def _configured_leverage(self) -> float:
        """Return the selected leverage after strategy parameter loading."""
        return float(self.leverage_value.value)

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Scale the same adverse-risk target by the selected leverage."""
        dataframe = self._ensure_vtech_indicators(dataframe, metadata)
        period = self.freqai_info["feature_parameters"]["label_period_candles"]
        direction = self._candidate_direction(dataframe)

        future_low = dataframe["low"].shift(-period).rolling(period).min()
        future_high = dataframe["high"].shift(-period).rolling(period).max()
        long_adverse = (1.0 - future_low / dataframe["close"]).clip(lower=0.0)
        short_adverse = (future_high / dataframe["close"] - 1.0).clip(lower=0.0)
        adverse_move = pd.Series(
            np.where(direction > 0, long_adverse, short_adverse),
            index=dataframe.index,
        )
        fee = float(self.config.get("fee", self.DEFAULT_FEE))
        predicted_risk = self._configured_leverage() * (adverse_move + 2.0 * fee)
        dataframe["&-vtech_adverse"] = predicted_risk.where(direction != 0.0, np.nan)
        return dataframe

    def leverage(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """Return the user-selected leverage, bounded by the exchange limit."""
        return min(self._configured_leverage(), float(max_leverage))
