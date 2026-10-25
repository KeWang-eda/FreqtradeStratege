"""Independent verifier rejects rehashed corruption of actual FreqAI artifacts."""

import json
import os
import shutil
import subprocess
import sys

import pandas as pd
import pytest

from quant_strategy.infrastructure.experiment_store import file_hash
from tools.verify_native_training_acceptance import verify_native_training_acceptance


@pytest.fixture(scope="module")
def actual_native_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("real-native-probe") / "native_training"
    result = subprocess.run(
        [
            sys.executable,
            "tools/run_native_training_probe.py",
            "--end",
            "2022-01-01T00:00:00+00:00",
            "--output",
            str(root),
            "--pairs",
            "BTC/USDT:USDT",
        ],
        env={**os.environ, "PYTHONPATH": "src:."},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    base = verify_native_training_acceptance(root)
    assert base["status"] == "PASS", json.dumps(base, default=str)
    # Keep the genuine independent verification already performed by setup as
    # an immutable JSON value.  The positive test need not repeat that full
    # verification; every mutated-copy test below still reruns the verifier.
    original_hashes = tuple(
        sorted(
            (path.relative_to(root).as_posix(), file_hash(path))
            for path in root.rglob("*")
            if path.is_file()
        )
    )
    return root, json.dumps(base, sort_keys=True), original_hashes


def _original_native_run(actual_native_run):
    """Require the complete original tree to stay unchanged before reuse."""
    root, verified_json, original_hashes = actual_native_run
    current_hashes = tuple(
        sorted(
            (path.relative_to(root).as_posix(), file_hash(path))
            for path in root.rglob("*")
            if path.is_file()
        )
    )
    assert current_hashes == original_hashes, "Shared original native artifacts changed"
    return root, json.loads(verified_json)


def _rehash(root):
    run_file = root / "training_run.json"
    run = json.loads(run_file.read_text())
    for pair in run["pairs"]:
        directory = root / pair["audit_directory"]
        audit_path = directory / "audit.json"
        audit = json.loads(audit_path.read_text())
        audit["artifacts"] = {name: file_hash(directory / name) for name in audit["artifacts"]}
        audit_path.write_text(json.dumps(audit))
    run["artifacts"] = {name: file_hash(root / name) for name in run["artifacts"]}
    run_file.write_text(json.dumps(run))


def test_real_native_training_has_independently_recomputed_safe_boundaries(actual_native_run):
    _, report = _original_native_run(actual_native_run)
    assert report["status"] == "PASS", json.dumps(report, default=str)
    assert report["pairs"][0]["purged"] == 3
    assert report["pairs"][0]["independent_preprocessing_refit_exact"]
    assert report["funding"]["status"] == "BLOCKED"
    assert report["formal_out_of_sample_research_allowed"] is False


@pytest.mark.parametrize(
    "fault", ["boundary", "xy", "weight", "fit_ids", "schema", "prediction", "timestamp"]
)
def test_independent_verifier_rejects_self_consistently_rehashed_faults(
    actual_native_run, tmp_path, fault
):
    root = tmp_path / "damaged"
    original, _ = _original_native_run(actual_native_run)
    shutil.copytree(original, root)
    run = json.loads((root / "training_run.json").read_text())
    directory = root / run["pairs"][0]["audit_directory"]
    if fault in {"boundary", "timestamp"}:
        path = directory / "samples.parquet"
        frame = pd.read_parquet(path)
        if fault == "boundary":
            index = frame.index[frame.assignment == "purged"][0]
            frame.loc[index, "assignment"] = "train"
        else:
            index = frame.index[frame.assignment == "train"][0]
            frame.loc[index, "label_end_time"] += pd.Timedelta(hours=4)
        frame.to_parquet(path)
    elif fault in {"xy", "weight"}:
        path = directory / "train_before_preprocessing.parquet"
        frame = pd.read_parquet(path)
        if fault == "xy":
            column = next(c for c in frame if c.startswith("&"))
            frame[column] = frame[column].shift(-1).fillna(0)
        else:
            frame.iloc[0, frame.columns.get_loc("sample_weight")] += 0.1
        frame.to_parquet(path)
    elif fault == "fit_ids":
        path = directory / "audit.json"
        audit = json.loads(path.read_text())
        audit["preprocessor_fit"]["feature_pipeline"]["sample_ids"].append("purged-id")
        path.write_text(json.dumps(audit))
    elif fault == "schema":
        run["pairs"][0]["features"].pop()
        (root / "training_run.json").write_text(json.dumps(run))
    else:
        path = root / run["pairs"][0]["model_directory"] / "development_predictions.parquet"
        frame = pd.read_parquet(path)
        frame.iloc[0, frame.columns.get_loc("&-s_return")] = float("nan")
        frame.to_parquet(path)
    _rehash(root)
    report = verify_native_training_acceptance(root)
    assert report["status"] == "FAIL", (fault, report)
    expected = {
        "boundary": "Purge did not enforce",
        "xy": "DataFrame.iloc",
        "weight": "misaligned",
        "fit_ids": "entered a preprocessor fit",
        "schema": "Incomplete production feature schema",
        "prediction": "Missing/nonfinite real predictions",
        "timestamp": "Label completion time",
    }
    assert expected[fault] in report["error"]["message"], (fault, report)


@pytest.mark.parametrize(
    "fault",
    [
        "moved_validation",
        "audit_timeframe",
        "audit_horizon",
        "incomplete_phase",
        "recorded_boundary",
        "missing_safe_train",
        "agreed_schema_subset",
    ],
)
def test_independent_verifier_binds_audit_to_original_split_and_configuration(
    actual_native_run, tmp_path, fault
):
    root = tmp_path / "damaged"
    original, _ = _original_native_run(actual_native_run)
    shutil.copytree(original, root)
    run = json.loads((root / "training_run.json").read_text())
    directory = root / run["pairs"][0]["audit_directory"]
    audit_path = directory / "audit.json"
    audit = json.loads(audit_path.read_text())
    if fault == "moved_validation":
        path = directory / "samples.parquet"
        samples = pd.read_parquet(path)
        first_validation = samples.index[samples.assignment == "validation"][0]
        first_purged = samples.index[samples.assignment == "purged"][0]
        samples.loc[[first_validation, first_purged], "assignment"] = "filtered"
        samples.to_parquet(path)
        for name in ("test_before_preprocessing.parquet", "test_after_preprocessing.parquet"):
            path = directory / name
            frame = pd.read_parquet(path)
            frame.drop(first_validation, errors="ignore").to_parquet(path)
    elif fault in {"audit_timeframe", "audit_horizon"}:
        audit["timeframe" if fault == "audit_timeframe" else "label_horizon"] = (
            "8h" if fault == "audit_timeframe" else 4
        )
        audit_path.write_text(json.dumps(audit))
    elif fault in {"recorded_boundary", "missing_safe_train"}:
        path = directory / "samples.parquet"
        samples = pd.read_parquet(path)
        if fault == "recorded_boundary":
            samples["validation_start"] += pd.Timedelta(hours=4)
        else:
            samples.loc[samples.index[samples.assignment == "train"][0], "assignment"] = "filtered"
        samples.to_parquet(path)
    elif fault == "agreed_schema_subset":
        removed = audit["feature_schema"].pop()
        run["pairs"][0]["features"].pop()
        (root / "training_run.json").write_text(json.dumps(run))
        path = directory / "input.parquet"
        raw = pd.read_parquet(path).drop(columns=[removed])
        raw.to_parquet(path)
        from quant_strategy.market_data.contracts import frame_fingerprint

        audit["input_fingerprint"] = frame_fingerprint(raw)
        audit_path.write_text(json.dumps(audit))
    else:
        audit["phase"] = "before_preprocessing"
        audit_path.write_text(json.dumps(audit))
    _rehash(root)
    report = verify_native_training_acceptance(root)
    assert report["status"] == "FAIL", (fault, report)
    expected = {
        "moved_validation": "Final validation membership differs from original split",
        "audit_timeframe": "Audit label/timeframe contract differs from production configuration",
        "audit_horizon": "Audit label/timeframe contract differs from production configuration",
        "incomplete_phase": "Incomplete per-training lifecycle",
        "recorded_boundary": "Recorded validation_start differs from original split",
        "missing_safe_train": "Final training membership differs from original split minus purge",
        "agreed_schema_subset": "Incomplete independently rebuilt production feature schema",
    }
    assert expected[fault] in report["error"]["message"], (fault, report)
