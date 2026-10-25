#!/usr/bin/env python3
"""Run explicit pytest layers and preserve exact collection, outcomes and cost receipts.

Examples: python tools/run_tests.py ci --output /tmp/unique-ci
          python tools/run_tests.py fast --output /tmp/unique-fast --profile
Use -- followed by pytest arguments for a deliberate subset; it is recorded as
such, never accepted as complete-project evidence by the independent validator.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_ROOT / "src"), str(_ROOT)]
from quant_strategy.infrastructure.experiment_store import canonical_hash, file_hash  # noqa: E402
from quant_strategy.validation.admission import (  # noqa: E402
    current_source_hashes,
    new_receipt_context,
)
from quant_strategy.validation.source_monitor import SourceMonitor  # noqa: E402
from quant_strategy.validation.test_receipts import MODE_MARKERS, junit_counts  # noqa: E402

_MODE_MARKERS = MODE_MARKERS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=sorted(_MODE_MARKERS))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    args, extra = parser.parse_known_args(argv)
    if extra and extra[0] == "--":
        extra = extra[1:]
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="quant-tests-"))
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    reserved = ("--suite-record", "--junitxml", "--junit-xml", "--basetemp")
    if any(value.split("=", 1)[0] in reserved for value in extra):
        parser.error("Audit output options are owned by the runner")
    if any(value in {"no:tools.pytest_receipt", "no:junitxml"} for value in extra):
        parser.error("Required receipt plugins cannot be disabled")
    monitor = SourceMonitor(_ROOT)
    context = new_receipt_context(args.run_id or output.name)
    execution_id = uuid.uuid4().hex
    basetemp = Path(tempfile.mkdtemp(prefix="quant-suite-")) / "pytest"

    marker = _MODE_MARKERS[args.mode]
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        marker,
        "-p",
        "tools.pytest_receipt",
        "--suite-record=" + str(output / "nodes.json"),
        "--junitxml=" + str(output / "junit.xml"),
        "--basetemp=" + str(basetemp),
        *extra,
    ]
    if args.collect_only:
        command.append("--collect-only")
    env = os.environ.copy()
    inherited_addopts = env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = os.pathsep.join([str(_ROOT / "src"), str(_ROOT)])
    env["QUANT_TEST_EXECUTION_ID"] = execution_id
    # Keep Python cache creation outside the monitored source-change contract.
    # Existing bytecode may be read; tests and their children do not write it.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    profile_directory = output / "profile"
    if args.profile:
        if os.environ.get("QUANT_TEST_PROFILE_DIR"):
            profile_directory = Path(os.environ["QUANT_TEST_PROFILE_DIR"]) / f"nested-{os.getpid()}"
        env["QUANT_TEST_PROFILE_DIR"] = str(profile_directory)
        env["PYTHONPATH"] = os.pathsep.join([str(_ROOT / "tools/test_support"), env["PYTHONPATH"]])
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    with (output / "pytest.log").open("w") as log:
        process = subprocess.Popen(
            command, cwd=_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        pytest_exit_code = process.wait()
    duration = time.monotonic() - started
    source_end = current_source_hashes()
    source_monitor = monitor.finish(context["source_files_sha256"], source_end)
    (output / "source_monitor.json").write_text(json.dumps(source_monitor, indent=2) + "\n")
    source_unchanged = context["source_files_sha256"] == source_end and not source_monitor["events"]
    exit_code = pytest_exit_code or (0 if source_unchanged else 3)
    finished_at = datetime.now(timezone.utc).isoformat()
    execution = {
        "execution_id": execution_id,
        "pid": process.pid,
        "run_id": context["run_id"],
        "command": command,
        "cwd": str(_ROOT),
        "started_at": started_at,
        "finished_at": finished_at,
        "pytest_exit_code": pytest_exit_code,
        "runner_exit_code": exit_code,
        "source_start_sha256": canonical_hash(context["source_files_sha256"]),
        "source_end_sha256": canonical_hash(source_end),
    }
    (output / "runner_execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    nodes_path = output / "nodes.json"
    selected = json.loads(nodes_path.read_text()) if nodes_path.is_file() else {}
    nodeids = [item["node_id"] for item in selected.get("selected_nodes", [])]
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    junit = output / "junit.xml"
    if junit.is_file():
        counts = junit_counts(junit)
    else:
        counts["passed"] = 0
    profile_counts = {}
    profiles = list(profile_directory.rglob("*.json")) if args.profile else []
    for path in profiles:
        for key, value in json.loads(path.read_text())["counts"].items():
            profile_counts[key] = profile_counts.get(key, 0) + value
    receipt = {
        **context,
        "test_receipt_version": 3,
        "execution_id": execution_id,
        "extra_pytest_args": extra,
        "mode": args.mode,
        "marker": marker,
        "command": command,
        "cwd": str(_ROOT),
        "python": sys.executable,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "exit_code": exit_code,
        "collect_only": args.collect_only,
        "counts": counts,
        "selected_nodeids": nodeids,
        "selected_nodeids_sha256": canonical_hash(nodeids),
        "selected_nodes_file": "nodes.json",
        "selected_nodes_file_sha256": file_hash(nodes_path) if nodes_path.is_file() else None,
        "junit": "junit.xml",
        "junit_sha256": file_hash(junit) if junit.is_file() else None,
        "pytest_addopts_cleared": True,
        "inherited_pytest_addopts": inherited_addopts,
        "profile_counts": profile_counts,
        "profile_process_count": len(profiles),
        "profile_files_sha256": {str(p): file_hash(p) for p in profiles},
        "basetemp": str(basetemp),
        "profile_enabled": args.profile,
        "formal_research_allowed": False,
        "source_unchanged": source_unchanged,
        "source_end_files_sha256": source_end,
        **{
            key: {"path": name, "sha256": file_hash(output / name)}
            for key, name in (
                ("source_monitor", "source_monitor.json"),
                ("runner_execution", "runner_execution.json"),
                ("pytest_log", "pytest.log"),
            )
        },
        "requested_subset": bool(extra),
        "profile_scope": "observed Python calls, including Python children; OS I/O is not inferred",
    }
    (output / "test_run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "exit_code": exit_code,
                "seconds": duration,
                "counts": counts,
                "profile_counts": profile_counts,
            }
        )
    )
    if exit_code:
        print((output / "pytest.log").read_text()[-8000:])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
