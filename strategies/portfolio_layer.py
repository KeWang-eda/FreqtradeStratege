"""Portfolio allocation and fixed-leverage risk-budget layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, Sequence

from contracts import CandidateScore, PositionTarget
from logging_config import get_layer_logger, log_failures, log_layer_event


LOGGER = get_layer_logger("portfolio")


@dataclass(frozen=True, slots=True)
class PortfolioConfiguration:
    """Fixed control-group portfolio settings."""

    leverage: float = 2.0
    risk_budget: float = 0.02
    stop_distance: float = 0.15
    max_open_trades: int = 3
    max_side_exposure: float = 0.50
    liquidation_buffer: float = 0.05


class PortfolioLayer(Protocol):
    """Convert selected candidates into risk-bounded targets."""

    def allocate_positions(
        self, candidates: Sequence[CandidateScore], account_equity: float
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


@log_failures("portfolio")
def build_position_targets(
    candidates: Sequence[CandidateScore],
    account_equity: float,
    configuration: PortfolioConfiguration = PortfolioConfiguration(),
) -> tuple[PositionTarget, ...]:
    """Build a fixed-leverage control group from selected candidates.

    Risk budget is split equally across the selected slots. Dynamic leverage,
    covariance optimization, and exchange precision belong to later layers.
    """
    if account_equity <= 0:
        raise ValueError("account_equity must be positive")
    if configuration.max_open_trades < 1:
        raise ValueError("max_open_trades must be positive")
    if configuration.leverage < 1:
        raise ValueError("leverage must be at least 1")
    if not 0 < configuration.risk_budget:
        raise ValueError("risk_budget must be positive")
    if not 0 < configuration.max_side_exposure <= 1:
        raise ValueError("max_side_exposure must be in (0, 1]")
    if configuration.liquidation_buffer < 0:
        raise ValueError("liquidation_buffer must be non-negative")

    ordered_candidates = sorted(
        candidates, key=lambda candidate: candidate.net_edge, reverse=True
    )[: configuration.max_open_trades]
    if not ordered_candidates:
        return ()

    per_position_risk = configuration.risk_budget / len(ordered_candidates)
    stake_amount = calculate_risk_bounded_stake(
        account_equity,
        per_position_risk,
        configuration.leverage,
        configuration.stop_distance,
    )
    target_weight = stake_amount / account_equity
    log_layer_event(
        LOGGER,
        logging.DEBUG,
        "portfolio_targets_built",
        candidate_count=len(candidates),
        selected_count=len(ordered_candidates),
        long_count=sum(candidate.side == "long" for candidate in ordered_candidates),
        short_count=sum(candidate.side == "short" for candidate in ordered_candidates),
        leverage=configuration.leverage,
        total_stake=stake_amount * len(ordered_candidates),
    )
    return tuple(
        PositionTarget(
            timestamp=candidate.timestamp,
            pair=candidate.pair,
            side=candidate.side,
            leverage=configuration.leverage,
            stake_amount=stake_amount,
            target_weight=target_weight,
            stop_distance=configuration.stop_distance,
        )
        for candidate in ordered_candidates
    )
