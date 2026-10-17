"""Prediction quality is distinct from strategy returns and trading costs."""

import numpy as np
import pandas as pd


def prediction_metrics(
    truth: np.ndarray | pd.Series, prediction: np.ndarray | pd.Series
) -> dict[str, float | int | None]:
    """Evaluate finite pairs; undefined constant/empty correlations become None."""
    actual = np.asarray(truth, dtype=float).reshape(-1)
    predicted = np.asarray(prediction, dtype=float).reshape(-1)
    if actual.shape != predicted.shape:
        raise ValueError("Truth and prediction lengths disagree")
    valid = np.isfinite(actual) & np.isfinite(predicted)
    actual, predicted = actual[valid], predicted[valid]
    if not len(actual):
        return {
            "n": 0,
            "mae": None,
            "rmse": None,
            "direction_accuracy": None,
            "pearson_ic": None,
            "spearman_ic": None,
        }

    def correlation(rank: bool) -> float | None:
        left, right = pd.Series(actual), pd.Series(predicted)
        if len(left) < 2 or left.nunique() < 2 or right.nunique() < 2:
            return None
        return float(left.rank().corr(right.rank()) if rank else left.corr(right))

    return {
        "n": len(actual),
        "mae": float(np.abs(actual - predicted).mean()),
        "rmse": float(np.sqrt(np.mean((actual - predicted) ** 2))),
        "direction_accuracy": float(np.mean(np.sign(actual) == np.sign(predicted))),
        "pearson_ic": correlation(False),
        "spearman_ic": correlation(True),
    }
