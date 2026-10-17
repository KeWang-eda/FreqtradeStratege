"""Freqtrade-compatible entry point for the refactored strategy adapter."""

import _quant_strategy_bootstrap  # noqa: F401
from quant_strategy.execution.freqtrade_strategy import QuantStrategy


class MyStrategy(QuantStrategy):
    """Keep the existing strategy name and framework discovery path."""
