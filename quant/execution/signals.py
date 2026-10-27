"""Entry signals retain the original prediction-sign rule."""

import numpy as np
import pandas as pd

from quant.labels import FREQAI_RETURN_TARGET


def read_model_prediction(dataframe: pd.DataFrame) -> pd.Series:
    """Read FreqAI predictions without confusing them with research truth."""
    return dataframe[FREQAI_RETURN_TARGET]


def should_enter_long(model_prediction: pd.Series, prediction_ready: pd.Series) -> pd.Series:
    """Positive, ready, finite predictions generate long signals."""
    return prediction_ready & np.isfinite(model_prediction) & (model_prediction > 0)


def should_enter_short(model_prediction: pd.Series, prediction_ready: pd.Series) -> pd.Series:
    """Negative, ready, finite predictions generate short signals."""
    return prediction_ready & np.isfinite(model_prediction) & (model_prediction < 0)
