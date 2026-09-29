"""Model training and inference contract."""

from __future__ import annotations

from typing import Any, Protocol

from contracts import RiskPrediction, require_timezone_aware


class ModelLayer(Protocol):
    """Return risk predictions without selecting or sizing positions."""

    def predict_risk(
        self, feature_frame: Any, timestamp: Any, pair: str
    ) -> RiskPrediction:
        """Return one versioned risk prediction."""
        ...


def validate_risk_prediction(prediction: RiskPrediction) -> None:
    """Validate model output before selection or sizing."""
    require_timezone_aware(prediction.timestamp, "RiskPrediction.timestamp")
    if not prediction.pair:
        raise ValueError("RiskPrediction.pair must not be empty")
    if prediction.predicted_adverse_risk < 0:
        raise ValueError("predicted_adverse_risk must be non-negative")
    if prediction.stop_event_probability is not None and not 0 <= prediction.stop_event_probability <= 1:
        raise ValueError("stop_event_probability must be between 0 and 1")
    if not prediction.model_identifier or not prediction.model_version:
        raise ValueError("model identity must be recorded")
