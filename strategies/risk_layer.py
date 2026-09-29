"""Portfolio, margin, and liquidation-risk contract."""

from __future__ import annotations

from typing import Protocol

from contracts import RiskDecision, require_timezone_aware


class RiskLayer(Protocol):
    """Approve, resize, or reject a proposed target."""

    def apply_risk_limits(self, position_target: object) -> RiskDecision:
        """Return a fail-closed risk decision."""
        ...


def validate_risk_decision(decision: RiskDecision) -> None:
    """Validate risk decision fields."""
    require_timezone_aware(decision.timestamp, "RiskDecision.timestamp")
    if decision.approved_leverage < 1:
        raise ValueError("approved_leverage must be at least 1")
    if decision.approved_stake < 0:
        raise ValueError("approved_stake must be non-negative")
    if decision.liquidation_buffer < 0:
        raise ValueError("liquidation_buffer must be non-negative")
    if not decision.reason:
        raise ValueError("risk decision must include a reason")
