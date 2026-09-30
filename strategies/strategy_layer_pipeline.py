"""Explicit composition boundary for one layered strategy decision."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from pandas import DataFrame

from contracts import CandidateScore
from execution_layer import (
    ExecutionConfiguration,
    create_order_plan,
    validate_order_plan,
)
from logging_config import get_layer_logger, log_failures, log_layer_event
from portfolio_layer import PortfolioConfiguration, build_position_targets
from risk_layer import apply_position_risk_limits
from selection_layer import rank_cross_sectional_candidates


LOGGER = get_layer_logger("pipeline")
FRAMEWORK_VERSION = "0.1.0-composition"


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
    """Artifacts produced by one explicit composition decision."""

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
    """Compose selection, portfolio, risk, and execution for one timestamp."""

    def __init__(self, layers: dict[str, object] | None = None) -> None:
        """Keep optional adapters for experiment identity and future injection."""
        self.layers = dict(layers or {})

    @log_failures("pipeline")
    def run(
        self,
        context: StrategyRunContext,
        market_input: Mapping[str, Any],
    ) -> StrategyRunResult:
        """Build order plans from a same-timestamp candidate frame.

        ``market_input`` must contain ``candidate_frame``, ``account_equity``,
        and ``current_prices``. Model training is deliberately outside this
        method: its predictions must already be present in the candidate frame.
        """
        candidate_frame = market_input.get("candidate_frame")
        if candidate_frame is None or not isinstance(candidate_frame, DataFrame):
            raise ValueError("market_input.candidate_frame must be a DataFrame")
        if candidate_frame.empty:
            raise ValueError("market_input.candidate_frame must not be empty")
        account_equity = float(market_input.get("account_equity", 0.0))
        current_prices = market_input.get("current_prices")
        if account_equity <= 0:
            raise ValueError("market_input.account_equity must be positive")
        if not isinstance(current_prices, Mapping):
            raise ValueError("market_input.current_prices must be a mapping")

        ranked_candidates = rank_cross_sectional_candidates(
            candidate_frame,
            top_k_per_side=int(market_input.get("top_k_per_side", 3)),
            minimum_net_edge=float(market_input.get("minimum_net_edge", 0.0)),
            risk_penalty=float(market_input.get("risk_penalty", 1.0)),
        )
        selected = ranked_candidates[ranked_candidates["selected"]]
        candidate_scores = tuple(
            CandidateScore(
                timestamp=row.timestamp.to_pydatetime(),
                pair=row.pair,
                side=row.side,
                expected_edge=float(row.expected_edge),
                predicted_adverse_risk=float(row.predicted_adverse_risk),
                net_edge=float(row.net_edge),
                rank=int(row.rank),
            )
            for row in selected.itertuples(index=False)
        )

        portfolio_configuration = market_input.get(
            "portfolio_configuration", PortfolioConfiguration()
        )
        if not isinstance(portfolio_configuration, PortfolioConfiguration):
            raise TypeError("portfolio_configuration has an invalid type")
        targets = build_position_targets(
            candidate_scores, account_equity, portfolio_configuration
        )

        minimum_stakes = market_input.get("minimum_stakes", {})
        maximum_stake = market_input.get("maximum_stake")
        exchange_max_leverage = float(market_input.get("exchange_max_leverage", 20.0))
        risk_decisions = tuple(
            apply_position_risk_limits(
                target,
                minimum_stake=minimum_stakes.get(target.pair),
                maximum_stake=maximum_stake,
                exchange_max_leverage=exchange_max_leverage,
                liquidation_buffer=portfolio_configuration.liquidation_buffer,
                current_price=float(current_prices[target.pair]),
                liquidation_price=market_input.get("liquidation_prices", {}).get(target.pair),
            )
            for target in targets
        )

        execution_configuration = market_input.get(
            "execution_configuration", ExecutionConfiguration()
        )
        if not isinstance(execution_configuration, ExecutionConfiguration):
            raise TypeError("execution_configuration has an invalid type")
        order_plans = []
        for decision in risk_decisions:
            if not decision.allowed:
                continue
            if decision.pair not in current_prices:
                raise ValueError(f"missing current price for {decision.pair}")
            order_plan = create_order_plan(
                decision,
                float(current_prices[decision.pair]),
                execution_configuration,
            )
            if order_plan is not None:
                validate_order_plan(order_plan)
                order_plans.append(order_plan)

        log_layer_event(
            LOGGER,
            logging.INFO,
            "composition_decision_complete",
            experiment_id=context.experiment_id,
            candidate_count=len(ranked_candidates),
            selected_count=len(selected),
            target_count=len(targets),
            allowed_risk_count=sum(decision.allowed for decision in risk_decisions),
            order_plan_count=len(order_plans),
            model_identifier=context.model_identifier,
        )
        return StrategyRunResult(
            context=context,
            pool_snapshot=market_input.get("pool_snapshot"),
            features=market_input.get("features"),
            predictions=market_input.get("predictions"),
            candidates=ranked_candidates,
            position_targets=targets,
            risk_decisions=risk_decisions,
            order_plans=tuple(order_plans),
            validation_report=None,
        )
