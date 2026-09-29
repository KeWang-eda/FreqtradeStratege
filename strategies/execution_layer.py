"""Exchange-ready order planning contract."""

from __future__ import annotations

from typing import Protocol

from contracts import OrderPlan, require_timezone_aware


class ExecutionLayer(Protocol):
    """Convert approved targets into explicit order plans."""

    def create_order_plan(self, risk_decision: object) -> OrderPlan:
        """Return an order plan with fees and slippage recorded."""
        ...


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
