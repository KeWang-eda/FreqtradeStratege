"""Time-series XGBoost risk model for the layered strategy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np
import pandas as pd
from pandas import DataFrame, Series
from xgboost import XGBRegressor

from contracts import RiskPrediction, require_timezone_aware


@dataclass(frozen=True, slots=True)
class ModelTrainingConfig:
    """Time-series training configuration."""

    test_size: float = 0.2
    early_stopping_rounds: int = 50
    model_parameters: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ModelFitReport:
    """Auditable result of one model fit."""

    model_identifier: str
    pair: str
    feature_count: int
    train_samples: int
    validation_samples: int
    best_iteration: int | None
    best_score: float | None


class ModelLayer(Protocol):
    """Return risk predictions without selecting or sizing positions."""

    def predict_risk(
        self, feature_frame: DataFrame, timestamp: datetime, pair: str
    ) -> RiskPrediction:
        """Return one versioned risk prediction."""
        ...


class XGBoostRiskModel:
    """One-pair XGBoost adverse-risk model with chronological validation."""

    def __init__(
        self,
        model_identifier: str,
        model_version: str,
        training_config: ModelTrainingConfig | None = None,
    ) -> None:
        """Create an unfitted model."""
        if not model_identifier or not model_version:
            raise ValueError("model identity must not be empty")
        self.model_identifier = model_identifier
        self.model_version = model_version
        self.training_config = training_config or ModelTrainingConfig()
        if not 0 < self.training_config.test_size < 1:
            raise ValueError("test_size must be between 0 and 1")
        if self.training_config.early_stopping_rounds < 1:
            raise ValueError("early_stopping_rounds must be positive")
        self._model: XGBRegressor | None = None
        self._feature_columns: tuple[str, ...] = ()
        self.fit_report: ModelFitReport | None = None

    def fit(
        self,
        features: DataFrame,
        target: Series,
        feature_columns: Sequence[str],
        pair: str,
    ) -> ModelFitReport:
        """Fit with a chronological train/validation split.

        The final validation block is never shuffled and is the only eval set
        passed to XGBoost early stopping.
        """
        columns = tuple(feature_columns)
        if not columns:
            raise ValueError("feature_columns must not be empty")
        missing_columns = set(columns).difference(features.columns)
        if missing_columns:
            raise ValueError(f"missing model features: {sorted(missing_columns)}")
        if len(features) != len(target):
            raise ValueError("features and target must have equal lengths")
        if len(features) < 20:
            raise ValueError("at least 20 rows are required for model fitting")

        training_frame = features.loc[:, columns].copy()
        training_frame["__target__"] = pd.to_numeric(target, errors="coerce").to_numpy()
        training_frame = training_frame.replace([np.inf, -np.inf], np.nan).dropna()
        split_index = int(len(training_frame) * (1.0 - self.training_config.test_size))
        if split_index < 10 or len(training_frame) - split_index < 5:
            raise ValueError("time split leaves too few train or validation rows")

        train_frame = training_frame.iloc[:split_index]
        validation_frame = training_frame.iloc[split_index:]
        parameters = {
            "objective": "reg:pseudohubererror",
            "n_estimators": 600,
            "max_depth": 3,
            "learning_rate": 0.03,
            "subsample": 0.85,
            "colsample_bytree": 0.70,
            "min_child_weight": 16,
            "reg_alpha": 0.1,
            "reg_lambda": 2.0,
            "eval_metric": "mae",
            "tree_method": "hist",
            "n_jobs": 1,
            "random_state": 42,
        }
        parameters.update(self.training_config.model_parameters or {})
        model = XGBRegressor(
            **parameters,
            early_stopping_rounds=self.training_config.early_stopping_rounds,
        )
        model.fit(
            train_frame.loc[:, columns],
            train_frame["__target__"],
            eval_set=[
                (
                    validation_frame.loc[:, columns],
                    validation_frame["__target__"],
                )
            ],
            verbose=False,
        )
        self._model = model
        self._feature_columns = columns
        best_iteration = getattr(model, "best_iteration", None)
        best_score = getattr(model, "best_score", None)
        self.fit_report = ModelFitReport(
            model_identifier=self.model_identifier,
            pair=pair,
            feature_count=len(columns),
            train_samples=len(train_frame),
            validation_samples=len(validation_frame),
            best_iteration=best_iteration,
            best_score=best_score,
        )
        return self.fit_report

    def predict(self, features: DataFrame) -> Series:
        """Predict risk using the fitted best-iteration model."""
        if self._model is None:
            raise RuntimeError("model must be fitted before prediction")
        missing_columns = set(self._feature_columns).difference(features.columns)
        if missing_columns:
            raise ValueError(f"missing prediction features: {sorted(missing_columns)}")
        values = self._model.predict(features.loc[:, self._feature_columns])
        return Series(np.maximum(values, 0.0), index=features.index, dtype="float64")

    def predict_risk(
        self, feature_frame: DataFrame, timestamp: datetime, pair: str
    ) -> RiskPrediction:
        """Return one validated risk prediction for one timestamp."""
        require_timezone_aware(timestamp, "RiskPrediction.timestamp")
        if len(feature_frame) != 1:
            raise ValueError("feature_frame must contain exactly one row")
        prediction = float(self.predict(feature_frame).iloc[0])
        return RiskPrediction(
            timestamp=timestamp,
            pair=pair,
            predicted_adverse_risk=prediction,
            stop_event_probability=None,
            distribution_distance=None,
            model_identifier=self.model_identifier,
            model_version=self.model_version,
        )

    def save_model(self, path: Path) -> None:
        """Save the fitted model after an explicit experiment decision."""
        if self._model is None:
            raise RuntimeError("model must be fitted before saving")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._model.save_model(path)


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
