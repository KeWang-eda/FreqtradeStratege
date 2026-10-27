"""Admission rejects forged, failed, missing or non-comparable evidence."""

import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict

import pandas as pd
import pytest
import yaml

from quant.config import ExperimentConfig
from quant.dataset import build_dataset
from quant.experiments.runner import _dataset_hash
from quant.infrastructure.experiment_store import canonical_hash, file_hash
from quant.market_data.contracts import audit_source
from quant.validation.admission import (
    diagnose_legacy_test_execution,
    new_receipt_context,
    verify_test_execution,
)
from tools.accept_training_readiness import (
    _native_feature_scope_status,
    aggregate,
    evaluate,
    verify_data_evidence,
)
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
    assert not report["formal_out_of_sample_research_allowed"]
    assert report["implemented_formal_gate_validators"] == ["1", "2"]
    assert report["status"] == "BLOCKED"
    assert report["model_effectiveness"] == report["live_trading_admission"] == "BLOCKED"


def test_receipt_requires_actual_nonempty_junit_and_zero_exit(tmp_path):
    junit = tmp_path / "tests.xml"
    receipt = tmp_path / "test_run.json"
    junit.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="actual_test"/></testsuite></testsuites>'
    )
    value = {
        **new_receipt_context("unit-test-receipt"),
        "junit": junit.name,
        "junit_sha256": file_hash(junit),
        "exit_code": 0,
        "command": ["python", "-m", "pytest"],
    }
    receipt.write_text(json.dumps(value))
    diagnostic = diagnose_legacy_test_execution(receipt)
    assert diagnostic["executed_test_names"] == ["actual_test"]
    assert diagnostic["diagnostic_only"] is True
    assert diagnostic["engineering_status"] == "PARTIAL"
    assert diagnostic["formal_research_allowed"] is False
    with pytest.raises(ValueError, match="runner receipt version 3"):
        verify_test_evidence(receipt)
    with pytest.raises(ValueError, match="runner receipt version 3"):
        verify_test_execution(receipt)
    with pytest.raises(ValueError, match="explicit diagnose_legacy_test_execution"):
        verify_test_execution(receipt, require_runner_receipt=False)
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
                **new_receipt_context("unit-skipped-receipt"),
                "junit": junit.name,
                "junit_sha256": file_hash(junit),
                "exit_code": 0,
                "command": ["pytest"],
            }
        )
    )
    report = diagnose_legacy_test_execution(receipt)
    assert report["skipped"] == 1
    assert "required_test" not in report["executed_test_names"]
    assert report["diagnostic_only"] and not report["formal_research_allowed"]
    with pytest.raises(ValueError, match="runner receipt version 3"):
        verify_test_evidence(receipt)


def test_failed_junit_cannot_be_relabelled_by_exit_code(tmp_path):
    junit = tmp_path / "tests.xml"
    junit.write_text(
        '<testsuites><testsuite tests="1" failures="1" errors="0" skipped="0"><testcase name="x"><failure/></testcase></testsuite></testsuites>'
    )
    receipt = tmp_path / "run.json"
    receipt.write_text(
        json.dumps(
            {
                **new_receipt_context("unit-failed-receipt"),
                "junit": junit.name,
                "junit_sha256": file_hash(junit),
                "exit_code": 0,
                "command": ["pytest"],
            }
        )
    )
    with pytest.raises(ValueError, match="failed"):
        verify_test_evidence(receipt)


