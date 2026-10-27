"""Real pytest/runner/validator CLI controls; no model or receipt success mocks."""

import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from subprocess import run

import pytest

from quant.infrastructure.experiment_store import file_hash
from quant.validation.admission import current_source_hashes
from quant.validation.source_monitor import SourceMonitor
from quant.validation.test_receipts import junit_counts

pytestmark = [pytest.mark.leakage_security, pytest.mark.formal_preflight]
MODES = ["ci", "fast", "real-data", "formal-preflight"]


@pytest.fixture(scope="module")
def actual_receipts(tmp_path_factory):
    root = tmp_path_factory.mktemp("actual-runner-receipts")
    targets = {
        "ci": "tests/unit/test_config_labels_features.py::test_metrics_empty_constant_and_known_values",
        "fast": "tests/unit/test_config_labels_features.py::test_metrics_empty_constant_and_known_values",
        "real-data": "tests/unit/test_controlled_contract.py::test_overlay_preserves_production_task_and_does_not_change_legacy_defaults",
        "formal-preflight": "tests/unit/test_controlled_contract.py::test_contract_checksum_and_formal_flags_are_enforced",
    }
    for mode, target in targets.items():
        completed = run(
            [
                sys.executable,
                "tools/run_tests.py",
                mode,
                "--output",
                str(root / mode),
                "--",
                target,
            ],
            env={**os.environ, "PYTEST_ADDOPTS": "-k hidden_filter_must_not_apply"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        receipt = json.loads((root / mode / "test_run.json").read_text())
        assert receipt["selected_nodeids"] == [target]
        assert receipt["source_unchanged"] is True
        assert receipt["counts"]["passed"] == 1
    return root


def invoke(path, mode, output, *, suite=False):
    command = [sys.executable, "tools/verify_test_consolidation.py", "--output", str(output)]
    if suite:
        command += [
            "--baseline",
            "docs/testing/baseline/full_baseline.xml",
            "--ci",
            str(path),
            "--mapping",
            "docs/testing/requirement_test_mapping.json",
        ]
    else:
        command += ["--receipt", str(path), "--mode", mode]
    result = run(
        command,
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads((output / "verification.json").read_text())
    return result, report


def copied_receipt(actual_receipts, tmp_path, mode):
    target = tmp_path / "copy"
    shutil.copytree(actual_receipts / mode, target)
    path = target / "test_run.json"
    return path, json.loads(path.read_text())


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.real_data
def test_real_receipt_cli_positive_is_integrity_only_not_complete_admission(
    actual_receipts, tmp_path, mode
):
    result, report = invoke(actual_receipts / mode / "test_run.json", mode, tmp_path / "verified")
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["receipt_integrity"] == "PASS"
    assert report["engineering_status"] == "PARTIAL"
    assert report["formal_research_allowed"] is False


KNOWN_FAULTS = {
    "collect_only": ("collect_only", ["collect_only"]),
    "source_changed": ("source_unchanged", ["source_unchanged"]),
    "command_collection_only": ("Actual command", ["command"]),
    "wrong_mode": ("Actual command", ["mode", "marker"]),
    "failed_counts": ("Receipt counts", ["counts"]),
}


def known_fault(receipt, fault):
    if fault == "collect_only":
        receipt["collect_only"] = True
    elif fault == "source_changed":
        receipt["source_unchanged"] = False
    elif fault == "command_collection_only":
        receipt["command"].append("--collect-only")
    elif fault == "wrong_mode":
        other = "fast" if receipt["mode"] != "fast" else "ci"
        receipt.update(mode=other, marker=other)
    else:
        receipt["counts"]["failures"] += 1
        receipt["counts"]["passed"] -= 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("fault", list(KNOWN_FAULTS))
@pytest.mark.real_data
def test_all_profile_clis_reject_original_audit_faults(actual_receipts, tmp_path, mode, fault):
    path, receipt = copied_receipt(actual_receipts, tmp_path, mode)
    before = deepcopy(receipt)
    known_fault(receipt, fault)
    reason, fields = KNOWN_FAULTS[fault]
    assert {k for k in receipt if receipt[k] != before[k]} == set(fields)
    path.write_text(json.dumps(receipt))
    result, report = invoke(path, mode, tmp_path / "rejected")
    assert result.returncode == 1, (fault, result.stdout, result.stderr)
    assert reason in report["error"]["message"], report
    assert report["engineering_status"] == "FAIL"


@pytest.mark.parametrize("fault", list(KNOWN_FAULTS))
@pytest.mark.real_data
def test_full_suite_cli_checks_ci_contract_before_coverage(actual_receipts, tmp_path, fault):
    path, receipt = copied_receipt(actual_receipts, tmp_path, "ci")
    known_fault(receipt, fault)
    path.write_text(json.dumps(receipt))
    result, report = invoke(path, "ci", tmp_path / "rejected", suite=True)
    assert result.returncode == 1
    assert KNOWN_FAULTS[fault][0] in report["error"]["message"], report


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("missing_version", "version 3"),
        ("missing_mode", "Invalid mode"),
        ("invalid_mode", "Invalid mode"),
        ("missing_counts", "Receipt counts"),
        ("boolean_count", "Receipt counts"),
        ("missing_source_flag", "source_unchanged"),
        ("end_hash", "before/after"),
        ("missing_monitor", "source_monitor"),
        ("missing_junit", "artifact missing"),
        ("invalid_junit", "syntax error"),
        ("junit_missing_count", "JUnit tests"),
        ("observed_command", "observed pytest"),
        ("log_rehashed", "log has no"),
        ("log_missing", "artifact missing"),
        ("sticky_drift", "Source monitor"),
        ("missing_phase", "Missing or unexpected executed test phase"),
    ],
)
@pytest.mark.real_data
def test_receipt_cli_rejects_incomplete_or_contradictory_artifacts(
    actual_receipts, tmp_path, fault, reason
):
    path, receipt = copied_receipt(actual_receipts, tmp_path, "ci")
    if fault in {
        "missing_version",
        "missing_mode",
        "missing_counts",
        "missing_source_flag",
        "missing_monitor",
    }:
        key = {
            "missing_version": "test_receipt_version",
            "missing_mode": "mode",
            "missing_counts": "counts",
            "missing_source_flag": "source_unchanged",
            "missing_monitor": "source_monitor",
        }[fault]
        del receipt[key]
    elif fault == "invalid_mode":
        receipt["mode"] = "unknown"
    elif fault == "boolean_count":
        receipt["counts"]["failures"] = False
    elif fault == "end_hash":
        receipt["source_end_files_sha256"]["tools/run_tests.py"] = "0" * 64
    elif fault.startswith("junit") or fault in {"missing_junit", "invalid_junit"}:
        junit = path.parent / receipt["junit"]
        if fault == "missing_junit":
            junit.unlink()
        else:
            text = (
                "not xml"
                if fault == "invalid_junit"
                else junit.read_text().replace('tests="1"', "")
            )
            junit.write_text(text)
            receipt["junit_sha256"] = file_hash(junit)
    else:
        key = {
            "observed_command": "selected_nodes_file",
            "missing_phase": "selected_nodes_file",
            "log_rehashed": "pytest_log",
            "log_missing": "pytest_log",
            "sticky_drift": "source_monitor",
        }[fault]
        artifact = path.parent / (
            receipt[key] if key == "selected_nodes_file" else receipt[key]["path"]
        )
        if fault == "log_missing":
            artifact.unlink()
        elif fault == "log_rehashed":
            artifact.write_text("collected nodes; execution not demonstrated\n")
        else:
            obj = json.loads(artifact.read_text())
            if fault == "observed_command":
                obj["invocation_args"].append("--collect-only")
            elif fault == "missing_phase":
                obj["reports"].pop()
            else:
                isolated = tmp_path / "watched"
                isolated.mkdir()
                (isolated / "pyproject.toml").write_text("[project]\n")
                code = isolated / "example.py"
                code.write_text("VALUE=1\n")
                monitor = SourceMonitor(isolated)
                before = current_source_hashes(isolated)
                code.write_text("VALUE=2\n")
                code.write_text("VALUE=1\n")
                after = current_source_hashes(isolated)
                assert before == after
                events = monitor.finish(before, after)["events"]
                assert events
                obj["events"] = events  # real restored-write events, not invented
            artifact.write_text(json.dumps(obj))
        if artifact.exists():
            if key == "selected_nodes_file":
                receipt["selected_nodes_file_sha256"] = file_hash(artifact)
            else:
                receipt[key]["sha256"] = file_hash(artifact)
    path.write_text(json.dumps(receipt))
    result, report = invoke(path, "ci", tmp_path / "rejected")
    assert result.returncode == 1, (fault, report)
    assert reason in report["error"]["message"], (fault, report)


@pytest.mark.parametrize(
    "tag,key",
    [(None, "passed"), ("failure", "failures"), ("error", "errors"), ("skipped", "skipped")],
)
def test_junit_count_mapping_uses_actual_leaf_outcomes(tmp_path, tag, key):
    counts = {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}
    if key != "passed":
        counts[key] = 1
    attrs = " ".join(f'{k}="{v}"' for k, v in counts.items())
    path = tmp_path / "junit.xml"
    path.write_text(
        f'<testsuites><testsuite {attrs}><testcase classname="test" name="x">'
        + (f"<{tag}/>" if tag else "")
        + "</testcase></testsuite></testsuites>"
    )
    actual = junit_counts(path)
    assert actual[key] == 1
    assert actual["passed"] == (key == "passed")


def test_actual_runner_cannot_erase_source_write_by_restoring_bytes(tmp_path):
    """Run copied real runner/library against an isolated synthetic project."""
    root = Path(__file__).resolve().parents[2]
    shutil.copytree(root / "quant", tmp_path / "quant", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "tools").mkdir()
    for name in ("run_tests.py", "pytest_receipt.py"):
        shutil.copyfile(root / "tools" / name, tmp_path / "tools" / name)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath=["."]\nmarkers=["ci: test"]\n'
    )
    source = tmp_path / "quant" / "probe.py"
    source.write_text("VALUE=1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_restored.py").write_text(
        "from pathlib import Path\nimport pytest\npytestmark=pytest.mark.ci\n"
        "def test_restored():\n"
        '    p=Path("quant/probe.py")\n'
        "    before=p.read_bytes()\n"
        '    p.write_text("VALUE=2\\n")\n'
        "    p.write_bytes(before)\n"
        "    assert p.read_bytes()==before\n"
    )
    output = tmp_path / "execution"
    completed = run(
        [sys.executable, "tools/run_tests.py", "ci", "--output", str(output)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 3, completed.stdout + completed.stderr
    receipt = json.loads((output / "test_run.json").read_text())
    execution = json.loads((output / "runner_execution.json").read_text())
    monitor = json.loads((output / "source_monitor.json").read_text())
    assert receipt["source_files_sha256"] == receipt["source_end_files_sha256"]
    assert receipt["source_unchanged"] is False
    assert execution["pytest_exit_code"] == 0
    assert execution["runner_exit_code"] == 3
    assert any(event.get("path") == "quant/probe.py" for event in monitor["events"])
