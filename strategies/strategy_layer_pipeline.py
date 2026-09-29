"""Explicit composition boundary for the layered strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FRAMEWORK_VERSION = "0.1.0-skeleton"


@dataclass(frozen=True, slots=True)
class StrategyRunContext:
    """Immutable identity shared by one experiment run."""

    experiment_id: str
    parent_commit: str
    strategy_version: str
    feature_version: str
    label_version: str
    model_identifier: str
    data_snapshot: str


@dataclass(frozen=True, slots=True)
class StrategyRunResult:
    """Artifacts that a combined run must persist."""

    context: StrategyRunContext
    pool_snapshot: Any
    features: Any
    predictions: Any
    candidates: Any
    position_targets: Any
    risk_decisions: Any
    order_plans: Any
    validation_report: Any


class LayeredStrategyPipeline:
    """Compose explicit adapters after independent validation."""

    def __init__(self, layers: dict[str, object]) -> None:
        """Store adapters by contract name."""
        self.layers = dict(layers)

    def run(self, context: StrategyRunContext, market_input: Any) -> StrategyRunResult:
        """Fail closed until all layer adapters are implemented."""
        del context, market_input
        raise NotImplementedError(
            "The clean-room framework has no production adapters yet."
        )
