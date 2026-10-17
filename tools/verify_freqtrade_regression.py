"""Compare trusted local Freqtrade/FreqAI runs, including prediction caches.

Usage: PYTHONPATH=src python tools/verify_freqtrade_regression.py OLD_USERDIR NEW_USERDIR
Both runs must export signals, use the same config and start with separate caches.
"""

import argparse
import io
import json
import math
import zipfile
from pathlib import Path

import joblib
import pandas as pd

from quant_strategy.infrastructure.experiment_store import file_hash, write_json
from quant_strategy.validation.truncation import load_backtest


def _archive(directory: Path) -> Path:
    archives = sorted(directory.rglob("*.zip"))
    if len(archives) != 1:
        raise ValueError(f"Expected exactly one backtest zip in {directory}, got {len(archives)}")
    return archives[0]


def _signals(archive: Path, kind: str) -> dict:
    # joblib is only used with artifacts generated locally by these test runs.
    with zipfile.ZipFile(archive) as handle:
        names = [name for name in handle.namelist() if name.endswith(f"_{kind}.pkl")]
        if len(names) != 1:
            raise ValueError(f"Missing or ambiguous {kind} export in {archive}")
        return joblib.load(io.BytesIO(handle.read(names[0])))


def _metrics(archive: Path, strategy: str) -> dict:
    with zipfile.ZipFile(archive) as handle:
        results = [
            json.loads(handle.read(name)) for name in handle.namelist() if name.endswith(".json")
        ]
    result = next(
        value["strategy"][strategy] for value in results if isinstance(value.get("strategy"), dict)
    )
    # Only wall-clock execution timestamps are excluded; historical boundaries,
    # all metrics, wallet statistics and trading settings must remain equivalent.
    excluded = {"trades", "backtest_run_start_ts", "backtest_run_end_ts"}
    return {key: value for key, value in result.items() if key not in excluded}


def _equivalent(left, right) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_equivalent(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_equivalent(a, b) for a, b in zip(left, right))
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def compare_runs(old: Path, new: Path) -> dict:
    """Compare trades/orders, metrics, signal frames, model schemas and predictions."""
    archives = {"old": _archive(old), "new": _archive(new)}
    results = {name: load_backtest(path) for name, path in archives.items()}
    differences: list[str] = []
    if any(results["old"][key] != results["new"][key] for key in ("strategy", "start", "end")):
        raise ValueError("Runs must use the same strategy and timerange")

    def compare_frames(label: str, left: pd.DataFrame, right: pd.DataFrame) -> None:
        try:
            pd.testing.assert_frame_equal(left, right, check_exact=False, rtol=1e-12, atol=1e-12)
        except AssertionError as exc:
            differences.append(f"{label}: {exc}")

    compare_frames(
        "trades", pd.DataFrame(results["old"]["trades"]), pd.DataFrame(results["new"]["trades"])
    )
    metrics = {name: _metrics(path, results[name]["strategy"]) for name, path in archives.items()}
    if not _equivalent(metrics["old"], metrics["new"]):
        for key in metrics["old"].keys() | metrics["new"].keys():
            if (
                key not in metrics["old"]
                or key not in metrics["new"]
                or not _equivalent(metrics["old"].get(key), metrics["new"].get(key))
            ):
                differences.append(f"metric/{key}: differs or missing")
    signal_counts = {}
    for kind in ("signals", "rejected", "exited"):
        left, right = _signals(archives["old"], kind), _signals(archives["new"], kind)
        if left.keys() != right.keys():
            differences.append(f"{kind}: strategy set differs")
        signal_counts[kind] = {}
        for strategy in left.keys() & right.keys():
            if left[strategy].keys() != right[strategy].keys():
                differences.append(f"{kind}/{strategy}: pair set differs")
            for pair in left[strategy].keys() & right[strategy].keys():
                a, b = left[strategy][pair], right[strategy][pair]
                compare_frames(f"{kind}/{strategy}/{pair}", a, b)
                signal_counts[kind][pair] = {"old": len(a), "new": len(b)}

    def matching_files(pattern: str) -> list[Path]:
        left = {path.relative_to(old) for path in old.rglob(pattern)}
        right = {path.relative_to(new) for path in new.rglob(pattern)}
        if not left or left != right:
            differences.append(f"{pattern}: missing or different file sets")
        return sorted(left & right)

    predictions = []
    for relative in matching_files("*_prediction.feather"):
        a, b = pd.read_feather(old / relative), pd.read_feather(new / relative)
        compare_frames(str(relative), a, b)
        predictions.append(
            {
                "file": str(relative),
                "rows": len(a),
                "old_sha256": file_hash(old / relative),
                "new_sha256": file_hash(new / relative),
            }
        )
    schemas = []
    for relative in matching_files("*_metadata.json"):
        left = json.loads((old / relative).read_text())
        right = json.loads((new / relative).read_text())
        for key in ("training_features_list", "label_list", "labels_mean", "labels_std"):
            if key not in left or key not in right or left[key] != right[key]:
                differences.append(f"{relative}: {key} differs or missing")
        schemas.append(
            {"file": str(relative), "feature_count": len(left.get("training_features_list", []))}
        )
    return {
        "passed": not differences,
        "tolerance": {"rtol": 1e-12, "atol": 1e-12},
        "archives": {
            name: {"path": str(path), "sha256": file_hash(path)} for name, path in archives.items()
        },
        "start": str(results["old"]["start"]),
        "end": str(results["old"]["end"]),
        "trade_count": {name: len(result["trades"]) for name, result in results.items()},
        "order_count": {
            name: sum(len(trade.get("orders", [])) for trade in result["trades"])
            for name, result in results.items()
        },
        "metrics": {
            "compared_keys": sorted(metrics["old"]),
            "values": {
                name: {
                    key: value.get(key)
                    for key in (
                        "profit_total_abs",
                        "final_balance",
                        "sharpe",
                        "max_drawdown_account",
                    )
                }
                for name, value in metrics.items()
            },
        },
        "signal_counts": signal_counts,
        "prediction_files": predictions,
        "model_schemas": schemas,
        "differences": differences,
    }


def main(argv: list[str] | None = None) -> int:
    """Return 0 for equivalent runs, 1 for differences, 2 for invalid inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare_runs(args.old, args.new)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        report = {"passed": False, "error": str(exc)}
        code = 2
    else:
        code = 0 if report["passed"] else 1
    if args.report:
        write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
