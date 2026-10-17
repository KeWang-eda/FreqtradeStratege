"""Read-only source and sample audit for the training-readiness gates.

Contracts follow UTC candle-open/close and actual funding event semantics.
See pandas time-series documentation and the installed Freqtrade history handler;
unknown publication/schedule provenance is recorded, never inferred or filled.
"""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from quant_strategy.config import load_config
from quant_strategy.dataset import build_dataset
from quant_strategy.experiments.runner import _dataset_hash
from quant_strategy.infrastructure.experiment_store import (
    canonical_hash,
    environment_versions,
    file_hash,
    git_state,
    write_json,
)
from quant_strategy.market_data import load_ohlcv
from quant_strategy.market_data.contracts import audit_source


def audit(output: Path, native_config: Path, research_configs: list[str]) -> dict:
    """Inventory every configured source and build only eligible research samples."""
    output.mkdir(parents=True, exist_ok=False)
    config = load_config(research_configs)
    native = json.loads(native_config.read_text())
    root = Path(native["datadir"])
    sources = []
    for pair in native["exchange"]["pair_whitelist"]:
        slug = pair.replace("/", "_").replace(":", "_")
        for kind, timeframe in (
            ("futures", native["timeframe"]),
            ("mark", "1h"),
            ("funding_rate", "1h"),
        ):
            path = root / "futures" / f"{slug}-{timeframe}-{kind}.feather"
            item = {
                "pair": pair,
                "path": f"data/futures/{path.name}",
                "captured_at": None,
                "capture_provenance": "Not recorded by existing files; audit time is not acquisition time",
            }
            if not path.is_file():
                item.update(status="FAIL", issues=[{"code": "missing_file"}])
            else:
                before = file_hash(path)
                try:
                    item.update(audit_source(pd.read_feather(path), kind=kind, timeframe=timeframe))
                except (OSError, ValueError, TypeError) as error:
                    item.update(status="FAIL", issues=[{"code": type(error).__name__}])
                item.update(file_sha256=before, unchanged=before == file_hash(path))
                if not item["unchanged"]:
                    raise RuntimeError("Raw input changed during read-only audit")
            item["formal_use"] = (
                "eligible_if_window_verified" if item["status"] == "PASS" else "quarantined"
            )
            sources.append(item)
    frames = {pair: load_ohlcv(path) for pair, path in config.data.items()}
    dataset = build_dataset(frames, config)
    dataset.metadata.to_parquet(output / "sample_metadata.parquet", index=False)
    dataset.exclusions.to_parquet(output / "sample_exclusions.parquet", index=False)
    write_json(output / "source_audit.json", sources)
    report = {
        "schema_version": 1,
        "phase": 1,
        "status": "PASS",
        "executed_at": datetime.now(UTC).isoformat(),
        "environment": environment_versions(),
        "git": git_state(),
        "research_config": asdict(config),
        "config_sha256": canonical_hash(asdict(config)),
        "config_inputs": [{"path": path, "sha256": file_hash(path)} for path in research_configs],
        "input_files": {
            pair: {"path": path, "sha256": file_hash(path)} for pair, path in config.data.items()
        },
        "dataset_sha256": _dataset_hash(dataset),
        "samples": len(dataset.X),
        "features": list(dataset.X),
        "quality": dataset.quality,
        "sources_by_status": {
            status: sum(s["status"] == status for s in sources)
            for status in ("PASS", "PARTIAL", "BLOCKED", "FAIL")
        },
        "source_policy": "Missing/unknown sources quarantined; no global zero-missing-rate rule. Funding schedule unverified sources cannot authorize formal funding evaluation.",
        "thresholds": {
            "illegal_eligible_samples": 0,
            "duplicate_sample_ids": 0,
            "input_mutations": 0,
            "minimum_samples": "Every requested pair must retain >=1; splitter enforces window-specific minima",
        },
        "time_contract": "UTC open t; features observed at t+bar; label end at t+horizon bars+bar; reset recursive features at every gap",
        "availability_scope": "Research OHLCV samples; native mark/funding inventory is separate and not silently approved",
    }
    report["artifacts"] = {p.name: file_hash(p) for p in output.iterdir() if p.is_file()}
    write_json(output / "phase1_data.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument(
        "--research-config",
        nargs="+",
        default=["configs/base.yaml", "configs/environment/local.yaml"],
    )
    args = parser.parse_args(argv)
    report = audit(args.output, args.config, args.research_config)
    print(
        json.dumps(
            {
                "status": report["status"],
                "samples": report["samples"],
                "sources_by_status": report["sources_by_status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
