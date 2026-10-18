"""Faults at the admission boundary must fail before a training directory exists."""

import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest

from quant_strategy.cli import main
from quant_strategy.config import ExperimentConfig
from quant_strategy.errors import DataContractError
from quant_strategy.infrastructure.experiment_store import canonical_hash, file_hash
from quant_strategy.validation.admission import (
    bound_artifact,
    current_source_hashes,
    git_revision_is_ancestor,
    new_receipt_context,
    require_training_admission,
    verify_receipt_context,
    verify_test_execution,
)


def test_six_pass_strings_with_counts_and_one_hash_cannot_grant_admission(tmp_path):
    config = ExperimentConfig()
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}")
    report = tmp_path / "readiness.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "PASS",
                "formal_out_of_sample_research_allowed": True,
                "phases": {str(i): {"status": "PASS"} for i in range(1, 7)},
                "tests": {"tests": 1, "failures": 0, "errors": 0, "skipped": 0, "exit_code": 0},
                "config_sha256": canonical_hash(asdict(config)),
                "input_files": {},
                "output_sha256": {artifact.name: file_hash(artifact)},
            }
        )
    )
    with pytest.raises(DataContractError):
        require_training_admission(report, config)


@pytest.mark.parametrize("content", ["{", "[]", "null", '{"status":"FAIL","status":"PASS"}'])
def test_invalid_admission_is_a_contract_error(tmp_path, content):
    report = tmp_path / "readiness.json"
    report.write_text(content)
    with pytest.raises(DataContractError):
        require_training_admission(report, ExperimentConfig())


def test_missing_admission_is_a_contract_error(tmp_path):
    with pytest.raises(DataContractError):
        require_training_admission(tmp_path / "missing.json", ExperimentConfig())


@pytest.mark.parametrize("content", ["{", "[]", "null"])
def test_formal_cli_malformed_readiness_has_stable_exit_two(tmp_path, content):
    report = tmp_path / "readiness.json"
    report.write_text(content)
    assert (
        main(
            [
                "formal-run",
                "-c",
                "configs/base.yaml",
                "-c",
                "configs/environment/local.yaml",
                "--readiness",
                str(report),
                "--output",
                str(tmp_path / "training"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "training").exists()


def test_direct_formal_api_cannot_bypass_admission(tmp_path, candles):
    from quant_strategy.experiments.runner import run_experiment

    with pytest.raises(DataContractError, match="admission"):
        run_experiment(
            ExperimentConfig(),
            tmp_path,
            frames={"BTC": candles},
            experiment_id="forged",
            experiment_scope="formal",
        )
    assert not (tmp_path / "formal").exists()


def test_default_research_artifacts_are_explicitly_development(tmp_path, candles):
    from quant_strategy.experiments.runner import run_experiment

    output = run_experiment(
        ExperimentConfig(),
        tmp_path,
        frames={"BTC": candles},
        experiment_id="debug",
        evaluate_final_holdout=True,
    )
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["experiment_scope"] == "development"
    assert manifest["formal_oos_result"] is False
    assert manifest["holdout_access"]["purpose"] == "development_diagnostic"


@pytest.mark.parametrize(
    "fault", ["run_id", "future", "expired", "too_long", "naive", "code", "environment", "commit"]
)
def test_receipt_context_rejects_mixed_stale_or_changed_context(fault):
    receipt = new_receipt_context("actual-run")
    now = datetime.now(UTC)
    if fault == "run_id":
        receipt["run_id"] = "other-run"
    elif fault == "future":
        receipt["created_at"] = (now + timedelta(hours=1)).isoformat()
    elif fault == "expired":
        receipt["created_at"] = (now - timedelta(days=2)).isoformat()
        receipt["expires_at"] = (now - timedelta(days=1)).isoformat()
    elif fault == "too_long":
        receipt["expires_at"] = (now + timedelta(days=2)).isoformat()
    elif fault == "naive":
        receipt["created_at"] = "2026-01-01T00:00:00"
    elif fault == "code":
        receipt["source_files_sha256"] = {}
    elif fault == "environment":
        receipt["environment"]["pandas"] = "unexecuted-version"
    else:
        receipt["git_commit"] = "0" * 40
    with pytest.raises(ValueError):
        verify_receipt_context(receipt, run_id="actual-run")


def test_valid_local_context_rechecks_current_state():
    verify_receipt_context(new_receipt_context("actual-run"), run_id="actual-run")


@pytest.mark.parametrize(
    "fault", ["hidden_failure", "wrong_class", "missing_case", "wrong_run", "skipped"]
)
def test_junit_uses_actual_results_and_exact_identity(tmp_path, fault):
    child = (
        "<failure/>" if fault == "hidden_failure" else "<skipped/>" if fault == "skipped" else ""
    )
    classname = "tests.other.test_file" if fault == "wrong_class" else "tests.unit.test_file"
    testcase = f'<testcase classname="{classname}" name="test_required">{child}</testcase>'
    if fault == "missing_case":
        testcase = ""
    junit = tmp_path / "tests.xml"
    junit.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
        + testcase
        + "</testsuite></testsuites>"
    )
    receipt = new_receipt_context("wrong-run" if fault == "wrong_run" else "actual-run")
    receipt.update(
        command=["python", "-m", "pytest"],
        exit_code=0,
        junit=junit.name,
        junit_sha256=file_hash(junit),
    )
    path = tmp_path / "test_run.json"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        verify_test_execution(
            path, run_id="actual-run", required_nodeids={"tests/unit/test_file.py::test_required"}
        )


@pytest.mark.parametrize("name", ["../outside", "/etc/hosts"])
def test_bound_artifact_rejects_path_escape(tmp_path, name):
    with pytest.raises(ValueError):
        bound_artifact(tmp_path, {"path": name, "sha256": "0" * 64})


def test_document_only_descendant_preserves_receipt_code_identity(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Admission Test")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    (tmp_path / "model.py").write_text("VALUE = 1\n")
    git("add", ".")
    git("commit", "-qm", "code baseline")
    original = git("rev-parse", "HEAD")
    fingerprints = current_source_hashes(tmp_path)
    (tmp_path / "README.md").write_text("Evidence from the executed baseline.\n")
    git("add", "README.md")
    git("commit", "-qm", "evidence only")
    evidence_revision = git("rev-parse", "HEAD")
    assert git_revision_is_ancestor(tmp_path, original, evidence_revision)
    assert current_source_hashes(tmp_path) == fingerprints
    (tmp_path / "model.py").write_text("VALUE = 2\n")
    git("add", "model.py")
    git("commit", "-qm", "changed training code")
    assert current_source_hashes(tmp_path) != fingerprints
    assert not git_revision_is_ancestor(tmp_path, "0" * 40, git("rev-parse", "HEAD"))
