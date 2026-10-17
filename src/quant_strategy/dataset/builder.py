"""Panel datasets keep global time boundaries and explicit exclusion counts."""

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Mapping

import numpy as np
import pandas as pd

from quant_strategy.config import ExperimentConfig
from quant_strategy.errors import DataContractError
from quant_strategy.features import build_features
from quant_strategy.labels import build_labels
from quant_strategy.market_data import validate_ohlcv
from quant_strategy.market_data.contracts import frame_fingerprint, validate_candle_grid
from quant_strategy.market_data.time_index import timeframe_delta


@dataclass(frozen=True)
class Dataset:
    """Positionally aligned features, target and per-sample provenance."""

    X: pd.DataFrame
    y: pd.Series
    metadata: pd.DataFrame
    quality: dict[str, dict[str, int]]
    exclusions: pd.DataFrame = field(default_factory=pd.DataFrame)

    def __post_init__(self) -> None:
        if not self.X.index.equals(self.y.index) or not self.X.index.equals(self.metadata.index):
            raise DataContractError("Dataset index alignment mismatch")
        if not self.X.columns.is_unique or any(not c.startswith("%") for c in self.X):
            raise DataContractError("Dataset must contain unique feature columns only")
        if not np.isfinite(self.X.to_numpy(dtype=float)).all() or not np.isfinite(self.y).all():
            raise DataContractError("Dataset must contain finite features and labels")
        required = {
            "sample_id",
            "data_version",
            "pair",
            "candle_timestamp",
            "available_at",
            "feature_start_time",
            "label_start_time",
            "label_end_time",
        }
        if required - set(self.metadata) or self.metadata.empty:
            raise DataContractError("Dataset requires nonempty sample identity and time provenance")
        meta = self.metadata
        for column in ("sample_id", "data_version"):
            if not meta[column].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
                raise DataContractError(f"Invalid {column}")
        if meta.sample_id.duplicated().any() or meta.duplicated(["pair", "candle_timestamp"]).any():
            raise DataContractError("Duplicate sample identity")
        for column in (
            "candle_timestamp",
            "available_at",
            "feature_start_time",
            "label_start_time",
            "label_end_time",
        ):
            if not isinstance(meta[column].dtype, pd.DatetimeTZDtype) or meta[column].isna().any():
                raise DataContractError(f"Invalid sample timestamp: {column}")
        if (
            (meta.feature_start_time > meta.candle_timestamp).any()
            or (meta.candle_timestamp >= meta.available_at).any()
            or (meta.label_start_time != meta.available_at).any()
            or (meta.label_end_time < meta.available_at).any()
        ):
            raise DataContractError("Sample information boundaries are invalid")


def build_dataset(frames: Mapping[str, pd.DataFrame], config: ExperimentConfig) -> Dataset:
    """Build a UTC panel, reporting warmup/tail exclusions without imputation."""
    panels, exclusions = [], []
    quality = {}
    for pair, raw in frames.items():
        frame = validate_ohlcv(raw)
        validate_candle_grid(frame, config.timeframe)
        version = frame_fingerprint(frame)
        step = timeframe_delta(config.timeframe)
        segments = frame.date.diff().ne(step).cumsum()
        pair_panels, pair_exclusions = [], []
        feature_missing = label_missing = 0
        for _, segment in frame.groupby(segments, sort=False):
            segment = segment.reset_index(drop=True)
            features = build_features(segment, config.periods, config.features)
            labels = build_labels(segment, config.label, config.timeframe)
            valid_features = features.notna().all(axis=1)
            valid_labels = labels["target"].notna() & labels["label_end_time"].notna()
            keep = valid_features & valid_labels
            feature_missing += int((~valid_features).sum())
            label_missing += int((~valid_labels).sum())
            identity = repr(
                (
                    pair,
                    version,
                    config.timeframe,
                    config.periods,
                    config.features,
                    asdict(config.label),
                )
            )
            panel = features.assign(
                target=labels["target"],
                label_end_time=labels["label_end_time"],
                candle_timestamp=segment.date,
                available_at=segment.date + step,
                label_start_time=segment.date + step,
                pair=pair,
                data_version=version,
                feature_start_time=segment.date.iloc[0],
                sample_id=[
                    hashlib.sha256(f"{identity}:{stamp.isoformat()}".encode()).hexdigest()
                    for stamp in segment.date
                ],
            )
            pair_panels.append(panel.loc[keep])
            rejected = panel.loc[
                ~keep, ["sample_id", "data_version", "pair", "candle_timestamp"]
            ].copy()
            rejected["feature_unavailable"] = ~valid_features.loc[~keep]
            rejected["label_unavailable"] = ~valid_labels.loc[~keep]
            rejected["reason"] = "feature_warmup"
            at_gap = segment.date.iloc[-1] != frame.date.iloc[-1]
            rejected.loc[rejected.label_unavailable, "reason"] = (
                "label_window_gap" if at_gap else "label_tail_unavailable"
            )
            pair_exclusions.append(rejected)
        kept = pd.concat(pair_panels)
        if kept.empty:
            raise DataContractError(f"No complete feature/label samples for {pair}")
        quality[pair] = {
            "input": len(frame),
            "feature_unavailable": feature_missing,
            "label_unavailable": label_missing,
            "excluded": len(frame) - len(kept),
            "kept": len(kept),
            "time_gaps": int((frame["date"].diff() > timeframe_delta(config.timeframe)).sum()),
        }
        panels.append(kept)
        exclusions.extend(pair_exclusions)
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
        panel[
            [
                "sample_id",
                "data_version",
                "pair",
                "candle_timestamp",
                "available_at",
                "feature_start_time",
                "label_start_time",
                "label_end_time",
            ]
        ],
        quality,
        pd.concat(exclusions, ignore_index=True)
        .sort_values(["candle_timestamp", "pair"], kind="stable")
        .reset_index(drop=True),
    )
