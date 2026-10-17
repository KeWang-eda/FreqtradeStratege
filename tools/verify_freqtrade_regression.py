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
import numpy as np
import pandas as pd

from quant_strategy.infrastructure.experiment_store import file_hash, write_json
from quant_strategy.validation.truncation import load_backtest

TOLERANCE = {"rtol": 1e-12, "atol": 1e-12}
METRIC_EXCLUSIONS = {
    "backtest_run_start_ts": "Wall-clock process start time, unrelated to historical decisions",
    "backtest_run_end_ts": "Wall-clock process end time, unrelated to historical decisions",
}


def _configuration(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as handle:
        names = [name for name in handle.namelist() if name.endswith("_config.json")]
        if len(names) != 1:
            raise ValueError("Native archive requires exactly one exported configuration")
        value = _json(handle.read(names[0]))
    if not isinstance(value, dict):
        raise ValueError("Invalid exported configuration")
    if "config_files" in value:
        sources = value["config_files"]
        if not isinstance(sources, list) or any(not isinstance(v, str) for v in sources):
            raise ValueError("Invalid config_files provenance")
        root = Path(__file__).resolve().parents[1]
        normalized = []
        for source in sources:
            path = Path(source)
            if path.is_absolute():
                try:
                    path = path.relative_to(root)
                except ValueError as exc:
                    raise ValueError("Config source outside checkout cannot be normalized") from exc
            if ".." in path.parts:
                raise ValueError("Config source must stay within checkout")
            normalized.append(path.as_posix())
        value["config_files"] = normalized
    return value


def _reject_constant(value: str):
    raise ValueError(f"Non-finite JSON number is invalid in results/model metadata: {value}")


def _json(value):
    return json.loads(value, parse_constant=_reject_constant)


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
        results = [_json(handle.read(name)) for name in handle.namelist() if name.endswith(".json")]
    result = next(
        value["strategy"][strategy] for value in results if isinstance(value.get("strategy"), dict)
    )
    # Only wall-clock execution timestamps are excluded; historical boundaries,
    # all metrics, wallet statistics and trading settings must remain equivalent.
    excluded = {"trades", *METRIC_EXCLUSIONS}
    return {key: value for key, value in result.items() if key not in excluded}


def _equivalent(left, right, *, numeric_tolerance=True) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _equivalent(left[k], right[k], numeric_tolerance=numeric_tolerance) for k in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _equivalent(a, b, numeric_tolerance=numeric_tolerance) for a, b in zip(left, right)
        )
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return (
            math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
            if numeric_tolerance
            else left == right
        )
    return left == right


def _model_metadata(path: Path, relative: Path) -> dict:
    value = _json(path.read_text())
    required = {"training_features_list", "label_list", "labels_mean", "labels_std"}
    if not isinstance(value, dict) or not required <= value.keys():
        raise ValueError(f"Incomplete model metadata: {path}")
    for key in ("training_features_list", "label_list"):
        if (
            not isinstance(value[key], list)
            or not value[key]
            or any(not isinstance(v, str) for v in value[key])
            or len(value[key]) != len(set(value[key]))
        ):
            raise ValueError(f"Invalid {key}: {path}")
    for key in ("labels_mean", "labels_std"):
        statistics = value[key]
        if (
            not isinstance(statistics, dict)
            or set(statistics) != set(value["label_list"])
            or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in statistics.values()
            )
            or (key == "labels_std" and any(v < 0 for v in statistics.values()))
        ):
            raise ValueError(f"Invalid {key}: {path}")
    if "data_path" in value:
        actual = Path(value["data_path"])
        expected = relative.parent
        if (
            not actual.is_absolute()
            or tuple(actual.parts[-len(expected.parts) :]) != expected.parts
        ):
            raise ValueError(f"Model data_path does not match artifact location: {path}")
        # Retain and validate the complete relative path. Only the run root varies
        # by design when FreqAI is retrained in independent fresh userdirs.
        value["data_path"] = "${USERDIR}/" + expected.as_posix()
    return value


def compare_runs(old: Path, new: Path) -> dict:
    """Compare trades/orders, metrics, signal frames, model schemas and predictions."""
    archives = {"old": _archive(old), "new": _archive(new)}
    results = {name: load_backtest(path) for name, path in archives.items()}
    differences: list[str] = []
    if any(results["old"][key] != results["new"][key] for key in ("strategy", "start", "end")):
        raise ValueError("Runs must use the same strategy and timerange")

    def compare_frames(label: str, left: pd.DataFrame, right: pd.DataFrame) -> None:
        for frame in (left, right):
            numeric = frame.select_dtypes(include="number")
            if np.isinf(numeric.to_numpy(dtype=float)).any():
                differences.append(f"{label}: invalid infinite values")
        try:
            pd.testing.assert_frame_equal(left, right, check_exact=False, rtol=1e-12, atol=1e-12)
        except AssertionError as exc:
            differences.append(f"{label}: {exc}")

    compare_frames(
        "trades", pd.DataFrame(results["old"]["trades"]), pd.DataFrame(results["new"]["trades"])
    )
    if not _equivalent(results["old"]["trades"], results["new"]["trades"], numeric_tolerance=False):
        differences.append("trades/orders: nested records differ")
    metrics = {name: _metrics(path, results[name]["strategy"]) for name, path in archives.items()}
    if not _equivalent(metrics["old"], metrics["new"]):
        for key in metrics["old"].keys() | metrics["new"].keys():
            if (
                key not in metrics["old"]
                or key not in metrics["new"]
                or not _equivalent(metrics["old"].get(key), metrics["new"].get(key))
            ):
                differences.append(f"metric/{key}: differs or missing")
    configurations = {name: _configuration(path) for name, path in archives.items()}
    for key in configurations["old"].keys() | configurations["new"].keys():
        if (
            key not in configurations["old"]
            or key not in configurations["new"]
            or not _equivalent(
                configurations["old"].get(key),
                configurations["new"].get(key),
                numeric_tolerance=False,
            )
        ):
            differences.append(f"configuration/{key}: differs or missing")
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
        left = _model_metadata(old / relative, relative)
        right = _model_metadata(new / relative, relative)
        for key in left.keys() | right.keys():
            if (
                key not in left
                or key not in right
                or not _equivalent(left.get(key), right.get(key), numeric_tolerance=False)
            ):
                differences.append(f"{relative}: {key} differs or missing")
        schemas.append(
            {"file": str(relative), "feature_count": len(left.get("training_features_list", []))}
        )
    return {
        "passed": not differences,
        "tolerance": TOLERANCE,
        "comparison_policy": {
            "excluded_result_fields": METRIC_EXCLUSIONS,
            "metadata_normalization": "Validate data_path suffix against artifact parent; normalize only independent userdir root",
            "metadata_fields": "All fields, including unknown/extra fields, are compared",
            "configuration": "All exported fields including exchange/FreqAI; config_files only normalizes checkout root, preserving order",
            "nonfinite": "Reject non-finite JSON and frame infinities; paired frame NaN masks must match",
        },
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
        "configuration_keys": sorted(configurations["old"]),
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
    except (ValueError, OSError, KeyError, TypeError, AttributeError, zipfile.BadZipFile) as exc:
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
