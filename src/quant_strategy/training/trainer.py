"""Fit one model per pair, matching the strategy's independent-pair baseline."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_strategy.backends import create_regressor
from quant_strategy.backends.base import BackendCapabilities
from quant_strategy.config import ExperimentConfig
from quant_strategy.dataset import Dataset
from quant_strategy.errors import DataContractError
from quant_strategy.prediction import PredictionBatch, PredictionRecord
from quant_strategy.preprocessing import fit_preprocessing
from quant_strategy.validation import SplitFold
from quant_strategy.validation.leakage import audit_fold


@dataclass(frozen=True)
class TrainingRequest:
    """Explicit dataset and globally aligned, already-purged fold."""

    dataset: Dataset
    fold: SplitFold
    config: ExperimentConfig
    experiment_id: str


@dataclass
class TrainingResult:
    """Fitted per-pair pipelines, predictions and leakage audit events."""

    predictions: PredictionBatch
    truth: np.ndarray
    models: dict[str, tuple[object, object]]
    audit: list[dict]


class StandaloneBackend:
    """Own splitting inputs, preprocessing fit, estimator fit and predictions."""

    def describe_capabilities(self) -> BackendCapabilities:
        """Standalone supports external folds and versioned model persistence."""
        return BackendCapabilities(True, True, True)

    def run_training(self, request: TrainingRequest) -> TrainingResult:
        """Fit every pair without touching outer test features or labels."""
        dataset, fold, config = request.dataset, request.fold, request.config
        metadata = dataset.metadata
        audit = [
            audit_fold(fold, pd.DatetimeIndex(metadata["available_at"]), metadata["label_end_time"])
        ]
        records, truths, models = [], [], {}
        for pair in sorted(metadata.iloc[fold.test_indices]["pair"].unique()):
            train = fold.train_indices[metadata.iloc[fold.train_indices]["pair"].to_numpy() == pair]
            test = fold.test_indices[metadata.iloc[fold.test_indices]["pair"].to_numpy() == pair]
            if len(train) < 2:
                raise DataContractError(f"Insufficient training samples for {pair}")
            valid = None
            if config.model.name == "xgboost" and config.model.params.get("early_stopping_rounds"):
                split = max(1, int(len(train) * 0.8))
                valid = train[split:]
                valid_start = metadata.iloc[valid]["available_at"].min()
                inner = train[:split]
                train = inner[(metadata.iloc[inner]["label_end_time"] < valid_start).to_numpy()]
                if len(train) < 2 or not len(valid):
                    raise DataContractError("Insufficient inner validation after label purge")
                audit.append(
                    {
                        "fold_id": fold.fold_id,
                        "pair": pair,
                        "inner_validation_start": str(valid_start),
                        "inner_training_end": str(metadata.iloc[train]["label_end_time"].max()),
                        "passed": True,
                    }
                )
            preprocessing = fit_preprocessing(dataset.X.iloc[train])
            X_train = preprocessing.transform(dataset.X.iloc[train])
            model = create_regressor(config.model, config.seed)
            kwargs = (
                {}
                if valid is None
                else {
                    "X_valid": preprocessing.transform(dataset.X.iloc[valid]),
                    "y_valid": dataset.y.iloc[valid],
                }
            )
            model.fit(X_train, dataset.y.iloc[train], **kwargs)
            values = model.predict(preprocessing.transform(dataset.X.iloc[test]))
            information_rows = train if valid is None else np.concatenate([train, valid])
            information_end = metadata.iloc[information_rows]["label_end_time"].max()
            model_version = f"{request.experiment_id}/{fold.fold_id}/{pair}"
            for index, value in zip(test, values, strict=True):
                row = metadata.iloc[index]
                if information_end >= row.available_at:
                    raise DataContractError("Training cutoff violates prediction availability")
                records.append(
                    PredictionRecord(
                        pair,
                        row.candle_timestamp,
                        float(value),
                        "raw_return" if config.label.mode == "raw" else "volnorm_return",
                        config.model.name,
                        model_version,
                        config.feature_version,
                        config.label.mode,
                        config.label.prediction_horizon,
                        bool(np.isfinite(value)),
                        information_end,
                    )
                )
                truths.append(float(dataset.y.iloc[index]))
            models[pair] = (preprocessing, model)
        return TrainingResult(
            PredictionBatch(tuple(records), request.experiment_id, "standalone"),
            np.asarray(truths),
            models,
            audit,
        )

    def predict(self, request: TrainingResult) -> PredictionBatch:
        """Expose normalized predictions from the completed training request."""
        return request.predictions
