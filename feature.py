"""Compatibility exports; new research code should import quant_strategy.features."""

import _quant_strategy_bootstrap  # noqa: F401
from quant_strategy.features import (
    add_baseline_features,
    add_basic_price_features,
    add_period_expanded_features,
)

__all__ = ["add_baseline_features", "add_basic_price_features", "add_period_expanded_features"]
