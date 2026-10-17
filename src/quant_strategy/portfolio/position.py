"""Single-position target and rotate/exit rules independent of execution."""

from dataclasses import dataclass
from typing import Sequence

from .ranking import AbsolutePredictionRanking, PoolCandidate, RankingPolicy


@dataclass(frozen=True)
class TargetPosition:
    """A missing pair denotes a complete snapshot with no eligible prediction."""

    pair: str | None
    side: str | None


@dataclass(frozen=True)
class PositionDecision:
    """Typed domain decision, translated to framework reasons by adapters."""

    action: str
    reason: str | None
    target: TargetPosition


def resolve_target_position(
    candidates: Sequence[PoolCandidate], ranking: RankingPolicy | None = None
) -> TargetPosition:
    """Resolve the best candidate; empty candidates produce an empty target."""
    ranked = (ranking or AbsolutePredictionRanking()).rank(candidates)
    return (
        TargetPosition(ranked[0].pair, ranked[0].direction)
        if ranked
        else TargetPosition(None, None)
    )


def decide_position_action(
    held_pair: str | None, held_side: str | None, target: TargetPosition
) -> PositionDecision:
    """Hold a matching target; rotate mismatches; exit an empty target."""
    if target.pair is None:
        return PositionDecision("exit", "no_eligible_target", target)
    if target.pair == held_pair and target.side == held_side:
        return PositionDecision("hold", None, target)
    reason = "rotate_to_stronger_pair" if target.pair != held_pair else "rotate_to_opposite_side"
    return PositionDecision("rotate", reason, target)
