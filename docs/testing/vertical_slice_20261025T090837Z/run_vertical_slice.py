from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from quant_strategy.backends import create_regressor
from quant_strategy.config import ExperimentConfig, LabelConfig, ModelConfig, ValidationConfig
from quant_strategy.preprocessing import fit_preprocessing
from quant_strategy.validation.metrics import prediction_metrics

ROOT = Path.cwd()
OUT = ROOT / "docs/testing/vertical_slice_20261025T090837Z"
OUT.mkdir(parents=True, exist_ok=True)
HOLDOUT_START = pd.Timestamp("2025-10-17T04:00:00Z")
PAIRS = {
    "BTC/USDT:USDT": ROOT / "data/futures/BTC_USDT_USDT-4h-futures.feather",
    "ETH/USDT:USDT": ROOT / "data/futures/ETH_USDT_USDT-4h-futures.feather",
    "BNB/USDT:USDT": ROOT / "data/futures/BNB_USDT_USDT-4h-futures.feather",
}


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_development_prefix(path: Path) -> pd.DataFrame:
    table = ds.dataset(path, format="feather").to_table(
        filter=ds.field("date") < HOLDOUT_START.to_pydatetime(),
        columns=["date", "open", "high", "low", "close", "volume"],
    )
    return table.to_pandas()


