"""Explicit direction head for already fitted native feature pipelines.

Reference: XGBoost Python API, eval_metric and callback.EarlyStopping.
The caller owns native time splitting, label maturity and preprocessing fit.
This learner consumes original-unit returns, never scaled regression labels.
It deliberately has no generic predict() or return-valued PredictionRecord API.
"""

from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from quant.errors import DataContractError
from quant.models.estimators import create_estimator


class NativeDirectionLearner:
    """Binary logloss early stopping; outputs probability or a direction margin."""

    prediction_kind = "direction_margin"

    def __init__(
        self,
        *,
        preprocessing_id: str,
        params: dict[str, Any] | None = None,
        early_stopping_rounds: int = 30,
    ) -> None:
        if (
            not isinstance(preprocessing_id, str)
            or len(preprocessing_id) != 64
            or any(c not in "0123456789abcdef" for c in preprocessing_id)
        ):
            raise DataContractError("Direction learner requires a fitted-pipeline SHA-256")
        if type(early_stopping_rounds) is not int or early_stopping_rounds < 1:
            raise DataContractError("Direction patience must be a positive integer")
        self.preprocessing_id = preprocessing_id
        self.early_stopping_rounds = early_stopping_rounds
        self.params = {
            "n_estimators": 300,
            "max_depth": 2,
            "learning_rate": 0.03,
            "reg_lambda": 5.0,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "n_jobs": 1,
            "tree_method": "hist",
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            **dict(params or {}),
        }
        objective = self.params.get("objective")
        metric = self.params.get("eval_metric")
        if (objective, metric) not in {
            ("binary:logistic", "logloss"),
            ("binary:hinge", "error"),
        }:
            raise DataContractError("Direction learner requires logistic/logloss or hinge/error")
        if self.params.get("callbacks") is not None or self.params.get(
            "early_stopping_rounds"
        ) is not None:
            raise DataContractError("Direction learner owns its early-stopping callback")
        self.params.pop("callbacks", None)
        self.params.pop("early_stopping_rounds", None)
        self.columns: tuple[str, ...] = ()
        self.estimator = None

    @staticmethod
    def _features(X: pd.DataFrame) -> None:
        if not isinstance(X, pd.DataFrame) or X.empty:
            raise DataContractError("Direction features must be a nonempty DataFrame")
        if not X.columns.is_unique or not X.index.is_unique:
            raise DataContractError("Direction features require unique columns and row identity")
        if any(not isinstance(c, str) or not c for c in X.columns):
            raise DataContractError("Direction features require named columns")
        try:
            finite = np.isfinite(X.to_numpy(dtype=float)).all()
        except (TypeError, ValueError) as exc:
            raise DataContractError("Direction features must be numeric and finite") from exc
        if not finite:
            raise DataContractError("Direction features must be numeric and finite")

    @staticmethod
    def _labels(X: pd.DataFrame, labels: pd.Series) -> np.ndarray:
        if not isinstance(labels, pd.Series) or not labels.index.equals(X.index):
            raise DataContractError("Raw return labels must align exactly with native feature rows")
        try:
            values = labels.to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise DataContractError("Raw return labels must be finite") from exc
        if not np.isfinite(values).all():
            raise DataContractError("Raw return labels must be finite")
        # Zero is nonpositive during binary fitting; evaluation still uses sign(0)=0.
        return (values > 0).astype(int)

    @staticmethod
    def _weights(X: pd.DataFrame, weights: np.ndarray | pd.Series) -> np.ndarray:
        if isinstance(weights, pd.Series) and not weights.index.equals(X.index):
            raise DataContractError("Direction weight rows do not align")
        try:
            values = np.asarray(weights, dtype=float)
        except (TypeError, ValueError) as exc:
            raise DataContractError("Direction weights must be finite, nonnegative and nonempty") from exc
        if (
            values.shape != (len(X),)
            or not np.isfinite(values).all()
            or (values < 0).any()
            or not (values > 0).any()
        ):
            raise DataContractError("Direction weights must be finite, nonnegative and nonempty")
        return values

    def fit_preprocessed(
        self,
        X: pd.DataFrame,
        raw_return_labels: pd.Series,
        *,
        validation_features: pd.DataFrame,
        validation_returns: pd.Series,
        sample_weight: np.ndarray | pd.Series,
        validation_weight: np.ndarray | pd.Series,
    ) -> None:
        """Fit only the supplied native rows; never fit another feature pipeline."""
        import xgboost as xgb

        self._features(X)
        self._features(validation_features)
        if tuple(validation_features.columns) != tuple(X.columns):
            raise DataContractError("Direction validation feature schema/order mismatch")
        if not X.index.intersection(validation_features.index).empty:
            raise DataContractError("Direction training and validation row identities overlap")
        y = self._labels(X, raw_return_labels)
        y_valid = self._labels(validation_features, validation_returns)
        if np.unique(y).size != 2:
            raise DataContractError("Direction training requires both binary classes")
        weights = self._weights(X, sample_weight)
        valid_weights = self._weights(validation_features, validation_weight)
        if any(not (weights[y == label] > 0).any() for label in (0, 1)):
            raise DataContractError("Direction training requires positive weight in both classes")
        callback = xgb.callback.EarlyStopping(
            rounds=self.early_stopping_rounds,
            metric_name=self.params["eval_metric"],
            data_name="validation_0",
            maximize=False,
            save_best=True,
        )
        estimator = create_estimator("xgboost_direction", self.params)
        estimator.set_params(callbacks=[callback])
        estimator.fit(
            X,
            y,
            sample_weight=weights,
            eval_set=[(validation_features, y_valid)],
            sample_weight_eval_set=[valid_weights],
            verbose=False,
        )
        self.estimator = estimator
        self.columns = tuple(X.columns)

    def predict_proba_up(self, X: pd.DataFrame, *, preprocessing_id: str) -> np.ndarray:
        """Return P(raw return > 0), bound to the original fitted feature pipeline."""
        if self.estimator is None:
            raise DataContractError("Direction learner is not fitted")
        if preprocessing_id != self.preprocessing_id:
            raise DataContractError("Direction preprocessing identity mismatch")
        self._features(X)
        if tuple(X.columns) != self.columns:
            raise DataContractError("Direction prediction feature schema/order mismatch")
        probabilities = np.asarray(self.estimator.predict_proba(X))[:, 1]
        if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
            raise DataContractError("Direction probability output is invalid")
        return probabilities

    def predict_margin(self, X: pd.DataFrame, *, preprocessing_id: str) -> np.ndarray:
        """Return 2*P(up)-1; zero means exactly p=.5, not a predicted zero return."""
        return 2 * self.predict_proba_up(X, preprocessing_id=preprocessing_id) - 1

    def save(self, path: str | Path) -> None:
        """Save a trusted local artifact; do not overwrite existing model evidence."""
        if self.estimator is None:
            raise DataContractError("Direction learner is not fitted")
        if Path(path).exists():
            raise DataContractError("Direction artifact already exists")
        joblib.dump(
            {
                "schema_version": 1,
                "prediction_kind": self.prediction_kind,
                "target": "original_return>0",
                "preprocessing_id": self.preprocessing_id,
                "columns": self.columns,
                "params": self.params,
                "patience": self.early_stopping_rounds,
                "dependency_versions": {p: version(p) for p in ("xgboost", "scikit-learn")},
                "estimator": self.estimator,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path, *, preprocessing_id: str) -> "NativeDirectionLearner":
        """Read a trusted artifact only when dependency, schema and pipeline agree."""
        payload = joblib.load(path)
        if (
            payload.get("schema_version") != 1
            or payload.get("prediction_kind") != cls.prediction_kind
            or payload.get("target") != "original_return>0"
            or payload.get("preprocessing_id") != preprocessing_id
            or payload.get("dependency_versions")
            != {p: version(p) for p in ("xgboost", "scikit-learn")}
        ):
            raise DataContractError("Direction artifact schema/dependency/pipeline mismatch")
        model = cls(preprocessing_id=preprocessing_id, params=payload["params"],
                    early_stopping_rounds=payload["patience"])
        estimator = payload["estimator"]
        columns = tuple(payload["columns"])
        params = estimator.get_params()
        if (
            tuple(estimator.get_booster().feature_names) != columns
            or params.get("objective") != "binary:logistic"
            or (params.get("objective"), params.get("eval_metric")) not in {
                ("binary:logistic", "logloss"), ("binary:hinge", "error")
            }
            or not np.array_equal(estimator.classes_, [0, 1])
        ):
            raise DataContractError("Direction artifact model contract mismatch")
        if any(joblib.hash(value) != joblib.hash(params.get(key))
               for key, value in model.params.items()):
            raise DataContractError("Direction artifact training parameter metadata mismatch")
        callbacks = params.get("callbacks") or []
        if (
            len(callbacks) != 1
            or getattr(callbacks[0], "rounds", None) != model.early_stopping_rounds
            or getattr(callbacks[0], "metric_name", None) != "logloss"
            or getattr(callbacks[0], "data", None) != "validation_0"
            or getattr(callbacks[0], "maximize", None) is not False
            or getattr(callbacks[0], "save_best", None) is not True
        ):
            raise DataContractError("Direction artifact early-stopping metadata mismatch")
        model.estimator, model.columns = estimator, columns
        return model
