"""Same-timestamp cross-sectional selection contract."""

from __future__ import annotations

from typing import Protocol, Sequence

from contracts import CandidateScore


class SelectionLayer(Protocol):
    """Rank candidates without changing leverage or stake."""

    def rank_candidates(
        self, candidate_scores: Sequence[CandidateScore]
    ) -> tuple[CandidateScore, ...]:
        """Return candidates ordered by net edge."""
        ...


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
