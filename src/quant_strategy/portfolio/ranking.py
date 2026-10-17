"""Compatibility ranking: largest absolute model output, stable input ties."""

import math
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class PoolCandidate:
    """Legacy raw_prediction means unmodified model output (possibly volnorm)."""

    pair: str
    raw_prediction: float

    @property
    def direction(self) -> str:
        """Preserve legacy zero -> short ranking semantics; zero has no entry."""
        return "long" if self.raw_prediction > 0 else "short"


def build_candidate(
    pair: str, raw_prediction: object, prediction_ready: bool
) -> PoolCandidate | None:
    """Discard unavailable and nonfinite predictions without magnitude filters."""
    if not prediction_ready or raw_prediction is None:
        return None
    raw = float(raw_prediction)
    return PoolCandidate(pair, raw) if math.isfinite(raw) else None


class RankingPolicy(Protocol):
    """A ranking changes neither the candidates nor their prediction units."""

    def rank(self, candidates: Sequence[PoolCandidate]) -> list[PoolCandidate]:
        """Return candidates ordered from strongest to weakest."""
        ...


class AbsolutePredictionRanking:
    """Descending absolute prediction; ties preserve whitelist order."""

    def rank(self, candidates: Sequence[PoolCandidate]) -> list[PoolCandidate]:
        """Apply the existing ranking formula without introducing new thresholds."""
        return sorted(candidates, key=lambda c: abs(c.raw_prediction), reverse=True)
