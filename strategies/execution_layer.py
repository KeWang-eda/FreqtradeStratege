"""Execution cost and order-plan layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Protocol

from contracts import OrderPlan, RiskDecision, require_timezone_aware


@dataclass(frozen=True, slots=True)
class ExecutionConfiguration:
    """Explicit execution assumptions for backtest and dry-run."""

    order_type: str = "limit"
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0002
    funding_rate: float = 0.0
    quantity_step: str = "0.001"
    minimum_stake: float = 0.0


class ExecutionLayer(Protocol):
    """Convert approved targets into explicit order plans."""

    def create_order_plan(self, risk_decision: RiskDecision) -> OrderPlan:
        """Return an order plan with costs and identity."""
        ...


def floor_to_step(value: float, step: str) -> float:
    """Floor a positive quantity to exchange precision."""
    if value < 0:
        raise ValueError("value must be non-negative")
    step_decimal = Decimal(step)
    if step_decimal <= 0:
        raise ValueError("step must be positive")
    return float(
        (Decimal(str(value)) / step_decimal).to_integral_value(rounding=ROUND_DOWN)
        * step_decimal
    )


def create_order_plan(
    risk_decision: RiskDecision,
    current_price: float,
    configuration: ExecutionConfiguration = ExecutionConfiguration(),
) -> OrderPlan | None:
    """Create a precision-aware order plan or reject an infeasible order."""
    require_timezone_aware(risk_decision.timestamp, "RiskDecision.timestamp")
    if current_price <= 0:
        raise ValueError("current_price must be positive")
    if configuration.order_type not in {"market", "limit"}:
        raise ValueError("order_type must be market or limit")
    if configuration.fee_rate < 0 or configuration.slippage_rate < 0:
        raise ValueError("execution costs must be non-negative")
    if not risk_decision.allowed:
        return None
    if risk_decision.approved_stake < configuration.minimum_stake:
        return None

    raw_quantity = (
        risk_decision.approved_stake * risk_decision.approved_leverage / current_price
    )
    quantity = floor_to_step(raw_quantity, configuration.quantity_step)
    if quantity <= 0:
        return None
    effective_stake = quantity * current_price / risk_decision.approved_leverage
    if effective_stake < configuration.minimum_stake:
        return None

    return OrderPlan(
        timestamp=risk_decision.timestamp,
        pair=risk_decision.pair,
        side=risk_decision.side,
        order_type=configuration.order_type,
        stake_amount=effective_stake,
        leverage=risk_decision.approved_leverage,
        expected_fee=effective_stake * risk_decision.approved_leverage * configuration.fee_rate,
        expected_slippage=effective_stake * risk_decision.approved_leverage * configuration.slippage_rate,
        client_order_tag=f"layered-vtech-{risk_decision.timestamp.strftime('%Y%m%d%H%M')}",
    )


def validate_order_plan(order_plan: OrderPlan) -> None:
    """Validate order identity and non-negative costs."""
    require_timezone_aware(order_plan.timestamp, "OrderPlan.timestamp")
    if order_plan.side not in {"long", "short"}:
        raise ValueError("OrderPlan.side must be long or short")
    if order_plan.order_type not in {"market", "limit"}:
        raise ValueError("OrderPlan.order_type must be market or limit")
    if order_plan.stake_amount < 0 or order_plan.leverage < 1:
        raise ValueError("order stake or leverage is invalid")
    if order_plan.expected_fee < 0 or order_plan.expected_slippage < 0:
        raise ValueError("execution costs must be non-negative")
    if not order_plan.client_order_tag:
        raise ValueError("client_order_tag must not be empty")
