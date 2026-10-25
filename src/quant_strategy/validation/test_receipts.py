"""Versioned runner evidence contract, shared by all execution profiles.

Counts follow pytest's _pytest/junitxml.py: call failures are failures, fixture
setup/teardown failures are errors; passing setup/teardown are not extra tests.
Validate leaf suites against actual testcase elements, then compare the receipt.
Local hashes and independently produced process/pytest evidence detect drift
and contradictions; they are not signatures against an author forging all files.
"""

import math
import re
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from quant_strategy.infrastructure.experiment_store import canonical_hash
from quant_strategy.validation.admission import bound_artifact, read_evidence_json

MODE_MARKERS = {
    "ci": "ci",
    "fast": "fast",
    "real-data": "real_data",
    "formal-preflight": "formal_preflight",
}


def junit_counts(path: Path) -> dict:
    """Read actual leaf cases, requiring every mandatory aggregate attribute."""
    root = ET.parse(path).getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("Invalid JUnit root")
    suites = [root] if root.tag == "testsuite" else list(root)
    if not suites or any(s.tag != "testsuite" or s.find("testsuite") is not None for s in suites):
        raise ValueError("Missing or ambiguous JUnit leaf suites")
    total = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        cases = list(suite.findall("testcase"))
        actual = {"tests": len(cases)}
        for key, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
            actual[key] = sum(c.find(tag) is not None for c in cases)
        for key, count in actual.items():
            value = suite.get(key)
            if value is None or not value.isdecimal() or int(value) != count:
                raise ValueError(f"JUnit {key} count missing or inconsistent with cases")
            total[key] += count
    total["passed"] = total["tests"] - sum(total[k] for k in ("failures", "errors", "skipped"))
    if total["passed"] < 0:
        raise ValueError("Overlapping JUnit outcomes")
    return total