@pytest.fixture(scope="module")
def genuine_readiness_receipt(tmp_path_factory):
    """Execute one real, model-free pytest node through the unmodified v3 runner."""
    output = tmp_path_factory.mktemp("readiness-v3") / "run"
    target = (
        "tests/unit/test_config_labels_features.py::test_metrics_empty_constant_and_known_values"
    )
    command = [
        sys.executable,
        "tools/run_tests.py",
        "ci",
        "--output",
        str(output),
        "--",
        target,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((output / "test_run.json").read_text())
    assert receipt["selected_nodeids"] == [target]
    assert receipt["counts"]["passed"] == 1
    assert receipt["source_unchanged"] is True
    return output


def test_readiness_entry_accepts_genuine_v3_without_claiming_complete_admission(
    genuine_readiness_receipt,
):
    report = verify_test_evidence(genuine_readiness_receipt / "test_run.json")
    assert report["tests"] == 1 and report["exit_code"] == 0
    assert report["executed_test_nodeids"] == [
        "tests/unit/test_config_labels_features.py::test_metrics_empty_constant_and_known_values"
    ]
    # This is execution-integrity acceptance, not a complete phase/six-gate grant.
    assert not aggregate({})["formal_out_of_sample_research_allowed"]


READINESS_FAULTS = {
    "missing_versions_with_contradictions": "runner receipt version 3",
    "missing_versions": "runner receipt version 3",
    "collect_only": "collect_only must be false",
    "source_changed": "source_unchanged must be true",
    "command_collection_only": "Actual command differs",
    "failed_counts": "Receipt counts disagree",
}


def _damaged_readiness_receipt(original, tmp_path, fault):
    copied = tmp_path / "damaged"
    shutil.copytree(original, copied)
    path = copied / "test_run.json"
    receipt = json.loads(path.read_text())
    before = deepcopy(receipt)
    fields = set()
    if fault.startswith("missing_versions"):
        assert receipt.pop("mode") == "ci"
        assert receipt.pop("test_receipt_version") == 3
        fields.update(("mode", "test_receipt_version"))
    if fault in {"collect_only", "missing_versions_with_contradictions"}:
        receipt["collect_only"] = True
        fields.add("collect_only")
    if fault in {"source_changed", "missing_versions_with_contradictions"}:
        receipt["source_unchanged"] = False
        fields.add("source_unchanged")
    if fault in {"command_collection_only", "missing_versions_with_contradictions"}:
        receipt["command"].append("--collect-only")
        fields.add("command")
    if fault in {"failed_counts", "missing_versions_with_contradictions"}:
        receipt["counts"]["failures"] += 1
        receipt["counts"]["passed"] -= 1
        fields.add("counts")
    assert {k for k in set(before) | set(receipt) if before.get(k) != receipt.get(k)} == fields
    # JUnit stays byte-for-byte genuine: failure must come from the target contract.
    assert file_hash(copied / receipt["junit"]) == before["junit_sha256"]
    path.write_text(json.dumps(receipt))
    return path


@pytest.mark.parametrize("fault,reason", READINESS_FAULTS.items())
def test_actual_readiness_entry_rejects_execution_contract_faults(
    genuine_readiness_receipt, tmp_path, fault, reason
):
    path = _damaged_readiness_receipt(genuine_readiness_receipt, tmp_path, fault)
    with pytest.raises(ValueError, match=reason):
        verify_test_evidence(path)


@pytest.mark.parametrize("fault,reason", READINESS_FAULTS.items())
def test_real_readiness_cli_rejects_before_data_checks(
    genuine_readiness_receipt, tmp_path, fault, reason
):
    path = _damaged_readiness_receipt(genuine_readiness_receipt, tmp_path, fault)
    output = tmp_path / "readiness"
    command = [
        sys.executable,
        "tools/accept_training_readiness.py",
        "--test-run",
        str(path),
        "--evidence",
        str(tmp_path / "absent-data-evidence"),
        "--output",
        str(output),
    ]
    result = subprocess.run(
        command,
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads((output / "readiness.json").read_text())
    assert report["status"] == "FAIL"
    assert reason in report["phases"]["1"]["tests"]["reason"]
    assert report["phases"]["1"]["reason"] == "Automated test evidence failed"
    assert not report["formal_out_of_sample_research_allowed"]
    assert not (output / "test_run.json").exists()


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


@pytest.mark.parametrize(
    "recomputed,source_errors,all_pairs,expected",
    [
        ("FAIL", [{"reason": "missing_source"}], True, "FAIL"),
        ("FAIL", [{"reason": "missing_source"}], False, "FAIL"),
        ("FAIL", [], True, "FAIL"),
        ("PASS", [{"reason": "missing_source"}], True, "BLOCKED"),
        ("BLOCKED", [{"reason": "missing_source"}], False, "BLOCKED"),
        ("PASS", [], False, "PARTIAL"),
        ("PASS", [], True, "PASS"),
    ],
)
def test_recomputed_feature_failure_dominates_missing_sources_and_partial_scope(
    recomputed, source_errors, all_pairs, expected
):
    assert (
        _native_feature_scope_status(recomputed, source_errors=source_errors, all_pairs=all_pairs)
        == expected
    )