frames = {}
quality = {}
for pair, path in PAIRS.items():
    before = file_sha(path)
    frame = read_development_prefix(path)
    after = file_sha(path)
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    numeric = frame[["open", "high", "low", "close", "volume"]].to_numpy(float)
    invalid_ohlc = (
        (frame.high < frame[["open", "close", "low"]].max(axis=1))
        | (frame.low > frame[["open", "close", "high"]].min(axis=1))
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    quality[pair] = {
        "path": str(path.relative_to(ROOT)),
        "sha256": before,
        "unchanged": before == after,
        "rows": len(frame),
        "first": frame.date.iloc[0].isoformat(),
        "last": frame.date.iloc[-1].isoformat(),
        "duplicate_timestamps": int(frame.date.duplicated().sum()),
        "null_timestamps": int(frame.date.isna().sum()),
        "nan_numeric": int(np.isnan(numeric).sum()),
        "nonfinite_numeric": int((~np.isfinite(numeric)).sum()),
        "invalid_ohlc": int(invalid_ohlc.sum()),
    }
    if any(quality[pair][key] for key in ("duplicate_timestamps", "null_timestamps", "nan_numeric", "nonfinite_numeric", "invalid_ohlc")):
        raise RuntimeError(f"data quality failure: {pair}")
    frames[pair] = frame

config = ExperimentConfig(
    name="vertical_slice_non_formal_raw_ridge",
    label=LabelConfig("raw", 3, 14),
    validation=ValidationConfig(
        method="fixed_holdout",
        n_splits=1,
        test_size=0.2,
        embargo_candles=3,
        final_holdout_fraction=0.15,
    ),
    model=ModelConfig("standalone", "ridge", {"alpha": 10.0}),
    feature_version="baseline-v2",
    seed=42,
    features=(),
    periods=(6, 14, 24),
    timeframe="4h",
    data={pair: str(path) for pair, path in PAIRS.items()},
)


class DevelopmentDataset:
    def __init__(self, X, y, metadata, quality, exclusions):
        self.X, self.y, self.metadata = X, y, metadata
        self.quality, self.exclusions = quality, exclusions


def build_local_causal_dataset(input_frames):
    panels, excluded, quality_out = [], [], {}
    step = pd.Timedelta(hours=4)
    for pair, frame in input_frames.items():
        work = frame.copy()
        features = pd.DataFrame(index=work.index)
        close = work.close.replace(0, np.nan)
        features["%ret_1"] = close.pct_change()
        features["%ret_3"] = close.pct_change(3)
        features["%ret_6"] = close.pct_change(6)
        features["%range"] = (work.high - work.low) / close
        features["%volume_change"] = work.volume.replace(0, np.nan).pct_change()
        features["%close_mean_6"] = close / close.rolling(6).mean() - 1
        target = close.shift(-3) / close - 1
        label_end = work.date.shift(-3) + step
        available = work.date + step
        sample_ids = [
            hashlib.sha256(f"vertical-slice:{pair}:{stamp.isoformat()}".encode()).hexdigest()
            for stamp in work.date
        ]
        meta = pd.DataFrame(
            {
                "sample_id": sample_ids,
                "data_version": file_sha(PAIRS[pair]),
                "pair": pair,
                "candle_timestamp": work.date,
                "available_at": available,
                "feature_start_time": work.date.iloc[0],
                "label_start_time": available,
                "label_end_time": label_end,
            }
        )
        valid = features.notna().all(axis=1) & target.notna() & label_end.notna()
        excluded.append(meta.loc[~valid, ["sample_id", "pair", "candle_timestamp"]].assign(reason="feature_warmup_or_label_tail"))
        quality_out[pair] = {
            "input": len(work),
            "feature_unavailable_or_label_missing": int((~valid).sum()),
            "kept": int(valid.sum()),
        }
        part = meta.loc[valid].copy()
        part["target"] = target.loc[valid].to_numpy()
        for column in features.columns:
            part[column] = features.loc[valid, column].to_numpy()
        panels.append(part)
    combined = pd.concat(panels, ignore_index=True).sort_values(
        ["available_at", "pair"], kind="stable"
    )
    feature_columns = [column for column in combined if column.startswith("%")]
    X = combined[feature_columns].reset_index(drop=True)
    y = combined["target"].reset_index(drop=True)
    metadata = combined[
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
    ].reset_index(drop=True)
    exclusions = pd.concat(excluded, ignore_index=True)
    return DevelopmentDataset(X, y, metadata, quality_out, exclusions)


dataset = build_local_causal_dataset(frames)
metadata = dataset.metadata.copy()
times = pd.DatetimeIndex(sorted(metadata.available_at.unique()))
if len(times) < 10:
    raise RuntimeError("insufficient development timeline")
t1 = times[int(len(times) * 0.60)]
t2 = times[int(len(times) * 0.80)]
train_mask = metadata.available_at < t1
validation_mask = (metadata.available_at >= t1) & (metadata.available_at < t2)
test_mask = metadata.available_at >= t2
if not train_mask.any() or not validation_mask.any() or not test_mask.any():
    raise RuntimeError("empty chronological split")
if metadata.loc[train_mask, "available_at"].max() >= metadata.loc[validation_mask, "available_at"].min():
    raise RuntimeError("train/validation overlap")
if metadata.loc[validation_mask, "available_at"].max() >= metadata.loc[test_mask, "available_at"].min():
    raise RuntimeError("validation/test overlap")

prediction_rows = []
model_records = {}
model_dir = OUT / "models"
model_dir.mkdir(exist_ok=True)
for pair in PAIRS:
    train_ids = metadata.index[train_mask & (metadata.pair == pair)]
    validation_ids = metadata.index[validation_mask & (metadata.pair == pair)]
    test_ids = metadata.index[test_mask & (metadata.pair == pair)]
    preprocessing = fit_preprocessing(dataset.X.loc[train_ids])
    model = create_regressor(config.model, config.seed)
    model.fit(preprocessing.transform(dataset.X.loc[train_ids]), dataset.y.loc[train_ids])
    model_path = model_dir / (pair.split("/")[0].lower() + ".joblib")
    model.save(model_path)
    model_records[pair] = {
        "path": str(model_path.relative_to(ROOT)),
        "sha256": file_sha(model_path),
        "train_rows": len(train_ids),
        "feature_count": dataset.X.shape[1],
    }
    for split, ids in (("validation", validation_ids), ("development_test", test_ids)):
        values = model.predict(preprocessing.transform(dataset.X.loc[ids]))
        for sample_id, value in zip(ids, values, strict=True):
            row = metadata.loc[sample_id]
            prediction_rows.append(
                {
                    "sample_id": row.sample_id,
                    "pair": pair,
                    "available_at": row.available_at.isoformat(),
                    "candle_timestamp": row.candle_timestamp.isoformat(),
                    "label_end_time": row.label_end_time.isoformat(),
                    "split": split,
                    "target": float(dataset.y.loc[sample_id]),
                    "prediction": float(value),
                    "baseline_zero": 0.0,
                }
            )
predictions = pd.DataFrame(prediction_rows).sort_values(["available_at", "pair"]).reset_index(drop=True)
predictions.to_csv(OUT / "predictions.csv", index=False)


def score(frame: pd.DataFrame) -> dict:
    return {
        "model": prediction_metrics(frame.target, frame.prediction),
        "zero_baseline": prediction_metrics(frame.target, frame.baseline_zero),
    }


metrics = {
    "validation": score(predictions[predictions.split == "validation"]),
    "development_test": score(predictions[predictions.split == "development_test"]),
}
rank_ics = []
for _, group in predictions[predictions.split == "development_test"].groupby("available_at"):
    if len(group) >= 2 and group.target.nunique() > 1 and group.prediction.nunique() > 1:
        rank_ics.append(float(group.target.rank().corr(group.prediction.rank())))
metrics["development_test"]["rank_ic_mean"] = float(np.mean(rank_ics)) if rank_ics else None

fee_each_side = 0.0005
equity = 1.0
peak = 1.0
max_drawdown = 0.0
next_free = None
trades = []
test_predictions = predictions[predictions.split == "development_test"]
for raw_time, group in test_predictions.groupby("available_at", sort=True):
    decision_time = pd.Timestamp(raw_time)
    if next_free is not None and decision_time < next_free:
        continue
    candidates = group[np.isfinite(group.prediction) & (group.prediction != 0)]
    if candidates.empty:
        continue
    chosen = candidates.iloc[np.argmax(np.abs(candidates.prediction.to_numpy()))]
    direction = 1 if chosen.prediction > 0 else -1
    gross = direction * chosen.target
    net = gross - 2 * fee_each_side
    equity *= 1 + net
    peak = max(peak, equity)
    max_drawdown = min(max_drawdown, equity / peak - 1)
    exit_time = decision_time + pd.Timedelta(hours=12)
    next_free = exit_time
    trades.append(
        {
            "entry_time": decision_time.isoformat(),
            "exit_time": exit_time.isoformat(),
            "pair": chosen.pair,
            "direction": "long" if direction == 1 else "short",
            "prediction": float(chosen.prediction),
            "target_return": float(chosen.target),
            "gross_return": float(gross),
            "fee_assumption": 2 * fee_each_side,
            "slippage_assumption": 0.0,
            "net_return_assumed": float(net),
            "equity_after": float(equity),
        }
    )
trades_frame = pd.DataFrame(trades)
trades_frame.to_csv(OUT / "trades.csv", index=False)
metrics["development_test"]["simulation"] = {
    "status": "PASS",
    "trades": len(trades_frame),
    "equity_final": equity,
    "cumulative_net_simple_sum": float(trades_frame.net_return_assumed.sum()) if len(trades_frame) else 0.0,
    "cumulative_gross_simple_sum": float(trades_frame.gross_return.sum()) if len(trades_frame) else 0.0,
    "max_drawdown": float(max_drawdown),
    "pair_counts": trades_frame.pair.value_counts().to_dict() if len(trades_frame) else {},
    "fee_each_side": fee_each_side,
    "slippage_bps": 0.0,
    "funding_cost": "NOT_MODELED",
    "universe": "fixed BTC/ETH/BNB development assumption",
}
(OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))
(OUT / "model_parameters.json").write_text(
    json.dumps(
        {
            "scope": "NON_FORMAL_DEVELOPMENT",
            "model": "Ridge",
            "params": {"alpha": 10.0},
            "seed": 42,
            "feature_columns": list(dataset.X.columns),
            "per_pair_artifacts": model_records,
        },
        ensure_ascii=False,
        indent=2,
    )
)
split = {
    "scope": "NON_FORMAL_DEVELOPMENT",
    "holdout_start_excluded": HOLDOUT_START.isoformat(),
    "global_available_times": len(times),
    "train": {"start": times[0].isoformat(), "end_exclusive": t1.isoformat(), "rows": int(train_mask.sum())},
    "validation": {"start": t1.isoformat(), "end_exclusive": t2.isoformat(), "rows": int(validation_mask.sum())},
    "development_test": {"start": t2.isoformat(), "end": times[-1].isoformat(), "rows": int(test_mask.sum())},
    "same_timestamp_atomic": True,
    "final_holdout_values_read": False,
}
(OUT / "split_manifest.json").write_text(json.dumps(split, ensure_ascii=False, indent=2))
(OUT / "data_quality.json").write_text(
    json.dumps(
        {
            "scope": "NON_FORMAL_DEVELOPMENT",
            "holdout_start_excluded": HOLDOUT_START.isoformat(),
            "pairs": quality,
            "dataset_quality": dataset.quality,
            "exclusion_rows": len(dataset.exclusions),
            "exclusion_reasons": dataset.exclusions.reason.value_counts().to_dict(),
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)
manifest = {
    "scope": "NON_FORMAL_DEVELOPMENT",
    "status": "PASS",
    "label": "raw return horizon=3 diagnostic baseline; production volnorm not changed",
    "model": "Ridge alpha=10",
    "seed": 42,
    "feature_version": "baseline-v2",
    "timeframe": "4h",
    "holdout_start_excluded": HOLDOUT_START.isoformat(),
    "source_files": {pair: {"path": str(path.relative_to(ROOT)), "sha256": file_sha(path)} for pair, path in PAIRS.items()},
    "python": sys.version,
    "platform": platform.platform(),
    "outputs": ["predictions.csv", "trades.csv", "metrics.json", "split_manifest.json", "data_quality.json"],
    "formal_research_status": "BLOCKED",
    "funding_status": "BLOCKED",
    "universe_status": "BLOCKED",
}
(OUT / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
print(json.dumps({"dataset_rows": len(metadata), "predictions": len(predictions), "trades": len(trades_frame), "splits": split, "metrics": metrics}, ensure_ascii=False, default=str))
