"""Shared value objects for the clean-room layered strategy framework."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping


@dataclass(frozen=True, slots=True)
class TradableAsset:
    """One asset eligible at a decision timestamp."""

    pair: str
    age_bars: int
    average_quote_volume: float
    minimum_stake: float | None
    funding_rate: float | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class DataPoolSnapshot:
    """Point-in-time tradable universe."""

    timestamp: datetime
    assets: tuple[TradableAsset, ...]

    @property
    def pairs(self) -> tuple[str, ...]:
        """Return ordered pair names."""
        return tuple(asset.pair for asset in self.assets)


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    """Causal features for one pair and timestamp."""

    timestamp: datetime
    pair: str
    values: Mapping[str, float]
    feature_version: str


@dataclass(frozen=True, slots=True)
class TrainingLabel:
    """Training target and the time when it becomes knowable."""

    timestamp: datetime
    pair: str
    value: float
    label_end: datetime
    label_version: str


@dataclass(frozen=True, slots=True)
class RiskPrediction:
    """Model output for one pair and timestamp."""

    timestamp: datetime
    pair: str
    predicted_adverse_risk: float
    stop_event_probability: float | None
    distribution_distance: float | None
    model_identifier: str
    model_version: str


@dataclass(frozen=True, slots=True)
class CandidateScore:
    """Comparable score for one pair and direction."""

    timestamp: datetime
    pair: str
    side: str
    expected_edge: float
    predicted_adverse_risk: float
    net_edge: float
    rank: int


@dataclass(frozen=True, slots=True)
class PositionTarget:
    """Desired position before exchange checks."""

    timestamp: datetime
    pair: str
    side: str
    leverage: float
    stake_amount: float
    target_weight: float
    stop_distance: float


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Risk approval, resize, or rejection."""

    timestamp: datetime
    pair: str
    allowed: bool
    approved_leverage: float
    approved_stake: float
    reason: str
    liquidation_buffer: float


@dataclass(frozen=True, slots=True)
class OrderPlan:
    """Exchange-ready order intent after precision and cost checks."""

    timestamp: datetime
    pair: str
    side: str
    order_type: str
    stake_amount: float
    leverage: float
    expected_fee: float
    expected_slippage: float
    client_order_tag: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Machine-readable promotion decision summary."""

    experiment_id: str
    parent_commit: str
    candidate_commit: str
    wallet_sharpe: float | None
    wallet_calmar: float | None
    max_relative_drawdown: float | None
    deflated_sharpe_probability: float | None
    probability_of_backtest_overfitting: float | None
    decision: str
    reason: str


def require_timezone_aware(timestamp: datetime, field_name: str) -> None:
    """Reject naive timestamps at layer boundaries."""
    if timestamp.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
