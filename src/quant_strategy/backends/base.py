"""Backend capabilities distinguish independent training from FreqAI lifecycle."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BackendCapabilities:
    """Only explicitly supported operations may be requested."""

    independent_splits: bool
    early_stopping: bool
    save_load: bool
    incremental_training: bool = False
    batch_prediction: bool = True


class Regressor(Protocol):
    """Standalone estimator contract, without framework lifecycle objects."""

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        *,
        X_valid: pd.DataFrame | None = None,
        y_valid: pd.Series | None = None,
    ) -> None:
        """Fit exclusively on training and optional internal validation rows."""
        ...

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict using the fitted training column order."""
        ...

    def save(self, path: str | Path) -> None:
        """Persist a versioned estimator artifact."""
        ...


class TrainingBackend(Protocol):
    """High-level lifecycle contract; unsupported operations fail explicitly."""

    def describe_capabilities(self) -> BackendCapabilities:
        """Describe the backend's supported lifecycle operations."""
        ...

    def run_training(self, request: Any) -> Any:
        """Run a backend-specific, validated training request."""
        ...

    def predict(self, request: Any) -> Any:
        """Adapt predictions to the shared prediction contract."""
        ...
