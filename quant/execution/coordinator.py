"""Assemble a cross-pair snapshot for exactly one timestamp before ranking."""

from typing import Sequence

import pandas as pd

from quant.errors import DataContractError
from quant.portfolio import PoolCandidate, build_candidate
from quant.prediction import PredictionBatch


def candidates_from_batch(
    batch: PredictionBatch, pairs: Sequence[str], timestamp: pd.Timestamp
) -> tuple[PoolCandidate, ...] | None:
    """Return None for incomplete data, () for complete but unusable data."""
    records = batch.records
    if any(record.candle_timestamp != timestamp for record in records):
        raise DataContractError("Cross-pair ranking requires a single signal timestamp")
    if len({r.pair for r in records}) != len(records):
        raise DataContractError("Duplicate pair in prediction snapshot")
    semantics = {(r.prediction_kind, r.prediction_horizon, r.feature_version) for r in records}
    if len(semantics) > 1:
        raise DataContractError("Cannot rank incompatible prediction semantics")
    by_pair = {record.pair: record for record in records}
    if not pairs or any(pair not in by_pair for pair in pairs):
        return None
    return tuple(
        candidate
        for pair in pairs
        if (candidate := build_candidate(pair, by_pair[pair].prediction, by_pair[pair].is_ready))
        is not None
    )
