"""Portfolio allocation and leverage contract."""

from __future__ import annotations

from typing import Protocol, Sequence

from contracts import PositionTarget


class PortfolioLayer(Protocol):
    """Convert selected candidates into risk-bounded targets."""

    def allocate_positions(
        self, candidates: Sequence[object], account_equity: float
    ) -> tuple[PositionTarget, ...]:
        """Return target weights, leverage, and collateral."""
        ...


def calculate_risk_bounded_stake(
    account_equity: float,
    risk_budget: float,
    leverage: float,
    stop_distance: float,
) -> float:
    """Size collateral for a fixed account-risk budget."""
    if account_equity < 0:
        raise ValueError("account_equity must be non-negative")
    if risk_budget < 0:
        raise ValueError("risk_budget must be non-negative")
    if leverage < 1:
        raise ValueError("leverage must be at least 1")
    if stop_distance <= 0:
        raise ValueError("stop_distance must be positive")
    return account_equity * risk_budget / (leverage * stop_distance)
