#!/usr/bin/env python3
"""Collect and classify the project's pytest nodes.

The inventory is intentionally a reporting tool rather than a pytest plugin.  It
invokes pytest's collection phase in a subprocess, then combines the collected
node IDs with a conservative static scan of the test source.  Static flags are
evidence for triage (they are never used to skip tests), and each record keeps
the evidence strings so that a reviewer can audit a classification.

Example::

    PYTHONPATH=src:. python tools/collect_test_inventory.py \
        --output docs/testing/test_inventory.json

Use ``--pytest-executable`` when pytest must run under a project virtualenv.
The command exits with pytest's collection exit code, while still writing a
report when collection fails.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

_KNOWN_CATEGORIES = {
    "contract": "unit/contract",
    "unit": "unit/contract",
    "integration": "integration",
    "leakage": "leakage/security",
    "security": "leakage/security",
    "e2e": "e2e",
    "real-data": "real-data",
    "regression": "production-regression",
}


def _normalise_node_id(node_id: str, root: Path) -> str:
    """Return a stable root-relative node ID for JSON and joins."""

    path_text = node_id.split("::", 1)[0]
    path = Path(path_text)
    if path.is_absolute():
        try:
            path_text = path.relative_to(root).as_posix()
        except ValueError:
            path_text = path.as_posix()
    else:
        path_text = path.as_posix()
    return f"{path_text}::{node_id.split('::', 1)[1]}"


def collect_nodes(
    root: Path,
    pytest_executable: str | None,
    pytest_args: Iterable[str],
) -> tuple[list[str], dict[str, Any]]:
    """Run pytest collection and return node IDs plus subprocess metadata."""

    executable = pytest_executable or sys.executable
    command = [
        executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        "tools.collect_test_inventory",
        *pytest_args,
    ]
    env = os.environ.copy()
    inherited_addopts = env.pop("PYTEST_ADDOPTS", None)
    # Make the inventory independent of a caller's implicit PYTHONPATH while
    # preserving explicitly requested entries.
    src_entries = [str(root / "src"), str(root)]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(src_entries + ([existing] if existing else []))
    with tempfile.TemporaryDirectory(prefix="quant-test-inventory-") as temp:
        capture = Path(temp) / "collection.json"
        env["_QUANT_TEST_INVENTORY_CAPTURE"] = str(capture)
        result = subprocess.run(
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        captured = json.loads(capture.read_text()) if capture.exists() else []
    nodes = [_normalise_node_id(item["node_id"], root) for item in captured]
    duplicate_ids = [node for node, count in Counter(nodes).items() if count > 1]
    if duplicate_ids:
        raise ValueError(f"Pytest collected duplicate node IDs: {duplicate_ids}")
    markers = {
        _normalise_node_id(item["node_id"], root): sorted(set(item["markers"])) for item in captured
    }
    metadata = {
        "command": command,
        "cwd": str(root),
        "exit_code": result.returncode,
        "pytest_addopts_inherited": inherited_addopts,
        "pytest_addopts_cleared": True,
        "node_markers": markers,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }
    return nodes, metadata


def pytest_collection_finish(session: Any) -> None:
    """Capture pytest's actual selected nodes and final markers as a plugin.

    This hook runs after the project's collection/marker hooks.  It is active
    only in the explicit collection subprocess created by this utility.
    """

    capture = os.environ.get("_QUANT_TEST_INVENTORY_CAPTURE")
    if capture:
        Path(capture).write_text(
            json.dumps(
                [
                    {
                        "node_id": item.nodeid,
                        "markers": [marker.name for marker in item.iter_markers()],
                    }
                    for item in session.items
                ]
            )
            + "\n"
        )


class _TestDefinitionVisitor(ast.NodeVisitor):
    """Find test definitions, decorators and line numbers in one source file."""

    def __init__(self) -> None:
        self.definitions: dict[str, dict[str, Any]] = {}
        self._classes: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._classes.append(node.name)
        self.generic_visit(node)
        self._classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._record(node)
        # Nested test helper functions are not collected as tests, but visiting
        # them helps resolve a node in unusual pytest plugin setups.
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._record(node)
        self.generic_visit(node)

    def _record(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not node.name.startswith("test"):
            return
        decorators = [ast.unparse(item) for item in node.decorator_list]
        key = "::".join([*self._classes, node.name])
        self.definitions[key] = {
            "name": node.name,
            "class": self._classes[-1] if self._classes else None,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "decorators": decorators,
            "node": node,
        }


class _CallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.imports: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        try:
            self.calls.append(ast.unparse(node.func))
        except Exception:  # pragma: no cover - defensive for exotic AST nodes
            pass
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        self.imports.extend(alias.name for alias in node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        self.imports.append(node.module or "")
        self.generic_visit(node)


def _source_files(root: Path) -> dict[str, tuple[Path, str, ast.AST | None]]:
    files: dict[str, tuple[Path, str, ast.AST | None]] = {}
    candidates = list((root / "tests").rglob("*.py"))
    candidates.extend(root.glob("test_*.py"))
    for path in sorted(set(candidates)):
        try:
            source = path.read_text(encoding="utf-8")
            tree: ast.AST | None = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            # Collection failures are represented in the report; an unreadable
            # source file must not make the inventory tool silently disappear.
            source = ""
            tree = None
        files[path.relative_to(root).as_posix()] = (path, source, tree)
    return files


def _environment(root: Path, pytest_executable: str | None) -> dict[str, Any]:
    """Capture lightweight execution identity for the inventory evidence."""

    executable = pytest_executable or sys.executable

    def run(*command: str) -> str | None:
        try:
            result = subprocess.run(
                list(command), cwd=root, capture_output=True, text=True, check=False
            )
            return (result.stdout or result.stderr).strip() or None
        except OSError:
            return None

    commit = run("git", "rev-parse", "HEAD")
    pytest_version = run(executable, "-m", "pytest", "--version")
    return {
        "python": run(executable, "--version"),
        "pytest": pytest_version,
        "git_head": commit,
    }


def _find_definition(
    node_id: str,
    files: dict[str, tuple[Path, str, ast.AST | None]],
) -> tuple[str, dict[str, Any]]:
    path_text, *parts = node_id.split("::")
    test_name = parts[-1].split("[", 1)[0] if parts else ""
    source_info = files.get(path_text)
    if source_info is None:
        return test_name, {"line": None, "class": None, "decorators": []}
    _, _, tree = source_info
    if tree is None:
        return test_name, {"line": None, "class": None, "decorators": []}
    visitor = _TestDefinitionVisitor()
    visitor.visit(tree)
    key = "::".join([*parts[:-1], test_name])
    return test_name, visitor.definitions.get(
        key,
        visitor.definitions.get(
            test_name,
            {"line": None, "end_line": None, "class": None, "decorators": [], "node": None},
        ),
    )


def _node_source(
    source: str,
    definition: dict[str, Any],
    path_text: str,
) -> str:
    """Return a test's local source plus a small module/path context.

    Classifying against an entire module makes every parameterized node look
    like every other test in that file.  Restricting the body to this node
    keeps behavior flags useful while retaining imports and the path as context
    for helpers supplied by fixtures.
    """

    node = definition.get("node")
    if node is not None:
        body = ast.get_source_segment(source, node) or ""
        decorators = "\n".join(definition.get("decorators", []))
        lines = source.splitlines()
        imports = "\n".join(line for line in lines if line.startswith(("import ", "from ")))
        return f"{path_text}\n{imports}\n{decorators}\n{body}"
    return f"{path_text}\n{source}"


def _path_categories(path_text: str, source: str, node_id: str) -> list[str]:
    parts = set(Path(path_text).parts)
    lower = f"{path_text} {node_id} {source[:3000]}".lower()
    categories: list[str] = []
    for part, category in _KNOWN_CATEGORIES.items():
        if part in parts:
            categories.append(category)
    if "real" in lower and ("data" in lower or "histor" in lower):
        categories.append("real-data")
    if "production" in lower or "freqtrade_regression" in lower:
        categories.append("production-regression")
    if "e2e" in lower or "end_to_end" in lower:
        categories.append("e2e")
    if not categories:
        categories.append("uncategorized")
    return list(dict.fromkeys(categories))


def _evidence_flags(source: str, node_id: str) -> tuple[dict[str, bool], dict[str, list[str]]]:
    lower = f"{node_id}\n{source}".lower()
    call_visitor = _CallVisitor()
    try:
        call_visitor.visit(ast.parse(source))
    except SyntaxError:
        pass
    calls = " ".join(call_visitor.calls).lower()
    imports = " ".join(call_visitor.imports).lower()

    def evidence(patterns: Iterable[str]) -> list[str]:
        return [pattern for pattern in patterns if pattern.lower() in lower]

    evidence_map = {
        "real_historical_data": evidence(
            (
                "read_feather",
                "read_parquet",
                "data/futures",
                "data/ohlcv",
                "historical",
                "real_three_pair",
            )
        ),
        "model_training": evidence(
            ("xgbregressor", "xgboost", "fit_transform", "train_model", "model.fit", "train(")
        ),
        "production_features": evidence(
            (
                "populate_native_features",
                "feature_engineering",
                "freqai",
                "native_feature",
                "feature_parameters",
            )
        ),
        "cli_or_subprocess": evidence(
            ("subprocess", "sys.executable", "runpy", "formal-run", "accept_training", "cli")
        ),
        "network": evidence(
            ("requests", "httpx", "urllib", "socket", "network", "internet", "urlopen")
        ),
        "holdout_or_guard": evidence(("holdout", "final_holdout", "guard")),
        "purge": evidence(("purge", "purged")),
        "embargo": evidence(("embargo",)),
        "funding": evidence(("funding", "funding_rate")),
        "formal_admission": evidence(("admission", "readiness", "formal")),
    }
    evidence_map["real_historical_data"] += [
        item for item in ("read_feather", "read_parquet") if item in calls
    ]
    evidence_map["network"] += [
        item for item in ("requests", "httpx", "urllib", "socket") if item in imports
    ]
    flags = {name: bool(values) for name, values in evidence_map.items()}
    return flags, evidence_map


def _invariants(path_text: str, source: str, node_id: str) -> list[str]:
    lower = f"{path_text}\n{node_id}\n{source}".lower()
    rules = (
        ("production_label_horizon", ("horizon", "label_period", "volnorm", "&-s_return", "label")),
        (
            "feature_causality",
            ("future", "truncat", "lookahead", "leakage", "availability", "causal"),
        ),
        ("global_time_split", ("split", "chronolog", "walk_forward", "time_range", "sample_id")),
        ("label_boundary_purge", ("purge", "label_end", "label window")),
        ("embargo", ("embargo",)),
        ("train_validation_test_isolation", ("validation", "test", "train", "isolation")),
        (
            "preprocessor_training_scope",
            ("preprocess", "scaler", "fit_transform", "standardscaler"),
        ),
        ("holdout_access_control", ("holdout", "guard", "developmentaccess")),
        ("artifact_fingerprint_integrity", ("fingerprint", "sha256", "hash", "artifact")),
        (
            "data_source_integrity",
            ("data contract", "timestamp", "duplicate", "read_only", "coverage"),
        ),
        ("funding_evidence", ("funding",)),
        ("transaction_costs", ("cost", "fee", "slippage", "funding")),
        ("network_boundary", ("network", "offline", "socket")),
        ("formal_admission_fail_closed", ("admission", "readiness", "blocked", "fail_closed")),
        ("production_regression", ("production", "freqtrade", "baseline", "strategy")),
    )
    return [name for name, tokens in rules if any(token in lower for token in tokens)]


def _classify_duration(categories: list[str], flags: dict[str, bool]) -> str:
    if flags["real_historical_data"] or flags["model_training"] or flags["cli_or_subprocess"]:
        return "expensive"
    if "e2e" in categories or "integration" in categories:
        return "moderate"
    return "fast"


def build_inventory(
    root: Path,
    nodes: list[str],
    collection: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    files = _source_files(root)
    records: list[dict[str, Any]] = []
    for node_id in nodes:
        path_text = node_id.split("::", 1)[0]
        source_info = files.get(path_text)
        test_name, definition = _find_definition(node_id, files)
        source = _node_source(source_info[1], definition, path_text) if source_info else path_text
        categories = _path_categories(path_text, source, node_id)
        flags, evidence = _evidence_flags(source, node_id)
        records.append(
            {
                "node_id": node_id,
                "file": path_text,
                "test_name": test_name,
                "class": definition.get("class"),
                "line": definition.get("line"),
                "source_sha256": hashlib.sha256((root / path_text).read_bytes()).hexdigest(),
                "markers": definition.get("decorators", []),
                "execution_markers": collection["node_markers"][node_id],
                "categories": categories,
                "primary_category": categories[0],
                "flags": flags,
                "evidence": evidence,
                "expected_duration": _classify_duration(categories, flags),
                "protected_invariants": _invariants(path_text, source, node_id),
                "classification": "static_path_ast_heuristic",
            }
        )

    base_nodes = {node.split("[", 1)[0] for node in nodes}
    parametrized = [node for node in nodes if "[" in node.rsplit("::", 1)[-1]]
    directory_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for record in records:
        path_parts = Path(record["file"]).parts
        directory = (
            "/".join(path_parts[:2]) if path_parts and path_parts[0] == "tests" else path_parts[0]
        )
        directory_counts[directory] = directory_counts.get(directory, 0) + 1
        for category in record["categories"]:
            category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "schema_version": "1.0",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository_root": str(root),
        "environment": environment,
        "input_sha256": {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(
                {
                    *(item[0] for item in files.values()),
                    root / "pyproject.toml",
                    Path(__file__).resolve(),
                }
            )
        },
        "collection": collection,
        "summary": {
            "collected_nodes": len(nodes),
            "unique_test_functions": len(base_nodes),
            "parameterized_nodes": len(parametrized),
            "parameterized_test_functions": len({node.split("[", 1)[0] for node in parametrized}),
            "directory_node_counts": dict(sorted(directory_counts.items())),
            "category_node_counts": dict(sorted(category_counts.items())),
        },
        "tests": records,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Repository root (default: cwd)."
    )
    parser.add_argument("--output", type=Path, required=True, help="JSON output path.")
    parser.add_argument(
        "--pytest-executable",
        help="Python executable used for pytest collection (default: current Python).",
    )
    parser.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="Additional argument passed to pytest collection; may be repeated.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    nodes, collection = collect_nodes(root, args.pytest_executable, args.pytest_arg)
    report = build_inventory(
        root,
        nodes,
        collection,
        _environment(root, args.pytest_executable),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return int(collection["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
