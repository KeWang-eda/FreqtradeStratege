"""Future-label construction contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from contracts import TrainingLabel, require_timezone_aware


class LabelLayer(Protocol):
    """Build future training targets without leaking them into decisions."""

    def build_training_label(
        self, historical_market_data: Any, pair: str, timestamp: datetime
    ) -> TrainingLabel:
        """Return a target and its information horizon."""
        ...


def validate_training_label(training_label: TrainingLabel) -> None:
    """Reject labels with an invalid information horizon."""
    require_timezone_aware(training_label.timestamp, "TrainingLabel.timestamp")
    require_timezone_aware(training_label.label_end, "TrainingLabel.label_end")
    if training_label.label_end <= training_label.timestamp:
        raise ValueError("TrainingLabel.label_end must be after timestamp")
    if not training_label.label_version:
        raise ValueError("TrainingLabel.label_version must not be empty")
