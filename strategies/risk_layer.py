"""Trade-level risk and liquidation-buffer layer."""

from __future__ import annotations

import logging
from typing import Protocol

from contracts import PositionTarget, RiskDecision, require_timezone_aware
from logging_config import get_layer_logger, log_failures, log_layer_event


LOGGER = get_layer_logger("risk")


class RiskLayer(Protocol):
    """Approve, resize, or reject a proposed target."""

    def apply_risk_limits(self, position_target: PositionTarget) -> RiskDecision:
        """Return a fail-closed risk decision."""
        ...


@log_failures("risk")
def apply_position_risk_limits(
    position_target: PositionTarget,
    minimum_stake: float | None = None,
    maximum_stake: float | None = None,
    exchange_max_leverage: float = 20.0,
    liquidation_buffer: float = 0.05,
) -> RiskDecision:
    """Apply leverage, stake, and liquidation-buffer constraints."""
    require_timezone_aware(position_target.timestamp, "PositionTarget.timestamp")
    if exchange_max_leverage < 1:
        raise ValueError("exchange_max_leverage must be at least 1")
    if liquidation_buffer < 0:
        raise ValueError("liquidation_buffer must be non-negative")
    if minimum_stake is not None and minimum_stake < 0:
        raise ValueError("minimum_stake must be non-negative")
    if maximum_stake is not None and maximum_stake <= 0:
        raise ValueError("maximum_stake must be positive")

    if position_target.leverage > exchange_max_leverage:
        log_layer_event(
            LOGGER,
            logging.WARNING,
            "risk_rejected",
            pair=position_target.pair,
            side=position_target.side,
            reason="leverage_exceeds_exchange_limit",
            requested_leverage=position_target.leverage,
            exchange_max_leverage=exchange_max_leverage,
        )
        return RiskDecision(
            timestamp=position_target.timestamp,
            pair=position_target.pair,
            side=position_target.side,
            allowed=False,
            approved_leverage=exchange_max_leverage,
            approved_stake=0.0,
            reason="requested leverage exceeds exchange limit",
            liquidation_buffer=liquidation_buffer,
        )
    if minimum_stake is not None and position_target.stake_amount < minimum_stake:
        log_layer_event(
            LOGGER,
            logging.WARNING,
            "risk_rejected",
            pair=position_target.pair,
            side=position_target.side,
            reason="stake_below_minimum",
            stake_amount=position_target.stake_amount,
            minimum_stake=minimum_stake,
        )
        return RiskDecision(
            timestamp=position_target.timestamp,
            pair=position_target.pair,
            side=position_target.side,
            allowed=False,
            approved_leverage=position_target.leverage,
            approved_stake=0.0,
            reason="risk-bounded stake is below exchange minimum",
            liquidation_buffer=liquidation_buffer,
        )

    approved_stake = position_target.stake_amount
    if maximum_stake is not None:
        approved_stake = min(approved_stake, maximum_stake)
    if approved_stake <= 0:
        log_layer_event(
            LOGGER,
            logging.WARNING,
            "risk_rejected",
            pair=position_target.pair,
            side=position_target.side,
            reason="approved_stake_not_positive",
            approved_stake=approved_stake,
        )
        return RiskDecision(
            timestamp=position_target.timestamp,
            pair=position_target.pair,
            side=position_target.side,
            allowed=False,
            approved_leverage=position_target.leverage,
            approved_stake=0.0,
            reason="approved stake is not positive",
            liquidation_buffer=liquidation_buffer,
        )
    return RiskDecision(
        timestamp=position_target.timestamp,
        pair=position_target.pair,
        side=position_target.side,
        allowed=True,
        approved_leverage=position_target.leverage,
        approved_stake=approved_stake,
        reason="risk checks passed",
        liquidation_buffer=liquidation_buffer,
    )


def validate_risk_decision(decision: RiskDecision) -> None:
    """Validate risk decision fields."""
    require_timezone_aware(decision.timestamp, "RiskDecision.timestamp")
    if decision.side not in {"long", "short"}:
        raise ValueError("risk decision side must be long or short")
    if decision.approved_leverage < 1:
        raise ValueError("approved_leverage must be at least 1")
    if decision.approved_stake < 0:
        raise ValueError("approved_stake must be non-negative")
    if decision.liquidation_buffer < 0:
        raise ValueError("liquidation_buffer must be non-negative")
    if not decision.reason:
        raise ValueError("risk decision must include a reason")
