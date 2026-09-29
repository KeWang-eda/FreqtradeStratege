"""Causal future-label construction for the layered strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from pandas import DataFrame, Series

from contracts import TrainingLabel, require_timezone_aware


@dataclass(frozen=True, slots=True)
class LabelConfiguration:
    """Fixed label semantics for one experiment."""

    horizon_bars: int = 8
    fee_rate: float = 0.0005
    leverage: float = 2.0
    risk_penalty: float = 1.0
    label_version: str = "adverse-risk-v1"


class LabelLayer(Protocol):
    """Build future training targets without leaking them into decisions."""

    def build_training_label(
        self, historical_market_data: DataFrame, pair: str, timestamp: object
    ) -> TrainingLabel:
        """Return a target and its information horizon."""
        ...


def build_adverse_risk_labels(
    dataframe: DataFrame,
    direction: Series,
    configuration: LabelConfiguration = LabelConfiguration(),
) -> DataFrame:
    """Build causal future adverse-risk labels for candidate directions.

    ``direction`` is expected to contain ``1`` for long, ``-1`` for short, and
    ``0`` for no candidate. The returned label is only for training; callers
    must not merge it into live feature inputs.
    """
    required_columns = {"date", "close", "low", "high"}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(f"missing label columns: {sorted(missing_columns)}")
    if len(direction) != len(dataframe):
        raise ValueError("direction and dataframe must have the same length")
    if configuration.horizon_bars < 1:
        raise ValueError("horizon_bars must be positive")
    if configuration.fee_rate < 0 or configuration.leverage < 1:
        raise ValueError("fee_rate or leverage is invalid")
    if configuration.risk_penalty < 0:
        raise ValueError("risk_penalty must be non-negative")

    result = DataFrame(index=dataframe.index)
    result["timestamp"] = pd.to_datetime(dataframe["date"], utc=True)
    result["label_end"] = result["timestamp"].shift(-configuration.horizon_bars)
    direction_values = pd.to_numeric(direction, errors="coerce").fillna(0.0)
    result["direction"] = direction_values

    future_low = dataframe["low"].shift(-configuration.horizon_bars).rolling(
        configuration.horizon_bars
    ).min()
    future_high = dataframe["high"].shift(-configuration.horizon_bars).rolling(
        configuration.horizon_bars
    ).max()
    future_mean = dataframe["close"].shift(-configuration.horizon_bars).rolling(
        configuration.horizon_bars
    ).mean()
    long_adverse = (1.0 - future_low / dataframe["close"]).clip(lower=0.0)
    short_adverse = (future_high / dataframe["close"] - 1.0).clip(lower=0.0)
    result["directional_return"] = direction_values * (
        future_mean / dataframe["close"] - 1.0
    )
    result["directional_return"] = result["directional_return"].where(
        direction_values != 0.0
    )
    result["adverse_move"] = np.where(
        direction_values > 0, long_adverse, short_adverse
    )
    result["adverse_move"] = result["adverse_move"].where(direction_values != 0.0)
    result["adverse_risk"] = configuration.leverage * (
        result["adverse_move"] * configuration.risk_penalty
        + 2.0 * configuration.fee_rate
    )
    result["utility"] = configuration.leverage * (
        result["directional_return"]
        - configuration.risk_penalty * result["adverse_move"]
        - 2.0 * configuration.fee_rate
    )
    result["stop_event"] = (result["adverse_risk"] >= 0.15).astype("float64")
    result.loc[result["adverse_move"].isna(), "stop_event"] = np.nan
    result["label_version"] = configuration.label_version
    return result


def validate_training_labels(label_frame: DataFrame) -> None:
    """Validate label horizon and candidate-only output."""
    required_columns = {
        "timestamp",
        "label_end",
        "direction",
        "directional_return",
        "adverse_move",
        "adverse_risk",
        "utility",
        "stop_event",
        "label_version",
    }
    missing_columns = required_columns.difference(label_frame.columns)
    if missing_columns:
        raise ValueError(f"missing label output columns: {sorted(missing_columns)}")
    timestamps = pd.to_datetime(label_frame["timestamp"], utc=True)
    label_end = pd.to_datetime(label_frame["label_end"], utc=True)
    if not (label_end.dropna() > timestamps.loc[label_end.dropna().index]).all():
        raise ValueError("label_end must be after timestamp")
    candidate_mask = label_frame["direction"] != 0.0
    if label_frame.loc[~candidate_mask, "adverse_risk"].notna().any():
        raise ValueError("non-candidate rows must not have adverse-risk labels")
    if (label_frame.loc[candidate_mask, "adverse_risk"] < 0).any():
        raise ValueError("adverse-risk labels must be non-negative")
    if label_frame["label_version"].isna().any():
        raise ValueError("label_version must be present")


def validate_training_label(training_label: TrainingLabel) -> None:
    """Reject a single label with an invalid information horizon."""
    require_timezone_aware(training_label.timestamp, "TrainingLabel.timestamp")
    require_timezone_aware(training_label.label_end, "TrainingLabel.label_end")
    if training_label.label_end <= training_label.timestamp:
        raise ValueError("TrainingLabel.label_end must be after timestamp")
    if not training_label.label_version:
        raise ValueError("TrainingLabel.label_version must not be empty")
