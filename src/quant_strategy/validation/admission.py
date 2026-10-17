"""Formal research entry requires a complete, current engineering admission.

An admission is a local integrity receipt, not an exchange signature or security
sandbox. It never grants profitability or real-account trading authorization.
"""

import json
from dataclasses import asdict
from pathlib import Path

from quant_strategy.config import ExperimentConfig
from quant_strategy.errors import DataContractError
from quant_strategy.infrastructure.experiment_store import canonical_hash, file_hash


def require_training_admission(path: str | Path, config: ExperimentConfig) -> None:
    """Reject failed, partial, stale, unexecuted or wrong-input formal requests."""
    path = Path(path)
    report = json.loads(path.read_text())
    phases = report.get("phases", {})
    if (
        report.get("schema_version") != 1
        or report.get("status") != "PASS"
        or report.get("formal_out_of_sample_research_allowed") is not True
        or set(phases) != {str(i) for i in range(1, 7)}
        or any(p.get("status") != "PASS" or p.get("not_executed") for p in phases.values())
    ):
        raise DataContractError("Formal training denied: all six engineering gates must pass")
    tests = report.get("tests", {})
    if not tests.get("tests") or any(
        tests.get(key) != 0 for key in ("failures", "errors", "skipped", "exit_code")
    ):
        raise DataContractError("Formal training denied: incomplete test execution evidence")
    if report.get("config_sha256") != canonical_hash(asdict(config)):
        raise DataContractError("Formal training denied: configuration differs from admission")
    inputs = report.get("input_files", {})
    if set(inputs) != set(config.data):
        raise DataContractError("Formal training denied: input scope differs from admission")
    for pair, source in config.data.items():
        if inputs[pair].get("sha256") != file_hash(source):
            raise DataContractError("Formal training denied: raw input changed")
    if not report.get("output_sha256"):
        raise DataContractError("Formal training denied: required audited outputs are missing")
    for name, expected in report["output_sha256"].items():
        target = (path.parent / name).resolve()
        if not target.is_relative_to(path.parent.resolve()) or file_hash(target) != expected:
            raise DataContractError("Formal training denied: audited artifact changed")
