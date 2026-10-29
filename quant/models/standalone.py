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

    def __init__(self, estimator: Any, name: str):
        self.estimator = estimator
        self.name = name
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
        return np.asarray(self.estimator.predict(X), dtype=float).reshape(-1)

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
