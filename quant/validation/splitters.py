"""Global-time split boundaries for single and multi-pair datasets.

Reference: https://scikit-learn.org/stable/modules/cross_validation.html
Unlike a row-count TimeSeriesSplit, all pairs at one timestamp stay together.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant.config import ValidationConfig
from quant.errors import DataContractError


@dataclass(frozen=True)
class SplitFold:
    """Positional sample indices and auditable boundary exclusions."""

    fold_id: str
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    purged_indices: np.ndarray
    embargoed_indices: np.ndarray


class TimeSeriesSplitter:
    """Forward-only folds, always purging label ends >= first test time.

    Embargo excludes the last N global timestamps BEFORE the test boundary.
    No future test-side training is permitted. Explicit purge_candles adds a
    conservative gap; it can never relax the true label-interval purge.
    """

    def __init__(self, config: ValidationConfig):
        self.config = config

    def split(self, timestamps: pd.DatetimeIndex, label_end_times: pd.Series) -> list[SplitFold]:
        """Return valid folds, or fail for unordered/undersized inputs."""
        times = pd.DatetimeIndex(timestamps)
        ends = pd.DatetimeIndex(label_end_times)
        if (
            len(times) != len(ends)
            or times.tz is None
            or ends.tz is None
            or times.hasnans
            or ends.hasnans
            or not times.is_monotonic_increasing
        ):
            raise DataContractError(
                "Split timestamps/label ends must be aligned, UTC-aware and sorted"
            )
        if (ends < times).any():
            raise DataContractError("Label end precedes sample availability")
        unique = times.unique()
        count = len(unique)
        config = self.config
        if config.method == "fixed_holdout":
            start = int(count * (1 - config.test_size))
            windows = [(start, count)]
        else:
            start = config.min_train_size or count // (config.n_splits + 1)
            if start >= count:
                raise DataContractError("min_train_size leaves no test samples")
            blocks = np.array_split(np.arange(start, count), config.n_splits)
            windows = [(int(block[0]), int(block[-1]) + 1) for block in blocks if len(block)]
            if len(windows) != config.n_splits:
                raise DataContractError("Insufficient timestamps for requested folds")
        folds = []
        for number, (start, stop) in enumerate(windows):
            if start < 1 or stop <= start:
                raise DataContractError("Empty train/test time window")
            lower = (
                max(0, start - config.train_window_size) if config.method == "rolling_window" else 0
            )
            raw_train = (times >= unique[lower]) & (times < unique[start])
            overlap = raw_train & (ends >= unique[start])
            if config.purge_candles:
                overlap |= raw_train & (times >= unique[max(0, start - config.purge_candles)])
            embargo = (
                raw_train & ~overlap & (times >= unique[max(0, start - config.embargo_candles)])
                if config.embargo_candles
                else np.zeros(len(times), dtype=bool)
            )
            train = np.flatnonzero(raw_train & ~overlap & ~embargo)
            test = np.flatnonzero((times >= unique[start]) & (times <= unique[stop - 1]))
            if not len(train) or not len(test):
                raise DataContractError("Purge/embargo leaves an empty train or test fold")
            folds.append(
                SplitFold(
                    str(number),
                    train,
                    test,
                    times[train].min(),
                    times[train].max(),
                    times[test].min(),
                    times[test].max(),
                    np.flatnonzero(overlap),
                    np.flatnonzero(embargo),
                )
            )
        return folds
