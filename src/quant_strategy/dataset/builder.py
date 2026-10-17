"""Panel datasets keep global time boundaries and explicit exclusion counts."""

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from quant_strategy.config import ExperimentConfig
from quant_strategy.errors import DataContractError
from quant_strategy.features import build_features
from quant_strategy.labels import build_labels
from quant_strategy.market_data import validate_ohlcv
from quant_strategy.market_data.time_index import timeframe_delta


@dataclass(frozen=True)
class Dataset:
    """Positionally aligned features, target and per-sample provenance."""

    X: pd.DataFrame
    y: pd.Series
    metadata: pd.DataFrame
    quality: dict[str, dict[str, int]]

    def __post_init__(self) -> None:
        if not self.X.index.equals(self.y.index) or not self.X.index.equals(self.metadata.index):
            raise DataContractError("Dataset index alignment mismatch")
        if not self.X.columns.is_unique or any(not c.startswith("%") for c in self.X):
            raise DataContractError("Dataset must contain unique feature columns only")
        if not np.isfinite(self.X.to_numpy(dtype=float)).all() or not np.isfinite(self.y).all():
            raise DataContractError("Dataset must contain finite features and labels")


def build_dataset(frames: Mapping[str, pd.DataFrame], config: ExperimentConfig) -> Dataset:
    """Build a UTC panel, reporting warmup/tail exclusions without imputation."""
    panels = []
    quality = {}
    for pair, raw in frames.items():
        frame = validate_ohlcv(raw)
        features = build_features(frame, config.periods, config.features)
        labels = build_labels(frame, config.label, config.timeframe)
        valid_features = features.notna().all(axis=1)
        valid_labels = labels["target"].notna() & labels["label_end_time"].notna()
        keep = valid_features & valid_labels
        quality[pair] = {
            "input": len(frame),
            "feature_unavailable": int((~valid_features).sum()),
            "label_unavailable": int((~valid_labels).sum()),
            "excluded": int((~keep).sum()),
            "kept": int(keep.sum()),
            "time_gaps": int((frame["date"].diff() > timeframe_delta(config.timeframe)).sum()),
        }
        panel = features.assign(
            target=labels["target"],
            label_end_time=labels["label_end_time"],
            candle_timestamp=frame["date"],
            available_at=frame["date"] + timeframe_delta(config.timeframe),
            pair=pair,
        )
        panels.append(panel.loc[keep])
    if not panels:
        raise DataContractError("No input pairs")
    panel = (
        pd.concat(panels)
        .sort_values(["available_at", "pair"], kind="stable")
        .reset_index(drop=True)
    )
    if panel.empty:
        raise DataContractError("No complete feature/label samples after warmup")
    columns = [c for c in panel if c.startswith("%")]
    return Dataset(
        panel[columns],
        panel["target"],
        panel[["pair", "candle_timestamp", "available_at", "label_end_time"]],
        quality,
    )
