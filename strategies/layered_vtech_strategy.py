"""Layered Vtech strategy entry point.

This is the only Freqtrade entry point in the new framework branch. The layer
adapters are intentionally incomplete; the strategy therefore emits no trade
signals until the contracts are implemented and validated.

References:
  - Freqtrade strategy quickstart.
  - Freqtrade strategy callbacks and leverage documentation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class LayeredVtechStrategy(IStrategy):
    """New layered strategy shell with fail-closed trade behavior."""

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 200
    minimal_roi = {}
    stoploss = -0.15
    trailing_stop = False
    use_exit_signal = True
    max_open_trades = 3
    FRAMEWORK_VERSION = "0.1.0-skeleton"
    DATA_SNAPSHOT_VERSION = "local-feather-v1"
    FEATURE_VERSION = "technical-v1-causal"
    LABEL_VERSION = "adverse-risk-v1"
    MODEL_IDENTIFIER = "layered-vtech-skeleton"
    DEFAULT_LEVERAGE = 2.0
    RISK_BUDGET = 0.02
    LIQUIDATION_BUFFER = 0.05

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict[str, Any]
    ) -> DataFrame:
        """Reserve the indicator boundary for the feature layer."""
        del metadata
        return dataframe

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict[str, Any]
    ) -> DataFrame:
        """Fail closed until selection and risk adapters are implemented."""
        del metadata
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict[str, Any]
    ) -> DataFrame:
        """Reserve exit signals for the exit and risk layers."""
        del metadata
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float:
        """Return the fixed framework default until dynamic L is validated."""
        del pair, current_time, current_rate, proposed_leverage, entry_tag, side, kwargs
        return min(self.DEFAULT_LEVERAGE, float(max_leverage))

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float:
        """Keep the shell conservative until portfolio adapters are verified."""
        del (
            pair,
            current_time,
            current_rate,
            min_stake,
            max_stake,
            leverage,
            entry_tag,
            side,
            kwargs,
        )
        return proposed_stake
