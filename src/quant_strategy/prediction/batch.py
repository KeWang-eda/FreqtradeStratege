"""Prediction metadata includes units, signal times and model provenance."""

from dataclasses import asdict, dataclass

import pandas as pd

from quant_strategy.errors import DataContractError


@dataclass(frozen=True)
class PredictionRecord:
    """Prediction for a candle-open timestamp, usable after that candle closes."""

    pair: str
    candle_timestamp: pd.Timestamp
    prediction: float
    prediction_kind: str
    model_name: str
    model_version: str
    feature_version: str
    label_mode: str
    prediction_horizon: int
    is_ready: bool
    training_data_end: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        expected = {"raw": "raw_return", "volnorm": "volnorm_return"}
        if self.label_mode not in expected or self.prediction_kind != expected[self.label_mode]:
            raise DataContractError("Prediction kind and label units disagree")
        if pd.Timestamp(self.candle_timestamp).tzinfo is None:
            raise DataContractError("Prediction timestamp must be timezone-aware")
        if self.prediction_horizon < 1:
            raise DataContractError("Prediction horizon must be positive")


@dataclass(frozen=True)
class PredictionBatch:
    """Serializable prediction collection; alignment is checked before ranking."""

    records: tuple[PredictionRecord, ...]
    experiment_id: str
    backend: str

    def to_frame(self) -> pd.DataFrame:
        """Convert all metadata to tabular form suitable for Parquet."""
        return pd.DataFrame([asdict(record) for record in self.records])

    def at_time(self, timestamp: pd.Timestamp) -> "PredictionBatch":
        """Select records for exactly one signal time, never the latest per pair."""
        return PredictionBatch(
            tuple(r for r in self.records if r.candle_timestamp == timestamp),
            self.experiment_id,
            self.backend,
        )
