"""Layer YAML/JSON research settings and apply explicit CLI overrides."""

from dataclasses import fields
from pathlib import Path
from typing import Any, Iterable

import yaml

from quant.errors import ConfigurationError

from .schema import ExperimentConfig, LabelConfig, ModelConfig, ValidationConfig, known_fields


def merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings; replace scalar and sequence values."""
    merged = dict(base)
    for key, value in overlay.items():
        if key == "model" and isinstance(value, dict) and isinstance(merged.get(key), dict):
            previous = merged[key]
            if "name" in value and value["name"] != previous.get("name"):
                # Parameters belong to their estimator; alpha must not leak into XGBoost.
                merged[key] = {**previous, "params": {}}
        merged[key] = (
            merge_config(merged[key], value)
            if isinstance(value, dict) and isinstance(merged.get(key), dict)
            else value
        )
    return merged


def load_config(paths: Iterable[str | Path], overrides: Iterable[str] = ()) -> ExperimentConfig:
    """Load in supplied order; overrides use dotted.key=YAML-value syntax."""
    raw: dict[str, Any] = {}
    for path in paths:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ConfigurationError(f"Config must be a mapping: {path}")
        if "research" in document:
            document = document["research"]
        if not isinstance(document, dict):
            raise ConfigurationError("research must be a mapping")
        raw = merge_config(raw, document)
    for override in overrides:
        if "=" not in override:
            raise ConfigurationError(f"Expected dotted.key=value: {override}")
        key, value = override.split("=", 1)
        node = raw
        for part in key.split(".")[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ConfigurationError(f"Cannot override nested scalar: {key}")
        node[key.split(".")[-1]] = yaml.safe_load(value)
    raw = known_fields(raw, {f.name for f in fields(ExperimentConfig)}, "research")
    for key, schema in (
        ("label", LabelConfig),
        ("validation", ValidationConfig),
        ("model", ModelConfig),
    ):
        raw[key] = schema(**known_fields(raw.get(key, {}), {f.name for f in fields(schema)}, key))
    for key in ("features", "periods"):
        if key in raw:
            if not isinstance(raw[key], list):
                raise ConfigurationError(f"{key} must be a list")
            raw[key] = tuple(raw[key])
    return ExperimentConfig(**raw)
