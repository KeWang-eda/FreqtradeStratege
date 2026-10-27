"""Read-only real-data checks of split infrastructure, without model/OOS research.

Uses current splitter and exact sample/label identities. It does not unlock the
final holdout, perform model selection, compute returns or grant stage 3 admission.
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from quant.config import load_config
from quant.dataset import build_dataset
from quant.infrastructure.experiment_store import file_hash, write_json
from quant.market_data import load_ohlcv
from quant.validation import TimeSeriesSplitter
from quant.validation.leakage import audit_fold


def audit(config_paths: list[str], bars: int = 600) -> dict:
    """Audit three fixed protocols on the same predeclared development prefix."""
    config = load_config(config_paths)
    inputs = {}
    frames = {}
    for pair, path in config.data.items():
        raw = load_ohlcv(path)
        # A leading development prefix intentionally avoids the latest final
        # holdout region. Exact requested size is mandatory.
        if len(raw) < bars:
            raise ValueError("Insufficient unshortened development prefix")
        frames[pair] = raw.iloc[:bars].copy()
        inputs[pair] = {"path": path, "sha256": file_hash(path)}
    dataset = build_dataset(frames, config)
    timestamps = pd.DatetimeIndex(dataset.metadata.available_at)
    reports = {}
    for method in ("fixed_holdout", "expanding_window", "rolling_window"):
        settings = replace(
            config.validation,
            method=method,
            train_window_size=100 if method == "rolling_window" else None,
        )
        folds = TimeSeriesSplitter(settings).split(timestamps, dataset.metadata.label_end_time)
        records = []
        for fold in folds:
            check = audit_fold(fold, timestamps, dataset.metadata.label_end_time)
            records.append(
                {
                    **check,
                    "train_ids": dataset.metadata.iloc[fold.train_indices].sample_id.tolist(),
                    "test_ids": dataset.metadata.iloc[fold.test_indices].sample_id.tolist(),
                    "purged_ids": dataset.metadata.iloc[fold.purged_indices].sample_id.tolist(),
                    "embargoed_ids": dataset.metadata.iloc[
                        fold.embargoed_indices
                    ].sample_id.tolist(),
                    "train_start": str(fold.train_start),
                    "train_end": str(fold.train_end),
                    "test_start": str(fold.test_start),
                    "test_end": str(fold.test_end),
                }
            )
        reports[method] = records
    return {
        "status": "PASS",
        "scope": "development_infrastructure_only",
        "requested_prefix_bars": bars,
        "input_files": inputs,
        "sample_count": len(dataset.X),
        "methods": reports,
        "formal_walk_forward_admission": "BLOCKED",
        "final_holdout_unlocked": False,
        "models_trained": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite split evidence")
    report = audit(args.config)
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "methods": list(report["methods"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
