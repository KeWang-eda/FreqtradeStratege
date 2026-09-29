"""Causal feature-engineering contract."""

from __future__ import annotations

from typing import Any, Protocol

from contracts import FeatureFrame, require_timezone_aware


class FeatureLayer(Protocol):
    """Compute features without reading future bars."""

    def compute_causal_features(
        self, market_snapshot: Any, pair: str
    ) -> FeatureFrame:
        """Return one feature frame."""
        ...


def validate_feature_frame(feature_frame: FeatureFrame) -> None:
    """Validate feature identity before model consumption."""
    require_timezone_aware(feature_frame.timestamp, "FeatureFrame.timestamp")
    if not feature_frame.pair:
        raise ValueError("FeatureFrame.pair must not be empty")
    if not feature_frame.feature_version:
        raise ValueError("FeatureFrame.feature_version must not be empty")
    if not feature_frame.values:
        raise ValueError("FeatureFrame.values must not be empty")
