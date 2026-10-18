"""Controlled development training through real FreqAI, never formal OOS research.

Uses the installed FreqaiModelResolver/DataKitchen/prediction lifecycle and the
actual strategy expansion. Original OHLCV, labels, features and XGBoost parameters
are preserved. All output is written beneath a new, isolated user directory.
"""

import argparse
import json
import logging
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from quant_strategy.infrastructure.experiment_store import (
    canonical_hash,
    environment_versions,
    file_hash,
    git_state,
    write_json,
)
from quant_strategy.market_data import load_ohlcv
from quant_strategy.market_data.time_index import timeframe_delta
from quant_strategy.validation.admission import current_source_hashes
from quant_strategy.validation.native_features import populate_native_features


def run_probe(config_path: Path, output: Path, pairs: list[str], end: str | None = None) -> dict:
    """Train once per requested pair; freeze actual inputs and preserve failures."""
    from freqtrade.configuration.config_validation import validate_config_schema
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
    from freqtrade.resolvers.freqaimodel_resolver import FreqaiModelResolver

    from tools.audit_local_network import install_policy

    output.mkdir(parents=True, exist_ok=False)
    run_id = output.parent.name
    network = {"policy": "deny-all", "http_requests": [], "socket_events": [], "process_events": []}
    install_policy("deny-all", network)
    original = json.loads(config_path.read_text())
    config = deepcopy(original)
    if not set(pairs) <= set(config["exchange"]["pair_whitelist"]):
        raise ValueError("Development pairs must belong to the production whitelist")
    config.update(
        user_data_dir=output / "userdir",
        freqaimodel_path=str(Path("freqaimodels").resolve()),
    )
    validate_config_schema(config)
    # Namespace is isolated by userdir, while the actual production identifier and
    # training parameters stay unchanged. No production model can be loaded here.
    config["user_data_dir"].mkdir()
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "scope": "development",
        "started_at": datetime.now(UTC).isoformat(),
        "status": "RUNNING",
        "git": git_state(),
        "environment": environment_versions(),
        "source_files_sha256": current_source_hashes(),
        "config_file": {"path": config_path.as_posix(), "sha256": file_hash(config_path)},
        "production_config_sha256": canonical_hash(original),
        "model_parameters": config["freqai"]["model_training_parameters"],
        "identifier": config["freqai"]["identifier"],
        "input_files": {},
        "pairs": [],
        "model_selection": "none; controlled debug correctness check, not final OOS",
    }
    try:
        required = list(
            dict.fromkeys(
                [*pairs, *config["freqai"]["feature_parameters"]["include_corr_pairlist"]]
            )
        )
        frames = {}
        for pair in required:
            path = (
                Path(config["datadir"])
                / "futures"
                / (
                    pair.replace("/", "_").replace(":", "_")
                    + f"-{config['timeframe']}-futures.feather"
                )
            )
            frames[pair] = load_ohlcv(path)
            report["input_files"][pair] = {
                "path": str(path.resolve().relative_to(Path.cwd())),
                "sha256": file_hash(path),
                "rows": len(frames[pair]),
            }
        step = timeframe_delta(config["timeframe"])
        common_end = min(frame.date.iloc[-1] for frame in frames.values()) + step
        if end is not None:
            requested_end = pd.Timestamp(end)
            if (
                requested_end.tzinfo is None
                or requested_end > common_end
                or requested_end.value % step.value
            ):
                raise ValueError("Development --end must be an available UTC candle boundary")
            common_end = requested_end.tz_convert("UTC")
        # Native startup requirement is 365 days + max(100,2*24) = 2290 bars.
        # Keep the configured training period, with 100 earlier bars for features
        # and 48 later bars solely for development prediction API verification.
        train_end = common_end - 48 * step
        train_start = train_end - pd.Timedelta(days=config["freqai"]["train_period_days"])
        prefix_start = train_start - 100 * step
        for pair, raw in frames.items():
            if raw.date.iloc[0] > prefix_start or raw.date.iloc[-1] + step < common_end:
                raise ValueError(f"Insufficient unshortened development history for {pair}")
        training_sources = {
            pair: raw.loc[(raw.date >= prefix_start) & (raw.date < train_end)].copy()
            for pair, raw in frames.items()
        }
        prediction_sources = {
            pair: raw.loc[(raw.date >= prefix_start) & (raw.date < common_end)].copy()
            for pair, raw in frames.items()
        }
        model = FreqaiModelResolver.load_freqaimodel(config)
        model.live = False
        for pair in pairs:
            dk = FreqaiDataKitchen(config, live=True, pair=pair)
            dk.full_path = model.full_path
            dk.set_paths(pair, int(train_end.timestamp()))
            dk.set_new_model_names(pair, int(train_end.timestamp()))
            populated = populate_native_features(config, training_sources, pair)
            training = populated.loc[populated.date >= train_start].copy()
            dk.find_features(training)
            dk.find_labels(training)
            dk.data_path.mkdir(parents=True, exist_ok=True)
            training.to_parquet(dk.data_path / "populated_training.parquet")
            model.dd.get_pair_dict_info(pair)
            model.model = model.train(training, pair, dk)
            model.dd.save_data(model.model, pair, dk)
            full = populate_native_features(config, prediction_sources, pair)
            predict_input = full.loc[full.date >= train_end].copy()
            predict_input.to_parquet(dk.data_path / "populated_prediction.parquet")
            predictions, ready = model.predict(predict_input, dk)
            if (
                len(predictions) != len(predict_input)
                or not np.isfinite(predictions.to_numpy()).all()
            ):
                raise ValueError("Native prediction returned missing or nonfinite values")
            predictions.insert(0, "date", predict_input.date.to_numpy())
            predictions["do_predict"] = ready
            predictions.to_parquet(dk.data_path / "development_predictions.parquet", index=False)
            report["pairs"].append(
                {
                    "pair": pair,
                    "training_start": train_start.isoformat(),
                    "training_end_exclusive": train_end.isoformat(),
                    "features": dk.training_features_list,
                    "rows_before_native_filter": len(training),
                    "prediction_rows": len(predictions),
                    "ready_prediction_rows": int(np.asarray(ready).sum()),
                    "model_directory": str(dk.data_path.relative_to(output)),
                    "audit_directory": str(model.last_native_audit_path.relative_to(output)),
                    "xgboost_rounds": model.model.get_booster().num_boosted_rounds(),
                    "best_iteration": getattr(model.model, "best_iteration", None),
                    "status": "PASS",
                }
            )
        for item in report["input_files"].values():
            if file_hash(item["path"]) != item["sha256"]:
                raise ValueError("Original input changed during development training")
        report["status"] = "PASS"
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["artifacts"] = {
            str(p.relative_to(output)): file_hash(p) for p in output.rglob("*") if p.is_file()
        }
        network["completed"] = report["status"] == "PASS"
        network["denied_operations"] = sum(
            not item["allowed"]
            for key in ("http_requests", "socket_events", "process_events")
            for item in network[key]
        )
        write_json(output / "network.json", network)
        write_json(output / "training_run.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--end", help="Optional exclusive UTC prediction cutoff; tests use an early history prefix"
    )
    parser.add_argument(
        "--pairs", nargs="+", default=["BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT"]
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    run_probe(args.config, args.output, args.pairs, args.end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
