"""Check experiment files and model contracts without fitting any estimator."""

import json
from pathlib import Path

from quant_strategy.config import load_config
from quant_strategy.errors import DataContractError

from .experiment_store import file_hash
from .model_store import load_model


def check_artifacts(path: str | Path) -> dict:
    """Verify all recorded file hashes and each persisted pair/fold model."""
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or manifest.get("schema_version") != 1:
        raise DataContractError("Experiment is incomplete or uses an unsupported schema")
    checksums = manifest.get("artifact_checksums", {})
    if not checksums:
        raise DataContractError("Experiment has no artifact checksums")
    for name, expected in checksums.items():
        target = (path / name).resolve()
        if (
            not target.is_relative_to(path.resolve())
            or not target.is_file()
            or file_hash(target) != expected
        ):
            raise DataContractError(f"Experiment artifact checksum mismatch: {name}")
    config = load_config([path / "config.resolved.yaml"])
    model_paths = sorted((path / "model").glob("*/*"))
    if not model_paths:
        raise DataContractError("Experiment has no trained model artifacts")
    for model in model_paths:
        load_model(model, config)
    return {
        "passed": True,
        "experiment_id": manifest["experiment_id"],
        "verified_files": len(checksums),
        "verified_models": len(model_paths),
    }
