"""Freqtrade-compatible entry point for the refactored strategy adapter."""

from quant.execution.freqtrade_strategy import QuantStrategy


class MyStrategy(QuantStrategy):
    """Keep the existing strategy name and framework discovery path."""
