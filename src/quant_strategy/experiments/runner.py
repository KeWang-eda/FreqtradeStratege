"""Research orchestration; never places orders or changes production defaults."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import uuid4

import pandas as pd
import yaml

from quant_strategy.config import ExperimentConfig
from quant_strategy.dataset import Dataset, build_dataset
from quant_strategy.errors import DataContractError, UnsupportedCapabilityError
from quant_strategy.infrastructure.experiment_store import (
    canonical_hash,
    create_experiment_directory,
    environment_versions,
    file_hash,
    git_state,
    snapshot_source,
    write_json,
)
from quant_strategy.infrastructure.model_store import save_model
from quant_strategy.market_data import load_ohlcv
from quant_strategy.market_data.contracts import frame_fingerprint
from quant_strategy.training import StandaloneBackend, TrainingRequest
from quant_strategy.validation import TimeSeriesSplitter, prediction_metrics


def _dataset_hash(dataset: Dataset) -> str:
    digest = hashlib.sha256()
    for frame in (dataset.X, dataset.y.to_frame(), dataset.metadata):
        digest.update(frame_fingerprint(frame).encode())
    return digest.hexdigest()


def _fold_manifest(fold: object) -> dict:
    result = asdict(fold)
    for key in ("train_indices", "test_indices", "purged_indices", "embargoed_indices"):
        result[key] = result[key].tolist()
    return result


def run_experiment(
    config: ExperimentConfig,
    output_root: str | Path,
    *,
    frames: Mapping[str, pd.DataFrame] | None = None,
    experiment_id: str | None = None,
    evaluate_final_holdout: bool = False,
) -> Path:
    """Run per-pair time-series research and save complete auditable artifacts.

    The final time block is reserved and unscored unless explicitly requested.
    A failed experiment retains a failed manifest and its exception details.
    """
    if config.model.backend != "standalone":
        raise UnsupportedCapabilityError(
            "CLI research folds require standalone; run FreqAI via freqtrade backtesting"
        )
    experiment_id = experiment_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
    output = create_experiment_directory(output_root, experiment_id)
    resolved = asdict(config)
    manifest = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "name": config.name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "backend": config.model.backend,
        "model": asdict(config.model),
        "label": asdict(config.label),
        "feature_version": config.feature_version,
        "seed": config.seed,
        "config_sha256": canonical_hash(resolved),
        "git": git_state(),
        "environment": environment_versions(),
        "final_holdout_evaluated": evaluate_final_holdout,
    }
    write_json(output / "manifest.json", manifest)
    (output / "config.resolved.yaml").write_text(
        yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8"
    )
    try:
        manifest["source_files_sha256"] = snapshot_source(output / "source.tar.gz")
        if frames is None:
            frames = {pair: load_ohlcv(path) for pair, path in config.data.items()}
            manifest["input_files"] = {
                pair: {"path": path, "sha256": file_hash(path)}
                for pair, path in config.data.items()
            }
            if any(
                frame.attrs.get("source_sha256") != manifest["input_files"][pair]["sha256"]
                for pair, frame in frames.items()
            ):
                raise DataContractError("Input changed between loading and recording provenance")
        dataset = build_dataset(frames, config)
        raw_hash = hashlib.sha256()
        for pair, frame in sorted(frames.items()):
            raw_hash.update(pair.encode())
            raw_hash.update(
                pd.util.hash_pandas_object(
                    frame[["date", "open", "high", "low", "close", "volume"]], index=False
                ).values.tobytes()
            )
        manifest["input_data_sha256"] = raw_hash.hexdigest()
        manifest["dataset_sha256"] = _dataset_hash(dataset)
        dataset.exclusions.to_parquet(output / "sample_exclusions.parquet", index=False)
        manifest["data"] = {
            "pairs": sorted(frames),
            "timeframe": config.timeframe,
            "start": str(dataset.metadata["candle_timestamp"].min()),
            "end": str(dataset.metadata["candle_timestamp"].max()),
            "quality": dataset.quality,
        }
        write_json(
            output / "feature_schema.json",
            {
                "version": config.feature_version,
                "columns": list(dataset.X),
                "dtypes": [str(dtype) for dtype in dataset.X.dtypes],
                "label_version": "close-return-atr-v1",
                "time_semantics": "UTC candle open; features available at close",
            },
        )
        times = pd.DatetimeIndex(dataset.metadata["available_at"])
        unique = times.unique()
        cut = int(len(unique) * (1 - config.validation.final_holdout_fraction))
        if cut < 2 or cut >= len(unique):
            raise DataContractError("Insufficient timestamps for independent final holdout")
        holdout_start = unique[cut]
        keep = (times < holdout_start) & (
            dataset.metadata["label_end_time"] < holdout_start
        ).to_numpy()
        development = Dataset(
            dataset.X.loc[keep].reset_index(drop=True),
            dataset.y.loc[keep].reset_index(drop=True),
            dataset.metadata.loc[keep].reset_index(drop=True),
            dataset.quality,
        )
        manifest["final_holdout"] = {
            "start": str(holdout_start),
            "end": str(unique[-1]),
            "reserved_samples": int((times >= holdout_start).sum()),
            "development_boundary_purged": int(((times < holdout_start) & ~keep).sum()),
            "evaluated": evaluate_final_holdout,
        }
        dev_folds = TimeSeriesSplitter(config.validation).split(
            pd.DatetimeIndex(development.metadata["available_at"]),
            development.metadata["label_end_time"],
        )
        jobs = [(development, fold, "development") for fold in dev_folds]
        if evaluate_final_holdout:
            holdout_config = replace(
                config.validation,
                method="fixed_holdout",
                n_splits=1,
                test_size=config.validation.final_holdout_fraction,
            )
            final_fold = TimeSeriesSplitter(holdout_config).split(
                times, dataset.metadata["label_end_time"]
            )[0]
            jobs.append((dataset, replace(final_fold, fold_id="final"), "final_holdout"))
        frames_out, metrics, audits, folds_out = [], {}, [], []
        backend = StandaloneBackend()
        for current_dataset, fold, phase in jobs:
            result = backend.run_training(
                TrainingRequest(current_dataset, fold, config, experiment_id)
            )
            table = result.predictions.to_frame()
            table["truth"] = result.truth
            table["fold_id"], table["phase"] = fold.fold_id, phase
            frames_out.append(table)
            metrics[fold.fold_id] = {
                "phase": phase,
                "overall": prediction_metrics(table["truth"], table["prediction"]),
                "pairs": {
                    pair: prediction_metrics(group["truth"], group["prediction"])
                    for pair, group in table.groupby("pair")
                },
            }
            audits.extend(result.audit)
            folds_out.append(
                {
                    "phase": phase,
                    "index_space": "full_dataset"
                    if phase == "final_holdout"
                    else "development_dataset",
                    **_fold_manifest(fold),
                }
            )
            for pair, (preprocessor, model) in result.models.items():
                pair_slug = hashlib.sha256(pair.encode()).hexdigest()[:16]
                records = [record for record in result.predictions.records if record.pair == pair]
                save_model(
                    output / "model" / fold.fold_id / pair_slug,
                    preprocessor,
                    model,
                    config,
                    records[0].training_data_end,
                    records[0].model_version,
                )
        predictions = pd.concat(frames_out, ignore_index=True)
        predictions.to_parquet(output / "predictions.parquet", index=False)
        dataset.metadata.to_parquet(output / "dataset_metadata.parquet", index=False)
        development.metadata.to_parquet(output / "development_metadata.parquet", index=False)
        write_json(output / "folds.json", folds_out)
        manifest["folds_sha256"] = canonical_hash(folds_out)
        write_json(output / "metrics_prediction.json", metrics)
        write_json(
            output / "metrics_backtest.json",
            {
                "status": "not_run",
                "reason": "Trading evaluation belongs to Freqtrade; prediction metrics are not trading returns",
            },
        )
        write_json(
            output / "leakage_report.json",
            {
                "passed": all(event["passed"] for event in audits),
                "fold_audits": audits,
                "scope": "label interval purge, training cutoff, fold-local preprocessing",
                "additional_checks": "Run pytest tests/leakage and Freqtrade truncation audit separately",
            },
        )
        manifest["status"] = "complete"
        manifest["artifact_checksums"] = {
            str(path.relative_to(output)): file_hash(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and path != output / "manifest.json"
        }
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "manifest.json", manifest)
    return output


def compare_experiments(paths: list[str | Path]) -> list[dict]:
    """Compare metrics without choosing or deploying a production winner."""
    results = []
    for path in paths:
        path = Path(path)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        metrics = json.loads((path / "metrics_prediction.json").read_text(encoding="utf-8"))
        results.append(
            {
                "experiment_id": manifest["experiment_id"],
                "config_sha256": manifest["config_sha256"],
                "dataset_sha256": manifest["dataset_sha256"],
                "input_data_sha256": manifest.get("input_data_sha256"),
                "folds_sha256": manifest.get("folds_sha256"),
                "folds": metrics,
            }
        )
    return results