def runner_artifacts(path: Path, receipt: dict, report: dict) -> None:
    """Cross-check process launch, observed pytest invocation, log and outcomes."""
    if type(receipt.get("test_receipt_version")) is not int or receipt["test_receipt_version"] != 3:
        raise ValueError("Required runner receipt version 3 execution evidence missing")
    marker = MODE_MARKERS.get(receipt.get("mode"))
    if marker is None or receipt.get("marker") != marker:
        raise ValueError("Invalid mode/marker execution contract")
    if receipt.get("collect_only") is not False:
        raise ValueError("collect_only must be false for executed evidence")
    if receipt.get("source_unchanged") is not True:
        raise ValueError("source_unchanged must be true; source drift is forbidden")
    before, after = receipt["source_files_sha256"], receipt["source_end_files_sha256"]
    if not before or before != after:
        raise ValueError("Source before/after fingerprints differ")

    def artifact(key):
        return bound_artifact(path.parent, receipt[key])

    monitor = read_evidence_json(artifact("source_monitor"))
    required_watches = set(before)
    required_watches.update(str(p) for name in before for p in Path(name).parents)
    if (
        monitor.get("method") != "linux-inotify-v1"
        or monitor.get("completed") is not True
        or type(monitor.get("watch_count")) is not int
        or monitor["watch_count"] <= 0
        or not isinstance(monitor.get("watched_paths"), list)
        or monitor["watch_count"] != len(set(monitor["watched_paths"]))
        or not required_watches <= set(monitor["watched_paths"])
        or monitor.get("events") != []
        or monitor.get("before_sha256") != canonical_hash(before)
        or monitor.get("after_sha256") != canonical_hash(after)
    ):
        raise ValueError("Source monitor detected drift or lost coverage")
    execution = read_evidence_json(artifact("runner_execution"))
    selected = read_evidence_json(
        bound_artifact(
            path.parent,
            {
                "path": receipt["selected_nodes_file"],
                "sha256": receipt["selected_nodes_file_sha256"],
            },
        )
    )
    command = receipt["command"]
    extra = receipt["extra_pytest_args"]
    if not isinstance(extra, list) or not all(isinstance(a, str) for a in extra):
        raise ValueError("Invalid explicit pytest arguments")
    base = [receipt["python"], "-m", "pytest", "-q", "-m", marker, "-p", "tools.pytest_receipt"]
    if (
        command[:8] != base
        or len(command) < 11
        or not command[8].startswith("--suite-record=")
        or not command[9].startswith("--junitxml=")
        or command[10] != "--basetemp=" + receipt["basetemp"]
        or command[11:] != extra
        or receipt.get("requested_subset") is not bool(extra)
        or any(
            a.split("=", 1)[0]
            in {"--collect-only", "--collectonly", "--co", "-m", "--markexpr", "-p"}
            for a in extra
        )
        or any(a.startswith(("-m", "-p")) for a in extra)
    ):
        raise ValueError("Actual command differs from mode/marker/collection execution contract")
    if (
        Path(command[8].split("=", 1)[1]).name != receipt["selected_nodes_file"]
        or Path(command[9].split("=", 1)[1]).name != receipt["junit"]
    ):
        raise ValueError("Command output paths disagree with bound artifacts")
    if (
        execution.get("command") != command
        or execution.get("cwd") != receipt["cwd"]
        or execution.get("run_id") != receipt["run_id"]
        or execution.get("execution_id") != receipt["execution_id"]
        or execution.get("source_start_sha256") != canonical_hash(before)
        or execution.get("source_end_sha256") != canonical_hash(after)
        or execution.get("pytest_exit_code") != 0
        or execution.get("runner_exit_code") != 0
        or type(execution.get("pid")) is not int
        or execution["pid"] <= 0
        or selected.get("invocation_args") != command[3:]
        or selected.get("cwd") != receipt["cwd"]
        or selected.get("execution_id") != receipt["execution_id"]
        or selected.get("pid") != execution["pid"]
        or Path(selected.get("python", "/missing-python")).resolve()
        != Path(receipt["python"]).resolve()
        or selected.get("exit_code") != 0
    ):
        raise ValueError("Runner and observed pytest execution evidence disagree")
    for key in ("started_at", "finished_at"):
        if execution.get(key) != receipt.get(key):
            raise ValueError("Runner execution times disagree")
    start, end = (datetime.fromisoformat(receipt[k]) for k in ("started_at", "finished_at"))
    if any(
        t.tzinfo is None or t.utcoffset().total_seconds() != 0 for t in (start, end)
    ) or not start <= end <= datetime.now(UTC):
        raise ValueError("Invalid UTC execution interval")
    count = junit_counts(
        bound_artifact(path.parent, {"path": receipt["junit"], "sha256": receipt["junit_sha256"]})
    )
    declared = receipt.get("counts")
    if (
        not isinstance(declared, dict)
        or set(declared) != set(count)
        or any(type(v) is not int or v < 0 for v in declared.values())
        or declared != count
    ):
        raise ValueError("Receipt counts disagree with actual JUnit counts")
    if not count["tests"] or any(count[k] for k in ("failures", "errors", "skipped")):
        raise ValueError("Required executed JUnit cases must pass without skips")
    ids = receipt["selected_nodeids"]
    if (
        not ids
        or len(ids) != len(set(ids))
        or canonical_hash(ids) != receipt["selected_nodeids_sha256"]
        or set(ids) != set(report["executed_test_nodeids"])
        or len(ids) != len(report["executed_test_nodeids"])
    ):
        raise ValueError("Selected nodes differ from executed JUnit identities")
    if [r["node_id"] for r in selected["selected_nodes"]] != ids or any(
        marker not in r["markers"] for r in selected["selected_nodes"]
    ):
        raise ValueError("Collection identities/markers differ from execution")
    phases = {}
    for row in selected["reports"]:
        key = row["node_id"], row["phase"]
        seconds = row["seconds"]
        if (
            key in phases
            or row["outcome"] != "passed"
            or not isinstance(seconds, (float, int))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("Duplicate or unpassed execution phase")
        phases[key] = row
    if set(phases) != {(i, p) for i in ids for p in ("setup", "call", "teardown")}:
        raise ValueError("Missing or unexpected executed test phase")
    log = artifact("pytest_log").read_text()
    summary = re.findall(
        r"(?m)^([^\n]*\b(?:passed|failed|skipped|errors?)\b[^\n]*\bin \d+(?:\.\d+)?s[^\n]*)$", log
    )
    logged = {k: 0 for k in ("passed", "failures", "errors", "skipped")}
    if not summary:
        raise ValueError("Pytest log has no actual execution summary")
    for number, outcome in re.findall(r"(\d+) (passed|failed|skipped|errors?)\b", summary[-1]):
        logged[{"failed": "failures", "error": "errors"}.get(outcome, outcome)] += int(number)
    if logged != {k: count[k] for k in logged}:
        raise ValueError("Pytest log summary disagrees with actual JUnit counts")
