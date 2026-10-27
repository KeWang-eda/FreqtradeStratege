"""Framework-independent estimator interface used by research backends."""

from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd


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
