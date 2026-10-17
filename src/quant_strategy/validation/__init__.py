"""Time-series validation with inclusive label intervals and explicit gaps."""

from .metrics import prediction_metrics
from .splitters import SplitFold, TimeSeriesSplitter

__all__ = ["SplitFold", "TimeSeriesSplitter", "prediction_metrics"]
