"""Same-timestamp cross-sectional selection layer."""

from __future__ import annotations

from typing import Protocol, Sequence

import pandas as pd
from pandas import DataFrame

from contracts import CandidateScore


class SelectionLayer(Protocol):
    """Rank candidates without changing leverage or stake."""

    def rank_candidates(
        self, candidate_scores: Sequence[CandidateScore]
    ) -> tuple[CandidateScore, ...]:
        """Return candidates ordered by net edge."""
        ...


def rank_cross_sectional_candidates(
    candidate_frame: DataFrame,
    top_k_per_side: int = 3,
    minimum_net_edge: float = 0.0,
    risk_penalty: float = 1.0,
) -> DataFrame:
    """Rank long and short candidates independently at each timestamp.

    Required columns are ``timestamp``, ``pair``, ``side``,
    ``expected_edge``, ``predicted_adverse_risk``, and ``execution_cost``.
    ``expected_edge`` must already be direction-aware: a larger value means a
    better long or short candidate.
    """
    required_columns = {
        "timestamp",
        "pair",
        "side",
        "expected_edge",
        "predicted_adverse_risk",
        "execution_cost",
    }
    missing_columns = required_columns.difference(candidate_frame.columns)
    if missing_columns:
        raise ValueError(f"missing selection columns: {sorted(missing_columns)}")
    if top_k_per_side < 1:
        raise ValueError("top_k_per_side must be positive")
    if risk_penalty < 0:
        raise ValueError("risk_penalty must be non-negative")

    result = candidate_frame.copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    if result[["timestamp", "pair", "side"]].duplicated().any():
        raise ValueError("duplicate pair-side candidates at one timestamp")
    if not result["side"].isin(["long", "short"]).all():
        raise ValueError("side must be long or short")
    numeric_columns = [
        "expected_edge",
        "predicted_adverse_risk",
        "execution_cost",
    ]
    if result[numeric_columns].isna().any().any():
        raise ValueError("selection numeric inputs must not contain NaN")

    result["net_edge"] = (
        result["expected_edge"]
        - risk_penalty * result["predicted_adverse_risk"]
        - result["execution_cost"]
    )
    result["rank"] = result.groupby(["timestamp", "side"])["net_edge"].rank(
        method="first", ascending=False
    ).astype("int64")
    result["selected"] = (result["rank"] <= top_k_per_side) & (
        result["net_edge"] >= minimum_net_edge
    )
    return result.sort_values(["timestamp", "side", "rank", "pair"]).reset_index(
        drop=True
    )


def validate_candidate_scores(
    candidate_scores: Sequence[CandidateScore],
) -> None:
    """Ensure all candidates share one timestamp and valid directions."""
    timestamps = {candidate.timestamp for candidate in candidate_scores}
    if len(timestamps) > 1:
        raise ValueError("candidate scores must share one timestamp")
    for candidate in candidate_scores:
        if candidate.side not in {"long", "short"}:
            raise ValueError("candidate side must be long or short")
        if candidate.rank < 0:
            raise ValueError("candidate rank must be non-negative")
