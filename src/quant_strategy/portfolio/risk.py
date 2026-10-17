"""Extension contract only; no additional risk rule is enabled."""

from typing import Protocol

from .position import PositionDecision


class RiskPolicy(Protocol):
    """Future policies must be evaluated separately from compatibility migration."""

    def evaluate(self, decision: PositionDecision) -> PositionDecision:
        """Return a reviewed position decision."""
        ...
