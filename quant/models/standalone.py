"""Versioned standalone model wrapper and strict feature-schema persistence."""

from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from quant.errors import DataContractError


class StandaloneRegressor:
    """Scikit-learn compatible estimator with optional XGBoost validation."""

    def __init__(self, estimator: Any, name: str, prediction_power: str = "identity"):
        self.estimator = estimator
        self.name = name
        self.prediction_power = prediction_power
        self.selected_power = 1.0
        self.columns: tuple[str, ...] = ()
        self.positive_return_mean = 0.0
        self.negative_return_mean = 0.0
        self.constant_probability: float | None = None

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        *,
        X_valid: pd.DataFrame | None = None,
        y_valid: pd.Series | None = None,
        sample_weight: np.ndarray | None = None,
    ) -> None:
        """Fit; early stopping consumes only an inner chronological validation."""
        self.columns = tuple(X.columns)
        self.selected_power = 1.0
        kwargs = {}
        directional = self.name == "xgboost_direction"
        self.constant_probability = None
        early_stopping = (
            self.name in {"xgboost", "xgboost_direction"}
            and self.estimator.get_params().get("early_stopping_rounds")
        )
        if early_stopping:
            if X_valid is None or y_valid is None:
                raise DataContractError("XGBoost early stopping requires inner validation")
            eval_target = (np.asarray(y_valid) > 0).astype(int) if directional else y_valid
            kwargs = {"eval_set": [(X_valid, eval_target)], "verbose": False}
        target = (np.asarray(y) > 0).astype(int) if directional else y
        if sample_weight is not None:
            kwargs["sample_weight"] = sample_weight
        if directional:
            actual = np.asarray(y, dtype=float)
            positive = actual[actual > 0]
            negative = actual[actual < 0]
            self.positive_return_mean = float(positive.mean()) if len(positive) else 0.0
            self.negative_return_mean = float(-negative.mean()) if len(negative) else 0.0
            if np.unique(target).size < 2:
                self.constant_probability = float(target[0])
            else:
                self.estimator.fit(X, target, **kwargs)
        else:
            self.estimator.fit(X, target, **kwargs)
        if (
            self.name == "xgboost"
            and self.prediction_power
            in {"validation_grid", "validation_mae", "validation_spearman"}
            and X_valid is not None
            and y_valid is not None
        ):
            raw = np.asarray(self.estimator.predict(X_valid), dtype=float)
            actual = np.asarray(y_valid, dtype=float)
            candidates = np.arange(0.75, 2.01, 0.05)
            self.selected_power = float(
                min(
                    candidates,
                    key=lambda power: self._calibration_score(actual, raw, power),
                )
            )

    def _calibration_score(self, actual: np.ndarray, raw: np.ndarray, power: float) -> float:
        calibrated = np.sign(raw) * np.abs(raw) ** power
        if self.prediction_power == "validation_mae":
            return float(np.mean(np.abs(actual - calibrated)))
        if self.prediction_power == "validation_spearman":
            return -float(pd.Series(actual).corr(pd.Series(calibrated), method="spearman"))
        return float(np.mean((actual - calibrated) ** 2))

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Reject reordered/missing feature columns before prediction."""
        if tuple(X.columns) != self.columns:
            raise DataContractError("Prediction feature schema/order mismatch")
        if self.name == "xgboost_direction":
            probability = (
                np.full(len(X), self.constant_probability)
                if self.constant_probability is not None
                else np.asarray(self.estimator.predict_proba(X), dtype=float)[:, 1]
            )
            return (
                probability * self.positive_return_mean
                - (1.0 - probability) * self.negative_return_mean
            )
        prediction = np.asarray(self.estimator.predict(X), dtype=float).reshape(-1)
        if self.prediction_power in {
            "validation_grid",
            "validation_mae",
            "validation_spearman",
        }:
            prediction = np.sign(prediction) * np.abs(prediction) ** self.selected_power
        return prediction

    def save(self, path: str | Path) -> None:
        """Persist a local trusted estimator with schema and dependency version."""
        joblib.dump(
            {
                "schema_version": 1,
                "name": self.name,
                "columns": self.columns,
                "dependency_version": version(
                    "xgboost"
                    if self.name in {"xgboost", "xgboost_direction"}
                    else "scikit-learn"
                ),
                "model": self,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> "StandaloneRegressor":
        """Load trusted local artifacts only; reject incompatible versions."""
        payload = joblib.load(path)
        dependency = (
            "xgboost"
            if payload.get("name") in {"xgboost", "xgboost_direction"}
            else "scikit-learn"
        )
        if payload.get("schema_version") != 1 or payload.get("dependency_version") != version(
            dependency
        ):
            raise DataContractError("Estimator schema/dependency version mismatch")
        model = payload["model"]
        if model.columns != payload["columns"]:
            raise DataContractError("Estimator feature schema mismatch")
        return model
