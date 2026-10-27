"""Fail-closed admission for formal research, separate from debug training.

Receipts provide local integrity, not signatures or a security sandbox. Python's
json object_pairs_hook detects duplicate keys; ElementTree checks actual JUnit
cases. The approach follows pytest JUnit and sklearn's train-only fitting rules.
"""

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

from quant.config import ExperimentConfig
from quant.errors import DataContractError
from quant.infrastructure.experiment_store import (
    canonical_hash,
    environment_versions,
    file_hash,
    git_state,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
# A worktree receipt is intentionally short-lived. This policy bounds unnoticed
# environment drift; it is not an assertion about historical-data shelf life.
RECEIPT_VALIDITY = timedelta(hours=24)
# Stages 3--5 need real WF/evaluation/lineage execution, and stage 6 aggregates
# them. Filling their status strings cannot stand in for implementations.
IMPLEMENTED_FORMAL_GATES = frozenset({"1", "2"})


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate evidence JSON key: {key}")
        result[key] = value
    return result


def read_evidence_json(path: str | Path) -> dict:
    """Read an object receipt without accepting duplicate keys or NaN values."""

    def invalid_constant(value: str) -> None:
        raise ValueError(f"Non-finite evidence JSON value: {value}")

    value = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=invalid_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("Evidence JSON must be an object")
    return value


def admission_environment() -> dict:
    """Record the actual packages relevant to native and research receipts."""
    result = environment_versions()
    try:
        result["ccxt"] = importlib.metadata.version("ccxt")
    except importlib.metadata.PackageNotFoundError:
        result["ccxt"] = None
    return result


def current_source_hashes(repository_root: Path | None = None) -> dict[str, str]:
    """Bind tests, validators, CLI, production adapters and training code alike."""
    repository_root = repository_root or REPOSITORY_ROOT
    paths = set(repository_root.glob("*.py"))
    for name in ("quant", "tools", "tests"):
        paths.update((repository_root / name).rglob("*.py"))
    paths.add(repository_root / "pyproject.toml")
    return {str(p.relative_to(repository_root)): file_hash(p) for p in sorted(paths)}


def git_revision_is_ancestor(root: Path, previous: str, current: str) -> bool:
    """Allow evidence-only descendants while refusing unrelated/unknown revisions."""
    if not all(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)
        for value in (previous, current)
    ):
        return False
    result = subprocess.run(
        [
            shutil.which("git") or "git",
            "--no-pager",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(root),
            "merge-base",
            "--is-ancestor",
            previous,
            current,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def new_receipt_context(run_id: str) -> dict:
    """Capture integrity context at execution time; never synthesize test outcomes."""
    created = datetime.now(UTC)
    return {
        "schema_version": 2,
        "run_id": run_id,
        "created_at": created.isoformat(),
        "expires_at": (created + RECEIPT_VALIDITY).isoformat(),
        "environment": admission_environment(),
        "source_files_sha256": current_source_hashes(),
        "git_commit": git_state().get("commit"),
    }


def _utc_time(value: str) -> datetime:
    time = datetime.fromisoformat(value)
    if time.tzinfo is None or time.utcoffset() != timedelta(0):
        raise ValueError("Evidence timestamps must use explicit UTC")
    return time


def verify_receipt_context(receipt: dict, *, run_id: str | None = None) -> None:
    """Reject old, future, wrong-run or different-code/environment evidence."""
    if receipt.get("schema_version") != 2 or not isinstance(receipt.get("run_id"), str):
        raise ValueError("Evidence requires schema 2 and a run_id")
    if not receipt["run_id"] or (run_id is not None and receipt["run_id"] != run_id):
        raise ValueError("Evidence run_id mismatch")
    created = _utc_time(receipt["created_at"])
    expires = _utc_time(receipt["expires_at"])
    now = datetime.now(UTC)
    if (
        created > now
        or expires <= now
        or expires <= created
        or expires - created > RECEIPT_VALIDITY
    ):
        raise ValueError("Evidence expired, has a future timestamp or exceeds 24-hour validity")
    if receipt.get("environment") != admission_environment():
        raise ValueError("Evidence dependency versions differ from current environment")
    if receipt.get("source_files_sha256") != current_source_hashes():
        raise ValueError("Evidence source/test fingerprints differ from current worktree")
    if not git_revision_is_ancestor(
        REPOSITORY_ROOT, receipt.get("git_commit"), git_state().get("commit")
    ):
        raise ValueError("Evidence Git revision is unknown or not an ancestor of current checkout")


def bound_artifact(directory: Path, record: dict) -> Path:
    """Resolve a hash-bound artifact without allowing absolute paths or escapes."""
    name, expected = record["path"], record["sha256"]
    if not isinstance(name, str) or Path(name).is_absolute():
        raise ValueError("Artifact paths must be relative to their receipt")
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError("Required artifact missing or outside receipt directory")
    if not isinstance(expected, str) or len(expected) != 64 or file_hash(path) != expected:
        raise ValueError("Artifact fingerprint mismatch")
    return path


def verify_test_execution(
    receipt_path: Path,
    *,
    required_nodeids: set[str] | None = None,
    run_id: str | None = None,
    require_runner_receipt: bool = True,
) -> dict:
    """Verify v3 execution evidence; missing fields never select a legacy contract."""
    if require_runner_receipt is not True:
        raise ValueError("Legacy receipts require the explicit diagnose_legacy_test_execution API")
    return _verify_test_execution(
        receipt_path,
        required_nodeids=required_nodeids,
        run_id=run_id,
        require_runner_receipt=True,
    )


def diagnose_legacy_test_execution(receipt_path: Path, *, run_id: str | None = None) -> dict:
    """Inspect old local JUnit evidence without granting engineering or formal admission."""
    report = _verify_test_execution(receipt_path, run_id=run_id, require_runner_receipt=False)
    return {
        **report,
        "diagnostic_only": True,
        "engineering_status": "PARTIAL",
        "formal_research_allowed": False,
    }


def _verify_test_execution(
    receipt_path: Path,
    *,
    required_nodeids: set[str] | None = None,
    run_id: str | None = None,
    require_runner_receipt: bool,
) -> dict:
    """Check actual JUnit outcomes, identities, exit code and execution context."""
    receipt = read_evidence_json(receipt_path)
    verify_receipt_context(receipt, run_id=run_id)
    junit = bound_artifact(
        receipt_path.parent,
        {
            "path": receipt["junit"],
            "sha256": receipt["junit_sha256"],
        },
    )
    if require_runner_receipt or "mode" in receipt or "test_receipt_version" in receipt:
        from quant.validation.test_receipts import junit_counts

        junit_counts(junit)
    root = ElementTree.parse(junit).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {
        key: sum(int(s.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    cases = list(root.iter("testcase"))
    if type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0:
        raise ValueError("Required automated tests failed: nonzero or invalid exit code")
    failures = sum(c.find("failure") is not None for c in cases)
    errors = sum(c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    if failures or errors or counts["failures"] or counts["errors"]:
        raise ValueError("Required automated tests failed")
    if not counts["tests"] or counts["tests"] != len(cases):
        raise ValueError("JUnit case count is empty or inconsistent")
    if skipped != counts["skipped"]:
        raise ValueError("JUnit skipped count is inconsistent")
    executed = [c for c in cases if c.find("skipped") is None]
    nodeids = [f"{c.get('classname', '').replace('.', '/')}.py::{c.get('name')}" for c in executed]
    if required_nodeids and required_nodeids - set(nodeids):
        raise ValueError("Required exact test node IDs were not executed")
    command = receipt.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
        raise ValueError("Test execution command is missing")
    if not (
        Path(command[0]).name.startswith("pytest")
        or any(command[i : i + 2] == ["-m", "pytest"] for i in range(len(command) - 1))
    ):
        raise ValueError("Test execution receipt does not identify a pytest command")
    report = {
        **counts,
        "executed_test_names": [c.get("name", "").split("[", 1)[0] for c in executed],
        "executed_test_nodeids": nodeids,
        "command": command,
        "exit_code": 0,
        "junit_sha256": receipt["junit_sha256"],
        "run_id": receipt["run_id"],
    }
    # Only diagnose_legacy_test_execution can explicitly select the legacy
    # branch. Versioned receipts remain strict even in that diagnostic API.
    if require_runner_receipt or "mode" in receipt or "test_receipt_version" in receipt:
        from quant.validation.test_receipts import runner_artifacts

        runner_artifacts(receipt_path, receipt, report)
    return report


def verify_complete_test_execution(receipt_path: Path, *, run_id: str) -> dict:
    """Require every currently collected test, not an arbitrary successful subset."""
    report = verify_test_execution(receipt_path, run_id=run_id, require_runner_receipt=True)
    receipt = read_evidence_json(receipt_path)
    if receipt["mode"] != "ci" or receipt["requested_subset"]:
        raise ValueError("Complete execution requires CI mode without a requested subset")
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    # A caller-controlled PYTEST_ADDOPTS can silently narrow collection (for
    # example with ``-k``).  The independent completeness check must describe
    # the repository's full suite, regardless of the shell that invokes it.
    collection_environment = os.environ.copy()
    collection_environment.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=collection_environment,
    )
    if result.returncode != 0:
        raise ValueError("Current full test collection failed")
    collected = [line.strip() for line in result.stdout.splitlines() if ".py::" in line]
    executed = report["executed_test_nodeids"]
    if (
        not collected
        or len(collected) != len(set(collected))
        or len(executed) != len(set(executed))
        or set(executed) != set(collected)
        or report["skipped"]
    ):
        raise ValueError("Complete current test suite was not executed without skips")
    return {
        **report,
        "collection_command": command,
        "collection_environment": {"PYTEST_ADDOPTS": None},
        "collected_test_count": len(collected),
        "collected_nodeids_sha256": canonical_hash(sorted(collected)),
    }


def require_training_admission(path: str | Path, config: ExperimentConfig) -> dict:
    """Revalidate receipts before creating any formal output or fitting a model."""
    try:
        return _require_training_admission(Path(path), config)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        ElementTree.ParseError,
    ) as exc:
        if isinstance(exc, DataContractError):
            raise
        raise DataContractError(
            f"Formal training denied: invalid admission evidence: {exc}"
        ) from exc


def _require_training_admission(path: Path, config: ExperimentConfig) -> dict:
    if config.research_contract is not None:
        from quant.research.contract import load_research_contract

        frozen = load_research_contract(config.research_contract)
        if frozen.get("formal_oos_allowed") is not True:
            raise DataContractError(
                "Formal training denied: controlled development contract has no formal OOS authorization"
            )
    report = read_evidence_json(path)
    phases = report.get("phases", {})
    if (
        report.get("status") != "PASS"
        or report.get("formal_out_of_sample_research_allowed") is not True
        or not isinstance(phases, dict)
        or set(phases) != {str(i) for i in range(1, 7)}
        or any(
            not isinstance(p, dict) or p.get("status") != "PASS" or p.get("not_executed")
            for p in phases.values()
        )
    ):
        raise DataContractError("Formal training denied: all six engineering gates must pass")
    if not report.get("test_receipt"):
        raise DataContractError("Formal training denied: incomplete test execution evidence")
    verify_receipt_context(report)
    tests_path = bound_artifact(path.parent, report["test_receipt"])
    required = report.get("required_test_nodeids")
    if not isinstance(required, list) or not required:
        raise DataContractError(
            "Formal training denied: required exact test identities are missing"
        )
    verify_test_execution(
        tests_path,
        required_nodeids=set(required),
        run_id=report["run_id"],
        require_runner_receipt=True,
    )
    if report.get("config_sha256") != canonical_hash(asdict(config)):
        raise DataContractError("Formal training denied: configuration differs from admission")
    inputs = report.get("input_files", {})
    if set(inputs) != set(config.data):
        raise DataContractError("Formal training denied: input scope differs from admission")
    for pair, source in config.data.items():
        if inputs[pair].get("sha256") != file_hash(source):
            raise DataContractError("Formal training denied: raw input changed")
    outputs = report.get("output_sha256")
    if not isinstance(outputs, dict) or not outputs:
        raise DataContractError("Formal training denied: required audited outputs are missing")
    for name, digest in outputs.items():
        bound_artifact(path.parent, {"path": name, "sha256": digest})
    # This registry is code, not report-controlled. Incomplete stage validators
    # must be implemented and tested before an all-PASS document can authorize.
    missing = set(phases) - IMPLEMENTED_FORMAL_GATES
    if missing:
        raise DataContractError(
            "Formal training denied: independent stage implementations unavailable: "
            + ", ".join(sorted(missing))
        )
    return {"run_id": report["run_id"], "readiness_sha256": file_hash(path)}
