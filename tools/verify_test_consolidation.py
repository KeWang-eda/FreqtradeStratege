"""Independently compare real pytest collections, JUnit and requirement coverage.

This verifies test engineering evidence. It never authorizes formal research.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from quant.infrastructure.experiment_store import canonical_hash, file_hash, write_json
from quant.validation.admission import (
    bound_artifact,
    read_evidence_json,
    verify_complete_test_execution,
    verify_test_execution,
)


def junit_nodes(path: Path) -> tuple[set[str], dict]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    nodeids = [f"{c.get('classname', '').replace('.', '/')}.py::{c.get('name')}" for c in cases]
    if len(nodeids) != len(set(nodeids)) or not nodeids:
        raise ValueError("Empty or duplicate JUnit node identities")
    counts = Counter(tests=len(cases))
    for case in cases:
        for outcome in ("failure", "error", "skipped"):
            counts[outcome] += case.find(outcome) is not None
    if any(counts[name] for name in ("failure", "error", "skipped")):
        raise ValueError("Failed/errored/skipped test cannot establish complete coverage")
    return set(nodeids), dict(counts)


def validate_selection(receipt_path: Path, expected: set[str], marker: str) -> None:
    receipt = read_evidence_json(receipt_path)
    ids = receipt["selected_nodeids"]
    if (
        not ids
        or len(ids) != len(set(ids))
        or set(ids) != expected
        or canonical_hash(ids) != receipt["selected_nodeids_sha256"]
    ):
        raise ValueError("Selected identities are empty, duplicate, incomplete or changed")
    path = bound_artifact(
        receipt_path.parent,
        {"path": receipt["selected_nodes_file"], "sha256": receipt["selected_nodes_file_sha256"]},
    )
    selection = read_evidence_json(path)
    if (
        selection["exit_code"] != 0
        or [row["node_id"] for row in selection["selected_nodes"]] != ids
        or any(marker not in row["markers"] for row in selection["selected_nodes"])
    ):
        raise ValueError("Collection identities, markers or exit code differ from execution")
    phases = {}
    for row in selection["reports"]:
        key = (row["node_id"], row["phase"])
        if key in phases or row["outcome"] != "passed":
            raise ValueError("Duplicate or unpassed execution phase")
        phases[key] = row
    if set(phases) != {
        (identity, phase) for identity in expected for phase in ("setup", "call", "teardown")
    }:
        raise ValueError("Missing or unexpected executed test phase")


def verify(baseline: Path, ci: Path, layer_receipts: list[Path], mapping: Path) -> dict:
    old_nodes, _ = junit_nodes(baseline)
    receipt = read_evidence_json(ci)
    # Validate structure and all profiles before expensive full recollection.
    # Both the CI input and every layer use exactly the same strict contract.
    verify_test_execution(ci, require_runner_receipt=True)
    if receipt["mode"] != "ci":
        raise ValueError("Main CI receipt must declare CI mode")
    modes = [read_evidence_json(path).get("mode") for path in layer_receipts]
    if len(modes) != len(set(modes)) or set(modes) != {"fast", "real-data", "formal-preflight"}:
        raise ValueError("Exactly fast/real-data/formal-preflight completed receipts are required")
    for path in layer_receipts:
        verify_test_execution(path, run_id=receipt["run_id"], require_runner_receipt=True)
    complete = verify_complete_test_execution(ci, run_id=receipt["run_id"])
    new_nodes, counts = junit_nodes(ci.parent / receipt["junit"])
    if not old_nodes <= new_nodes:
        raise ValueError("Original test coverage was removed without a migration")
    if set(receipt["selected_nodeids"]) != new_nodes:
        raise ValueError("Selected nodes differ from actual JUnit execution")
    nodes_file = ci.parent / receipt["selected_nodes_file"]
    if file_hash(nodes_file) != receipt["selected_nodes_file_sha256"]:
        raise ValueError("Selected node evidence changed")
    validate_selection(ci, new_nodes, "ci")
    selection = json.loads(nodes_file.read_text())
    if any("ci" not in row["markers"] for row in selection["selected_nodes"]):
        raise ValueError("A test is missing from universal CI")
    layers = []
    for path in layer_receipts:
        layer = json.loads(path.read_text())
        if layer["exit_code"] != 0 or layer["collect_only"]:
            raise ValueError("Layer did not actually complete")
        verify_test_execution(path, run_id=receipt["run_id"], require_runner_receipt=True)
        marker = {"fast": "fast", "real-data": "real_data", "formal-preflight": "formal_preflight"}[
            layer["mode"]
        ]
        if layer["marker"] != marker:
            raise ValueError("Layer marker differs from declared mode")
        environment = os.environ.copy()
        environment.pop("PYTEST_ADDOPTS", None)
        collection = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", marker],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        expected = {line.strip() for line in collection.stdout.splitlines() if ".py::" in line}
        if collection.returncode or not expected or set(layer["selected_nodeids"]) != expected:
            raise ValueError("Layer omitted required current collected nodes")
        selection_path = path.parent / layer["selected_nodes_file"]
        if file_hash(selection_path) != layer["selected_nodes_file_sha256"]:
            raise ValueError("Layer selection evidence changed")
        if (
            set(row["node_id"] for row in json.loads(selection_path.read_text())["selected_nodes"])
            != expected
        ):
            raise ValueError("Layer selection file does not match current collection")
        validate_selection(path, expected, marker)
        junit = path.parent / layer["junit"]
        if file_hash(junit) != layer["junit_sha256"]:
            raise ValueError("Layer JUnit changed")
        actual, layer_counts = junit_nodes(junit)
        if set(layer["selected_nodeids"]) != actual or not actual <= new_nodes:
            raise ValueError("Layer receipt does not match executed project nodes")
        layers.append(
            {
                "mode": layer["mode"],
                "counts": layer_counts,
                "seconds": layer["duration_seconds"],
                "receipt_sha256": file_hash(path),
            }
        )
    matrix = json.loads(mapping.read_text())
    inventory_path = mapping.parent / "test_inventory.json"
    if file_hash(inventory_path) != matrix["inventory_sha256"]:
        raise ValueError("Reviewed inventory fingerprint changed")
    inventory = json.loads(inventory_path.read_text())
    if {row["node_id"] for row in inventory["tests"]} != new_nodes:
        raise ValueError("Inventory differs from executed final nodes")
    selected_markers = {row["node_id"]: set(row["markers"]) for row in selection["selected_nodes"]}
    root = Path(__file__).resolve().parents[1]
    requirements = matrix.get("requirements", matrix.get("mapping", []))
    required_ids = {
        "TASK-001",
        "LEAK-001",
        "SPLIT-001",
        "SPLIT-002",
        "SPLIT-003",
        "SPLIT-004",
        "LEAK-002",
        "LEAK-003",
        "HOLDOUT-001",
        "ARTIFACT-001",
        "DATA-001",
        "DATA-002",
        "COST-001",
        "NETWORK-001",
        "RECEIPT-001",
        "GATE-001",
        "PROD-001",
    }
    if (
        len(requirements) != len(required_ids)
        or {row["id"] for row in requirements} != required_ids
    ):
        raise ValueError("Mandatory requirement group missing or duplicated")
    checked = []
    for req in requirements:
        ids = set(req.get("test_nodeids", req.get("test_ids", [])))
        if not ids or not ids <= new_nodes:
            raise ValueError(f"Requirement missing executed exact nodes: {req.get('id')}")
        detail_nodes = [
            *req["positive_tests"],
            *[item for scenario in req["fault_injection_tests"] for item in scenario["tests"]],
        ]
        if {item["node_id"] for item in detail_nodes} != ids:
            raise ValueError("Reviewed positive/fault nodes do not match requirement node IDs")
        for item in detail_nodes:
            source = root / item["node_id"].split("::", 1)[0]
            if (
                file_hash(source) != item["source_sha256"]
                or set(item["execution_markers"]) != selected_markers[item["node_id"]]
            ):
                raise ValueError("Reviewed assertion source or markers changed")
        checked.append({"id": req.get("id"), "executed_nodes": len(ids)})
    return {
        "engineering_status": "PASS",
        "formal_research_status": "BLOCKED",
        "formal_research_allowed": False,
        "original_nodes": len(old_nodes),
        "final_nodes": len(new_nodes),
        "preserved_nodes": len(old_nodes & new_nodes),
        "added_nodes": sorted(new_nodes - old_nodes),
        "removed_nodes": [],
        "junit": counts,
        "layers": layers,
        "requirements": checked,
        "complete_test_receipt": {
            k: v for k, v in complete.items() if k != "executed_test_nodeids"
        },
        "inputs_sha256": {str(p): file_hash(p) for p in [baseline, ci, mapping, *layer_receipts]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--ci", type=Path)
    parser.add_argument("--layer", type=Path, action="append", default=[])
    parser.add_argument("--mapping", type=Path)
    parser.add_argument(
        "--receipt", type=Path, help="Check one receipt's integrity, never full coverage"
    )
    parser.add_argument("--mode", choices=["ci", "fast", "real-data", "formal-preflight"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt:
        if not args.mode or args.ci or args.baseline or args.mapping or args.layer:
            parser.error("--receipt requires --mode and cannot be combined with full-suite inputs")
    elif not all((args.baseline, args.ci, args.mapping)) or args.mode:
        parser.error("Full verification requires --baseline, --ci and --mapping")
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        if args.receipt:
            report = verify_test_execution(args.receipt, require_runner_receipt=True)
            if read_evidence_json(args.receipt)["mode"] != args.mode:
                raise ValueError("Receipt mode differs from required mode")
            result = {
                "receipt_integrity": "PASS",
                "engineering_status": "PARTIAL",
                "coverage": "single receipt; complete suite and profiles not checked",
                "formal_research_allowed": False,
                "tests": report,
            }
        else:
            result = verify(args.baseline, args.ci, args.layer, args.mapping)
        code = 0
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        ET.ParseError,
    ) as error:
        result = {
            "engineering_status": "FAIL",
            "formal_research_allowed": False,
            "error": {"type": type(error).__name__, "message": str(error)},
        }
        code = 1
    write_json(args.output / "verification.json", result)
    print(json.dumps({k: result.get(k) for k in ("engineering_status", "formal_research_allowed")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
