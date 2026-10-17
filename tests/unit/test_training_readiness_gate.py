"""Admission rejects forged, failed, missing or non-comparable evidence."""

import json
from dataclasses import asdict

import pandas as pd
import pytest
import yaml

from quant_strategy.config import ExperimentConfig
from quant_strategy.dataset import build_dataset
from quant_strategy.experiments.runner import _dataset_hash
from quant_strategy.infrastructure.experiment_store import canonical_hash, file_hash
from quant_strategy.market_data.contracts import audit_source
from tools.accept_training_readiness import aggregate, evaluate, verify_data_evidence
from tools.accept_training_readiness import test_evidence as verify_test_evidence


@pytest.mark.parametrize("status", ["FAIL", "BLOCKED", "PARTIAL"])
def test_any_unpassed_mandatory_gate_denies_training(status):
    report = aggregate({"1": {"status": "PASS"}, "2": {"status": status}})
    assert report["status"] == status
    assert report["formal_out_of_sample_research_allowed"] is False


def test_p0_failure_dominates_blocked_downstream():
    report = aggregate({"2": {"status": "FAIL"}, "3": {"status": "BLOCKED"}})
    assert report["status"] == "FAIL"
    assert not report["formal_out_of_sample_research_allowed"]


def test_passing_only_one_phase_or_empty_evidence_cannot_authorize_training():
    assert not aggregate({"1": {"status": "PASS"}})["formal_out_of_sample_research_allowed"]
    assert aggregate({})["status"] == "BLOCKED"


def test_engineering_gate_does_not_grant_profitability_or_live_admission():
    report = aggregate({str(i): {"status": "PASS"} for i in range(1, 7)})
    assert report["formal_out_of_sample_research_allowed"]
    assert report["model_effectiveness"] == report["live_trading_admission"] == "BLOCKED"


def test_receipt_requires_actual_nonempty_junit_and_zero_exit(tmp_path):
    junit = tmp_path / "tests.xml"
    receipt = tmp_path / "test_run.json"
    junit.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="actual_test"/></testsuite></testsuites>'
    )
    value = {
        "junit": junit.name,
        "junit_sha256": file_hash(junit),
        "exit_code": 0,
        "command": ["python", "-m", "pytest"],
    }
    receipt.write_text(json.dumps(value))
    assert verify_test_evidence(receipt)["executed_test_names"] == ["actual_test"]
    receipt.write_text(json.dumps({**value, "exit_code": 1}))
    with pytest.raises(ValueError, match="failed"):
        verify_test_evidence(receipt)
    receipt.write_text(json.dumps(value))
    junit.write_text(junit.read_text().replace('tests="1"', 'tests="0"'))
    with pytest.raises(ValueError, match="fingerprint"):
        verify_test_evidence(receipt)


def test_skipped_case_is_not_executed_gate_evidence(tmp_path):
    junit = tmp_path / "tests.xml"
    junit.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="1"><testcase name="required_test"><skipped/></testcase></testsuite></testsuites>'
    )
    receipt = tmp_path / "run.json"
    receipt.write_text(
        json.dumps(
            {
                "junit": junit.name,
                "junit_sha256": file_hash(junit),
                "exit_code": 0,
                "command": ["pytest"],
            }
        )
    )
    report = verify_test_evidence(receipt)
    assert report["skipped"] == 1
    assert "required_test" not in report["executed_test_names"]


def test_failed_junit_cannot_be_relabelled_by_exit_code(tmp_path):
    junit = tmp_path / "tests.xml"
    junit.write_text(
        '<testsuites><testsuite tests="1" failures="1" errors="0" skipped="0"><testcase name="x"><failure/></testcase></testsuite></testsuites>'
    )
    receipt = tmp_path / "run.json"
    receipt.write_text(
        json.dumps(
            {
                "junit": junit.name,
                "junit_sha256": file_hash(junit),
                "exit_code": 0,
                "command": ["pytest"],
            }
        )
    )
    with pytest.raises(ValueError, match="failed"):
        verify_test_evidence(receipt)


@pytest.fixture
def data_evidence(tmp_path, candles):
    raw = tmp_path / "raw.feather"
    candles.to_feather(raw)
    config = ExperimentConfig(data={"BTC": str(raw)})
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"research": asdict(config)}))
    dataset = build_dataset({"BTC": candles}, config)
    dataset.metadata.to_parquet(tmp_path / "sample_metadata.parquet", index=False)
    dataset.exclusions.to_parquet(tmp_path / "sample_exclusions.parquet", index=False)
    source = audit_source(candles, kind="futures", timeframe="4h")
    source.update(
        path=str(raw), file_sha256=file_hash(raw), formal_use="eligible_if_window_verified"
    )
    (tmp_path / "source_audit.json").write_text(json.dumps([source]))
    report = {
        "phase": 1,
        "status": "PASS",
        "sources_by_status": {"PASS": 1},
        "config_inputs": [{"path": str(config_path), "sha256": file_hash(config_path)}],
        "config_sha256": canonical_hash(asdict(config)),
        "input_files": {"BTC": {"path": str(raw), "sha256": file_hash(raw)}},
        "dataset_sha256": _dataset_hash(dataset),
        "samples": len(dataset.X),
        "availability_scope": "unit fixture",
    }
    report["artifacts"] = {p.name: file_hash(p) for p in tmp_path.iterdir() if p.is_file()}
    (tmp_path / "phase1_data.json").write_text(json.dumps(report))
    return tmp_path


def test_independent_data_gate_rebuilds_instead_of_trusting_pass_string(data_evidence):
    assert verify_data_evidence(data_evidence)["status"] == "PASS"
    path = data_evidence / "phase1_data.json"
    report = json.loads(path.read_text())
    report["dataset_sha256"] = "0" * 64
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="not reproducible"):
        verify_data_evidence(data_evidence)


def test_independent_gate_rejects_changed_source_even_with_original_report(data_evidence):
    path = data_evidence / "raw.feather"
    frame = pd.read_feather(path)
    frame.loc[0, "volume"] += 1
    frame.to_feather(path)
    with pytest.raises(ValueError, match="fingerprint|changed"):
        verify_data_evidence(data_evidence)


def test_independent_gate_rejects_exclusion_or_sample_artifact_tamper(data_evidence):
    path = data_evidence / "sample_exclusions.parquet"
    excluded = pd.read_parquet(path)
    excluded["reason"] = "hidden"
    excluded.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="fingerprint"):
        verify_data_evidence(data_evidence)


def test_missing_real_evidence_is_blocked_not_invented_pass_or_test_failure(tmp_path):
    report = evaluate(tmp_path / "missing", tmp_path / "no-test-run.json", tmp_path / "output")
    assert report["status"] == "BLOCKED"
    assert report["phases"]["6"]["independent_aggregation_executed"]
    assert not report["formal_out_of_sample_research_allowed"]
