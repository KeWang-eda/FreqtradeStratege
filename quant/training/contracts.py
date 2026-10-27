"""Request and result values shared by training lifecycle adapters."""

from dataclasses import dataclass

import numpy as np

from quant.config import ExperimentConfig
from quant.dataset import Dataset
from quant.prediction import PredictionBatch
from quant.validation import SplitFold


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
