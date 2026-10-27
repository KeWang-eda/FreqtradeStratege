"""Independently recompute native training identities, boundaries and fit lineage.

Reads real run artifacts rather than a trainer's PASS string. Locally generated
pickle pipelines/models are trusted executable artifacts; do not use this tool
to load untrusted third-party pickles. No market client or downloader is created.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
try:
    import cloudpickle
except ImportError:  # pragma: no cover - compatibility with older joblib-only environments
    from joblib.externals import cloudpickle

from quant.infrastructure.experiment_store import environment_versions, file_hash
from quant.market_data.contracts import frame_fingerprint
from quant.market_data.time_index import timeframe_delta
from quant.validation.admission import current_source_hashes
from quant.validation.native_features import populate_native_features


def _table_equal(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)


def verify_native_training_acceptance(run_directory: Path, output: Path | None = None) -> dict:
    """Verify only engineering correctness; funding/OOS admission stays separate."""
    report = {"schema_version": 1, "status": "FAIL", "scope": "development", "pairs": []}
    try:
        run = json.loads((run_directory / "training_run.json").read_text())
        if run.get("scope") != "development" or run.get("status") != "PASS" or not run.get("pairs"):
            raise ValueError("No completed real development training lifecycle")
        report["run_id"] = run["run_id"]
        if run.get("source_files_sha256") != current_source_hashes():
            raise ValueError("Training code or tests differ from the actual run")
        if run.get("environment") != environment_versions():
            raise ValueError("Software environment differs from actual training")
        for name, digest in run["artifacts"].items():
            path = (run_directory / name).resolve()
            if not path.is_relative_to(run_directory.resolve()) or file_hash(path) != digest:
                raise ValueError("Real training artifact missing or changed")
        for item in run["input_files"].values():
            if file_hash(item["path"]) != item["sha256"]:
                raise ValueError("Raw input changed after actual training")
        if file_hash(run["config_file"]["path"]) != run["config_file"]["sha256"]:
            raise ValueError("Production configuration changed after training")
        config = json.loads(Path(run["config_file"]["path"]).read_text())
        network = json.loads((run_directory / "network.json").read_text())
        if not network.get("completed") or network.get("denied_operations") != 0:
            raise ValueError("Network audit did not complete cleanly")
        for pair in run["pairs"]:
            directory = run_directory / pair["audit_directory"]
            audit = json.loads((directory / "audit.json").read_text())
            if audit.get("status") != "PASS" or audit.get("phase") != "trained":
                raise ValueError("Incomplete per-training lifecycle")
            if (
                audit.get("timeframe") != config["timeframe"]
                or audit.get("label_horizon")
                != config["freqai"]["feature_parameters"]["label_period_candles"]
                or audit.get("label_mode") != config.get("my_experiment", {}).get("label", "raw")
            ):
                raise ValueError(
                    "Audit label/timeframe contract differs from production configuration"
                )
            for name, digest in audit["artifacts"].items():
                if file_hash(directory / name) != digest:
                    raise ValueError("Per-training audit artifact changed")
            raw = pd.read_parquet(directory / "input.parquet")
            samples = pd.read_parquet(directory / "samples.parquet")
            if not raw.index.equals(samples.index) or not raw.index.is_unique or raw.empty:
                raise ValueError("Raw X/y/time metadata index alignment violated")
            if samples.sample_id.duplicated().any() or not (samples.pair == pair["pair"]).all():
                raise ValueError("Sample identity duplicated or assigned to another pair")
            if list(pair["features"]) != list(audit["feature_schema"]):
                raise ValueError("Incomplete production feature schema")
            if frame_fingerprint(raw) != audit["input_fingerprint"]:
                raise ValueError("Actual populated input fingerprint mismatch")
            step = timeframe_delta(audit["timeframe"])
            horizon = audit["label_horizon"]
            dates = raw.date
            if not dates.equals(samples.candle_timestamp) or not (dates + step).equals(
                samples.available_at
            ):
                raise ValueError("Source time metadata differs from real candles")
            expected_end = dates.shift(-horizon) + step
            if not expected_end.equals(samples.label_end_time):
                raise ValueError("Label completion time was altered")
            identities = [
                hashlib.sha256(f"{pair['pair']}|{date.isoformat()}".encode()).hexdigest()
                for date in dates
            ]
            if samples.sample_id.tolist() != identities:
                raise ValueError("Sample IDs do not map to actual pair and timestamp")
            features, labels = audit["feature_schema"], audit["label_schema"]
            train_start = pd.Timestamp(pair["training_start"])
            train_end = pd.Timestamp(pair["training_end_exclusive"])
            source_prefixes = {}
            for source_pair, source_item in run["input_files"].items():
                source_frame = pd.read_feather(source_item["path"])
                source_prefixes[source_pair] = source_frame.loc[
                    (source_frame.date >= train_start - 100 * step)
                    & (source_frame.date < train_end)
                ].copy()
            rebuilt = populate_native_features(config, source_prefixes, pair["pair"])
            if features != [c for c in rebuilt if c.startswith("%")]:
                raise ValueError("Incomplete independently rebuilt production feature schema")
            if labels != [c for c in rebuilt if c.startswith("&")]:
                raise ValueError("Incomplete independently rebuilt production label schema")
            rebuilt = rebuilt.loc[rebuilt.date >= train_start, ["date", *features, *labels]]
            _table_equal(raw, rebuilt)
            eligible = np.isfinite(raw[features + labels].to_numpy(dtype=float)).all(axis=1)
            observed = samples.original_split.isin(["train", "validation"]).to_numpy()
            if not np.array_equal(eligible, observed):
                raise ValueError("Filtered eligibility differs from actual features and labels")
            n = int(eligible.sum())
            split_size = config["freqai"]["data_split_parameters"]["test_size"]
            n_valid = int(np.ceil(n * split_size)) if isinstance(split_size, float) else split_size
            original_assignments = samples.original_split.loc[eligible].tolist()
            if original_assignments != ["train"] * (n - n_valid) + ["validation"] * n_valid:
                raise ValueError("Original validation boundary was silently changed")
            factor = config["freqai"]["feature_parameters"].get("weight_factor", 0)
            expected_weights = (
                np.exp(-np.arange(n) / (factor * n))[::-1] if factor > 0 else np.ones(n)
            )
            if not np.array_equal(samples.loc[eligible, "weight"].to_numpy(), expected_weights):
                raise ValueError("Sample weights differ from their actual temporal identity")
            train = samples.loc[samples.assignment == "train"]
            valid = samples.loc[samples.assignment == "validation"]
            purged = samples.loc[samples.assignment == "purged"]
            if train.empty or valid.empty or set(train.sample_id) & set(valid.sample_id):
                raise ValueError("Training/validation identities overlap or are empty")
            original_validation = samples.loc[samples.original_split == "validation"]
            if not valid.index.equals(original_validation.index):
                raise ValueError("Final validation membership differs from original split")
            boundary = original_validation.available_at.min()
            if not samples.validation_start.eq(boundary).all():
                raise ValueError("Recorded validation_start differs from original split")
            original_train = samples.loc[samples.original_split == "train"]
            expected_purged = original_train.index[original_train.label_end_time >= boundary]
            if not purged.index.equals(expected_purged):
                raise ValueError("Purge did not enforce label_end >= validation_start")
            expected_train = original_train.index[original_train.label_end_time < boundary]
            if not train.index.equals(expected_train):
                raise ValueError(
                    "Final training membership differs from original split minus purge"
                )
            if not samples.loc[~eligible, "assignment"].eq("filtered").all():
                raise ValueError("Ineligible rows were not explicitly filtered")
            if not (train.label_end_time < boundary).all():
                raise ValueError("Retained training label violates strict validation boundary")
            if not purged.reason.eq("label_end_ge_validation_start").all():
                raise ValueError("Purged samples lack an explicit exclusion reason")
            fitted = audit["preprocessor_fit"]
            for name in ("feature_pipeline", "label_pipeline"):
                if fitted[name]["sample_ids"] != train.sample_id.tolist():
                    raise ValueError("Purged/validation samples entered a preprocessor fit")
                if fitted[name]["source_indices"] != train.index.map(str).tolist():
                    raise ValueError("Preprocessor time index lineage mismatch")
            if audit["label_statistics_fit_sample_ids"] != train.sample_id.tolist():
                raise ValueError("Label statistics used validation or purged samples")
            for split, metadata in (("train", train), ("test", valid)):
                before = pd.read_parquet(directory / f"{split}_before_preprocessing.parquet")
                _table_equal(before[features + labels], raw.loc[metadata.index, features + labels])
                if not before.index.equals(metadata.index) or not np.array_equal(
                    before.sample_weight.to_numpy(), metadata.weight.to_numpy()
                ):
                    raise ValueError("X/y/weights/time indices are misaligned")
            # Real serialized fitted pipelines are independently refit on the
            # retained raw rows. Exact transformed values must match the run.
            model_dir = run_directory / pair["model_directory"]
            pipeline_path = next(model_dir.glob("*_feature_pipeline.pkl"))
            labels_path = next(model_dir.glob("*_label_pipeline.pkl"))
            with pipeline_path.open("rb") as stream:
                saved_pipeline = cloudpickle.load(stream)
                pipeline = copy.deepcopy(saved_pipeline)
            with labels_path.open("rb") as stream:
                saved_label_pipeline = cloudpickle.load(stream)
                label_pipeline = copy.deepcopy(saved_label_pipeline)
            before = pd.read_parquet(directory / "train_before_preprocessing.parquet")
            X, y, weights = pipeline.fit_transform(
                before[features], before[labels], before.sample_weight.to_numpy()
            )
            y, _, _ = label_pipeline.fit_transform(y)
            replay = X.join(y).assign(sample_weight=weights)
            after = pd.read_parquet(directory / "train_after_preprocessing.parquet")
            _table_equal(replay, after)
            before = pd.read_parquet(directory / "test_before_preprocessing.parquet")
            X, y, weights = pipeline.transform(
                before[features], before[labels], before.sample_weight.to_numpy()
            )
            y, _, _ = label_pipeline.transform(y)
            _table_equal(
                X.join(y).assign(sample_weight=weights),
                pd.read_parquet(directory / "test_after_preprocessing.parquet"),
            )
            predictions = pd.read_parquet(model_dir / "development_predictions.parquet")
            if (
                len(predictions) != pair["prediction_rows"]
                or not np.isfinite(predictions[labels]).all().all()
            ):
                raise ValueError("Missing/nonfinite real predictions")
            if not (predictions.date >= pd.Timestamp(pair["training_end_exclusive"])).all():
                raise ValueError("Development prediction time overlaps model training")
            prediction_input = pd.read_parquet(model_dir / "populated_prediction.parquet")
            if not np.isfinite(prediction_input[features].to_numpy()).all():
                raise ValueError("Development prediction source has unquarantined missing features")
            with next(model_dir.glob("*_model.joblib")).open("rb") as stream:
                saved_model = cloudpickle.load(stream)
            transformed, ready, _ = saved_pipeline.transform(
                prediction_input[features], outlier_check=True
            )
            replay_values = saved_model.predict(transformed).reshape(-1, len(labels))
            replay, _, _ = saved_label_pipeline.inverse_transform(
                pd.DataFrame(replay_values, columns=labels)
            )
            if not np.array_equal(
                replay.to_numpy(), predictions[labels].to_numpy()
            ) or not np.array_equal(ready, predictions.do_predict.to_numpy()):
                raise ValueError(
                    "Saved model/pipelines do not reproduce actual predictions exactly"
                )
            report["pairs"].append(
                {
                    "pair": pair["pair"],
                    "train_samples": len(train),
                    "validation_samples": len(valid),
                    "purged": len(purged),
                    "feature_columns": features,
                    "label_boundary_violations": 0,
                    "identity_overlap": 0,
                    "alignment_violations": 0,
                    "purged_entered_preprocessor_fit": 0,
                    "independent_preprocessing_refit_exact": True,
                    "saved_model_prediction_replay_exact": True,
                    "native_features_labels_rebuilt_from_raw": True,
                    "prediction_rows": len(predictions),
                    "validation_start": boundary.isoformat(),
                }
            )
        report.update(
            status="PASS",
            code_correctness="PASS",
            counts={
                key: 0
                for key in (
                    "label_boundary_violations",
                    "identity_overlap",
                    "alignment_violations",
                    "purged_entered_preprocessor_fit",
                )
            },
            funding={
                "status": "BLOCKED",
                "reason": "Authoritative historical payment schedules remain unverified",
            },
            formal_out_of_sample_research_allowed=False,
        )
    except (OSError, ValueError, KeyError, TypeError, AssertionError, StopIteration) as error:
        report.update(
            status="FAIL",
            code_correctness="FAIL",
            error={"type": type(error).__name__, "message": str(error)},
        )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            json.dump(report, stream, indent=2, default=str)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = verify_native_training_acceptance(args.run, args.output)
    print(json.dumps({"status": report["status"], "pairs": len(report["pairs"])}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
