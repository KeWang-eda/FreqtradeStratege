"""Versioned estimator wrappers and strict feature-schema persistence."""

from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from quant_strategy.errors import DataContractError


class StandaloneRegressor:
    """Scikit-learn compatible estimator with optional XGBoost validation."""

    def __init__(self, estimator: Any, name: str):
        self.estimator = estimator
        self.name = name
        self.columns: tuple[str, ...] = ()

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        *,
        X_valid: pd.DataFrame | None = None,
        y_valid: pd.Series | None = None,
    ) -> None:
        """Fit; early stopping consumes only an inner chronological validation."""
        self.columns = tuple(X.columns)
        kwargs = {}
        if self.name == "xgboost" and self.estimator.get_params().get("early_stopping_rounds"):
            if X_valid is None or y_valid is None:
                raise DataContractError("XGBoost early stopping requires inner validation")
            kwargs = {"eval_set": [(X_valid, y_valid)], "verbose": False}
        self.estimator.fit(X, y, **kwargs)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Reject reordered/missing feature columns before prediction."""
        if tuple(X.columns) != self.columns:
            raise DataContractError("Prediction feature schema/order mismatch")
        return np.asarray(self.estimator.predict(X)).reshape(-1)

    def save(self, path: str | Path) -> None:
        """Persist a local trusted estimator with schema and dependency version."""
        joblib.dump(
            {
                "schema_version": 1,
                "name": self.name,
                "columns": self.columns,
                "dependency_version": version(
                    "xgboost" if self.name == "xgboost" else "scikit-learn"
                ),
                "model": self,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> "StandaloneRegressor":
        """Load trusted local artifacts only; reject incompatible versions."""
        payload = joblib.load(path)
        dependency = "xgboost" if payload.get("name") == "xgboost" else "scikit-learn"
        if payload.get("schema_version") != 1 or payload.get("dependency_version") != version(
            dependency
        ):
            raise DataContractError("Estimator schema/dependency version mismatch")
        model = payload["model"]
        if model.columns != payload["columns"]:
            raise DataContractError("Estimator feature schema mismatch")
        return model
