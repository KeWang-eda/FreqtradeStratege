"""Save and load trusted local models with provenance and checksum checks."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from quant.models.standalone import StandaloneRegressor
from quant.config import ExperimentConfig
from quant.errors import DataContractError

from .experiment_store import canonical_hash, environment_versions, file_hash, write_json


def save_model(
    path: Path,
    preprocessing: Any,
    model: StandaloneRegressor,
    config: ExperimentConfig,
    training_data_end: pd.Timestamp,
    model_version: str,
) -> None:
    """Create an immutable pair/fold artifact; callers choose unique paths."""
    path.mkdir(parents=True, exist_ok=False)
    model.save(path / "model.bin")
    joblib.dump(preprocessing, path / "preprocessing.bin")
    write_json(
        path / "manifest.json",
        {
            "schema_version": 1,
            "feature_columns": list(model.columns),
            "feature_version": config.feature_version,
            "label": asdict(config.label),
            "label_version": "close-return-atr-v1",
            "model_name": config.model.name,
            "model_version": model_version,
            "training_data_end": str(training_data_end),
            "config_sha256": canonical_hash(asdict(config)),
            "environment": environment_versions(),
            "checksums": {
                name: file_hash(path / name) for name in ("model.bin", "preprocessing.bin")
            },
        },
    )


def load_model(path: str | Path, config: ExperimentConfig) -> tuple[Any, StandaloneRegressor, dict]:
    """Validate schema, units, config, dependencies and hashes before unpickling."""
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != 1
        or manifest.get("label_version") != "close-return-atr-v1"
        or manifest.get("config_sha256") != canonical_hash(asdict(config))
    ):
        raise DataContractError("Model artifact schema/config/label version mismatch")
    if (
        manifest.get("label") != asdict(config.label)
        or manifest.get("feature_version") != config.feature_version
        or manifest.get("model_name") != config.model.name
    ):
        raise DataContractError("Model artifact label/feature/model mismatch")
    current = environment_versions()
    for name in (
        "python",
        "numpy",
        "pandas",
        "scikit-learn",
        "xgboost" if config.model.name == "xgboost" else "scikit-learn",
    ):
        if manifest["environment"].get(name) != current.get(name):
            raise DataContractError(f"Model dependency version mismatch: {name}")
    for name in ("model.bin", "preprocessing.bin"):
        if manifest["checksums"].get(name) != file_hash(path / name):
            raise DataContractError(f"Model artifact checksum mismatch: {name}")
    model = StandaloneRegressor.load(path / "model.bin")
    if list(model.columns) != manifest["feature_columns"]:
        raise DataContractError("Model artifact feature schema mismatch")
    return joblib.load(path / "preprocessing.bin"), model, manifest
