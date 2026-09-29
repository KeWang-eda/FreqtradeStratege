"""Wallet metrics and promotion gates for the layered framework."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Protocol

import numpy as np
import pandas as pd
from pandas import DataFrame

from contracts import ValidationReport


@dataclass(frozen=True, slots=True)
class WalletMetrics:
    """Daily wallet metrics used by promotion decisions."""

    total_return: float
    annualized_return: float
    wallet_sharpe: float
    wallet_calmar: float
    max_relative_drawdown: float
    observation_count: int

    @property
    def product(self) -> float:
        """Return wallet Sharpe multiplied by wallet Calmar."""
        return self.wallet_sharpe * self.wallet_calmar


class ValidationLayer(Protocol):
    """Produce independent and combined experiment evidence."""

    def validate_experiment(self, experiment_id: str) -> ValidationReport:
        """Return a reproducible promotion decision."""
        ...


def calculate_wallet_metrics(
    wallet_frame: DataFrame,
    equity_column: str = "total_quote",
) -> WalletMetrics:
    """Calculate wallet metrics from a timestamped equity curve."""
    if equity_column not in wallet_frame.columns:
        raise ValueError(f"missing wallet column: {equity_column}")
    if "date" not in wallet_frame.columns:
        raise ValueError("wallet frame requires a date column")
    frame = wallet_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    frame = frame.sort_values("date").drop_duplicates("date", keep="last")
    equity = pd.to_numeric(frame[equity_column], errors="coerce").dropna()
    if len(equity) < 3 or (equity <= 0).any():
        raise ValueError("wallet equity must contain at least 3 positive observations")

    daily_returns = equity.pct_change().dropna()
    volatility = float(daily_returns.std(ddof=1))
    wallet_sharpe = (
        float(daily_returns.mean() / volatility * sqrt(365))
        if volatility > 0
        else float("nan")
    )
    running_high = equity.cummax()
    drawdowns = equity / running_high - 1.0
    max_relative_drawdown = float(-drawdowns.min())
    elapsed_days = max(
        (frame["date"].iloc[-1] - frame["date"].iloc[0]).total_seconds() / 86400,
        1.0,
    )
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    annualized_return = float((1.0 + total_return) ** (365.0 / elapsed_days) - 1.0)
    wallet_calmar = (
        annualized_return / max_relative_drawdown
        if max_relative_drawdown > 0
        else float("nan")
    )
    metrics = WalletMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        wallet_sharpe=wallet_sharpe,
        wallet_calmar=wallet_calmar,
        max_relative_drawdown=max_relative_drawdown,
        observation_count=len(daily_returns),
    )
    if not np.isfinite(
        [
            metrics.total_return,
            metrics.annualized_return,
            metrics.wallet_sharpe,
            metrics.wallet_calmar,
            metrics.max_relative_drawdown,
        ]
    ).all():
        raise ValueError("wallet metrics contain non-finite values")
    return metrics


def evaluate_promotion_gate(
    experiment_id: str,
    parent_commit: str,
    candidate_commit: str,
    parent_metrics: WalletMetrics,
    candidate_metrics: WalletMetrics,
    deflated_sharpe_probability: float | None,
    probability_of_backtest_overfitting: float | None,
    drawdown_limit: float = 0.30,
) -> ValidationReport:
    """Apply the repository promotion gates and fail closed on missing stats."""
    if deflated_sharpe_probability is None or probability_of_backtest_overfitting is None:
        decision = "blocked"
        reason = "DSR and PBO are required before promotion"
    elif candidate_metrics.max_relative_drawdown >= drawdown_limit:
        decision = "rejected"
        reason = "candidate maximum relative drawdown exceeds the gate"
    elif candidate_metrics.product <= parent_metrics.product:
        decision = "rejected"
        reason = "candidate wallet Sharpe × Calmar is not above parent"
    elif deflated_sharpe_probability < 0.95:
        decision = "rejected"
        reason = "deflated Sharpe probability is below 0.95"
    elif probability_of_backtest_overfitting > 0.05:
        decision = "rejected"
        reason = "probability of backtest overfitting exceeds 0.05"
    else:
        decision = "promoted"
        reason = "all configured promotion gates passed"

    return ValidationReport(
        experiment_id=experiment_id,
        parent_commit=parent_commit,
        candidate_commit=candidate_commit,
        wallet_sharpe=candidate_metrics.wallet_sharpe,
        wallet_calmar=candidate_metrics.wallet_calmar,
        max_relative_drawdown=candidate_metrics.max_relative_drawdown,
        deflated_sharpe_probability=deflated_sharpe_probability,
        probability_of_backtest_overfitting=probability_of_backtest_overfitting,
        decision=decision,
        reason=reason,
    )


def validate_report(report: ValidationReport) -> None:
    """Validate a report before it is persisted."""
    if not report.experiment_id:
        raise ValueError("experiment_id must not be empty")
    if not report.parent_commit or not report.candidate_commit:
        raise ValueError("parent and candidate commits are required")
    if report.decision not in {"proposed", "running", "promoted", "rejected", "blocked"}:
        raise ValueError("unknown validation decision")
    if not report.reason:
        raise ValueError("validation report must include a reason")
