"""Executable information-boundary assertions used during every training run."""

import pandas as pd

from quant.errors import DataContractError

from .splitters import SplitFold


def audit_fold(
    fold: SplitFold, timestamps: pd.DatetimeIndex, label_end_times: pd.Series
) -> dict[str, object]:
    """Require disjoint indices and all training label ends < first test time."""
    train, test = fold.train_indices, fold.test_indices
    overlap = set(train).intersection(test)
    cutoff = pd.DatetimeIndex(label_end_times.iloc[train]).max()
    first_test = timestamps[test].min()
    if overlap or cutoff >= first_test or timestamps[train].max() >= first_test:
        raise DataContractError("Training information overlaps test period")
    return {
        "fold_id": fold.fold_id,
        "passed": True,
        "training_information_end": str(cutoff),
        "test_information_start": str(first_test),
        "purged": len(fold.purged_indices),
        "embargoed": len(fold.embargoed_indices),
    }
