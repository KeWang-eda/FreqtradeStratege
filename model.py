"""Legacy imports retained while labels, signals and portfolio have separate owners."""

import _quant_strategy_bootstrap  # noqa: F401
from quant_strategy.execution.signals import (
    read_model_prediction,
    should_enter_long,
    should_enter_short,
)
from quant_strategy.labels import FREQAI_RETURN_TARGET, set_regression_target
from quant_strategy.portfolio import (
    PoolCandidate,
    TargetPosition,
    build_candidate,
    resolve_target_position,
)
from quant_strategy.portfolio import decide_position_action as _decide_position_action


def decide_position_action(
    held_pair: str | None, held_side: str | None, target: TargetPosition
) -> tuple[str, str | None]:
    """Preserve tuple results for callers of the old model module."""
    decision = _decide_position_action(held_pair, held_side, target)
    return decision.action, decision.reason


__all__ = [
    "FREQAI_RETURN_TARGET",
    "PoolCandidate",
    "TargetPosition",
    "build_candidate",
    "decide_position_action",
    "read_model_prediction",
    "resolve_target_position",
    "set_regression_target",
    "should_enter_long",
    "should_enter_short",
]
