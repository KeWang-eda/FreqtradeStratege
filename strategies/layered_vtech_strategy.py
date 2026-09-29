"""Causal feature control entry point for the layered framework.

This control connects the completed feature and risk boundaries to Freqtrade.
The model and same-timestamp cross-sectional ranking remain separate gates.

References:
  - Historical Vtech FreqAI strategy family on the ``main`` branch.
  - Freqtrade strategy interface and backtesting CLI documentation.
  - ``strategies/feature_layer.py`` for the causal feature contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pandas import DataFrame

from freqtrade.strategy import IStrategy

from feature_layer import build_vtech_model_features


class LayeredVtechStrategy(IStrategy):
    """Run the causal feature control without future or model predictions."""

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

    FRAMEWORK_VERSION = "0.1.0-control"
    DATA_SNAPSHOT_VERSION = "local-feather-v1"
    FEATURE_VERSION = "vtech-base72-plus-momentum6-plus-technical11-v1"
    LABEL_VERSION = "adverse-risk-v1"
    MODEL_IDENTIFIER = "not-used-control-feature-only"
    DEFAULT_LEVERAGE = 2.0
    RISK_BUDGET = 0.02
    LIQUIDATION_BUFFER = 0.05
    RISK_PENALTY = 0.5
    EXECUTION_COST = 0.0015
    MINIMUM_NET_EDGE = 0.0

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict[str, Any]
    ) -> DataFrame:
        """Build only causal features and pair-local execution edges."""
        del metadata
        result = build_vtech_model_features(dataframe, include_technical_candidates=True)
        risk_proxy = result["%-technical_atr_percent_14"].fillna(0.0)
        result["net_long_edge"] = (
            result["%-vtech-score-penalized"]
            - self.RISK_PENALTY * risk_proxy
            - self.EXECUTION_COST
        )
        result["net_short_edge"] = (
            result["%-vtech-short-score-penalized"]
            - self.RISK_PENALTY * risk_proxy
            - self.EXECUTION_COST
        )
        return result

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict[str, Any]
    ) -> DataFrame:
        """Enter when the causal pair-local edge clears the cost floor."""
        del metadata
        dataframe["enter_long"] = (
            (dataframe["net_long_edge"] >= self.MINIMUM_NET_EDGE)
            & (dataframe["volume"] > 0)
        ).astype(int)
        dataframe["enter_short"] = (
            (dataframe["net_short_edge"] >= self.MINIMUM_NET_EDGE)
            & (dataframe["volume"] > 0)
        ).astype(int)
        dataframe["enter_tag"] = "causal-feature-control"
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict[str, Any]
    ) -> DataFrame:
        """Exit on a confirmed opposite directional edge."""
        del metadata
        dataframe["exit_long"] = (
            dataframe["net_short_edge"] >= self.MINIMUM_NET_EDGE
        ).astype(int)
        dataframe["exit_short"] = (
            dataframe["net_long_edge"] >= self.MINIMUM_NET_EDGE
        ).astype(int)
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
        """Keep the control group at fixed 2x, bounded by the exchange."""
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
        """Apply the fixed account-risk budget before exchange rounding."""
        del pair, current_time, current_rate, entry_tag, side, kwargs
        equity = float(self.wallets.get_total_stake_amount())
        if equity <= 0.0 or leverage < 1.0:
            return 0.0
        stop_distance = abs(float(self.stoploss))
        stake = equity * self.RISK_BUDGET / (leverage * stop_distance)
        stake = min(stake, float(proposed_stake), float(max_stake))
        if min_stake is not None and stake < float(min_stake):
            return 0.0
        return max(stake, 0.0)
