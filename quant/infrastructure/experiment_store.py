"""Small file-based tracking, avoiding an additional tracking service.

Compared interfaces: FreqAI (owns production lifecycle), sklearn Pipeline
(owns fold-local transformations), MLflow (optional external tracking).
Reference: https://mlflow.org/docs/latest/ml/tracking/
"""

import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any


def write_json(path: Path, value: Any) -> None:
    """Write portable JSON with explicit nulls, rejecting NaN and infinity."""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def file_hash(path: str | Path) -> str:
    """SHA-256 an input or artifact without loading the whole file into RAM."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    """Hash a fully resolved JSON-compatible configuration."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def environment_versions() -> dict[str, str | None]:
    """Record actual dependencies; FreqAI ships inside the Freqtrade package."""
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for package in (
        "numpy",
        "pandas",
        "scikit-learn",
        "xgboost",
        "lightgbm",
        "TA-Lib",
        "technical",
        "freqtrade",
        "pyarrow",
        "PyYAML",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def git_state() -> dict[str, Any]:
    """Record source revision and dirty status when run inside a Git checkout."""
    # Provenance queries must not execute user-configured fsmonitor/diff/textconv
    # commands. This also lets the network auditor recognize exact local queries.
    command = [
        shutil.which("git") or "git",
        "--no-pager",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(Path(__file__).resolve().parents[2]),
    ]
    try:
        commit = subprocess.check_output(
            [*command, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            [*command, "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
        )
        diff = subprocess.check_output(
            [*command, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return {
            "commit": commit,
            "dirty": bool(status),
            "diff_sha256": hashlib.sha256(diff).hexdigest(),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def create_experiment_directory(root: str | Path, experiment_id: str) -> Path:
    """Never overwrite another experiment or accept path traversal IDs."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", experiment_id):
        raise ValueError("experiment_id must be a simple directory name")
    path = Path(root) / experiment_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def snapshot_source(destination: Path) -> dict[str, str]:
    """Save actual package/adapters even when the research checkout is dirty."""
    root = Path(__file__).resolve().parents[2]
    package = root / "quant"
    files = list(package.rglob("*.py"))
    if (root / "pyproject.toml").is_file():
        files.extend(root.glob("*.py"))
        files.append(root / "pyproject.toml")
    hashes = {}
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(set(files)):
            name = str(path.relative_to(root))
            archive.add(path, arcname=name, recursive=False)
            hashes[name] = file_hash(path)
    return hashes
