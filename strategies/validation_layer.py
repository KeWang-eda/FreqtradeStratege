"""Wallet metrics and promotion gates for the layered framework."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import sqrt
from typing import Protocol, Sequence

import numpy as np
import pandas as pd
from pandas import DataFrame, Series
from scipy.stats import norm

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
    periods_per_year: float = 365.0,
) -> WalletMetrics:
    """Calculate wallet metrics from a timestamped equity curve."""
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
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
        float(daily_returns.mean() / volatility * sqrt(periods_per_year))
        if volatility > 0
        else 0.0
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
        else 0.0
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


def calculate_deflated_sharpe_probability(
    returns: Series,
    trial_sharpes: Sequence[float],
    periods_per_year: float = 365.0,
) -> float:
    """Calculate DSR probability after correcting for trial selection.

    The implementation follows Bailey and López de Prado, *The Deflated
    Sharpe Ratio* (2014): the estimated Sharpe is tested against the expected
    maximum of the supplied independent trial Sharpes, then adjusted for
    sample length, skewness, and kurtosis. The returned value is a probability
    in ``[0, 1]``; trial Sharpes must use the same annualization convention as
    the selected return series.

    Reference:
      https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    trials = np.asarray(tuple(trial_sharpes), dtype=float)
    if len(values) < 3:
        raise ValueError("at least 3 return observations are required")
    if len(trials) < 2 or not np.isfinite(trials).all():
        raise ValueError("at least 2 finite trial Sharpes are required")
    volatility = float(values.std(ddof=1))
    if volatility <= 0:
        raise ValueError("return volatility must be positive")

    estimated_sharpe = float(values.mean() / volatility * sqrt(periods_per_year))
    trial_mean = float(trials.mean())
    trial_volatility = float(trials.std(ddof=1))
    euler_mascheroni = 0.5772156649
    trial_count = len(trials)
    maximum_normal_score = (
        (1.0 - euler_mascheroni) * norm.ppf(1.0 - 1.0 / trial_count)
        + euler_mascheroni
        * norm.ppf(1.0 - 1.0 / (trial_count * np.e))
    )
    expected_maximum = trial_mean + trial_volatility * maximum_normal_score
    return_distribution = pd.Series(values)
    skewness = float(return_distribution.skew())
    kurtosis = float(return_distribution.kurtosis() + 3.0)
    denominator = sqrt(
        max(
            1e-12,
            1.0
            - skewness * estimated_sharpe
            + (kurtosis - 1.0) * estimated_sharpe**2 / 4.0,
        )
    )
    probability = norm.cdf(
        (estimated_sharpe - expected_maximum)
        * sqrt(len(values) - 1.0)
        / denominator
    )
    return float(np.clip(probability, 0.0, 1.0))


def calculate_probability_of_backtest_overfitting(
    return_frame: DataFrame,
    number_blocks: int = 8,
) -> float:
    """Estimate PBO with combinatorially symmetric cross-validation.

    Each column is one pre-declared candidate strategy and each row is one
    equally spaced return period. The in-sample winner is ranked against all
    candidates in the complementary out-of-sample blocks. The returned value
    is the fraction of complementary splits where that winner ranks below the
    OOS median.

    Reference:
      https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
    """
    if number_blocks < 4 or number_blocks % 2:
        raise ValueError("number_blocks must be an even integer of at least 4")
    if return_frame.shape[1] < 2:
        raise ValueError("at least 2 candidate return columns are required")
    if len(return_frame) < number_blocks:
        raise ValueError("return frame is shorter than number_blocks")

    numeric_frame = return_frame.apply(pd.to_numeric, errors="coerce")
    if numeric_frame.isna().any().any():
        raise ValueError("candidate returns must contain no NaN values")
    usable_count = len(numeric_frame) - len(numeric_frame) % number_blocks
    if usable_count < number_blocks:
        raise ValueError("return frame has no complete CSCV blocks")
    numeric_frame = numeric_frame.iloc[:usable_count]
    blocks = np.array_split(np.arange(usable_count), number_blocks)
    half_block_count = number_blocks // 2
    split_count = 0
    overfit_count = 0

    for in_sample_blocks in combinations(range(number_blocks), half_block_count):
        if 0 not in in_sample_blocks:
            continue
        out_of_sample_blocks = tuple(
            block_index
            for block_index in range(number_blocks)
            if block_index not in in_sample_blocks
        )
        in_sample_index = np.concatenate([blocks[index] for index in in_sample_blocks])
        out_of_sample_index = np.concatenate(
            [blocks[index] for index in out_of_sample_blocks]
        )
        in_sample = numeric_frame.iloc[in_sample_index]
        out_of_sample = numeric_frame.iloc[out_of_sample_index]
        in_sample_sharpes = in_sample.mean() / in_sample.std(ddof=1)
        out_of_sample_sharpes = out_of_sample.mean() / out_of_sample.std(ddof=1)
        if not np.isfinite(in_sample_sharpes).all() or not np.isfinite(out_of_sample_sharpes).all():
            continue
        winner = in_sample_sharpes.idxmax()
        fractional_rank = float(
            (out_of_sample_sharpes <= out_of_sample_sharpes[winner]).mean()
        )
        overfit_count += fractional_rank < 0.5
        split_count += 1

    if split_count == 0:
        raise ValueError("CSCV produced no valid splits")
    return float(overfit_count / split_count)


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
    elif candidate_metrics.total_return <= 0:
        decision = "rejected"
        reason = "candidate wallet return is not positive"
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
