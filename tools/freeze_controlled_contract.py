"""Freeze the three-pair development task before producing predictive metrics.

The contract copies production semantics, never rewrites production settings.
Revising a contract requires a new version/path; old evidence is not overwritten.
"""

import argparse
import inspect
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from quant.config import load_config
from quant.infrastructure.experiment_store import file_hash, git_state, write_json
from quant.research.contract import PAIRS, ROOT, validate_research_equivalence
from quant.validation.admission import admission_environment
from quant.validation.native_features import populate_native_features


def freeze(path: Path, config_paths: list[str]) -> dict:
    """Observe input identities/schemas only; no model fitting or metric selection."""
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise ValueError("Refusing to replace a frozen contract; use a new version")
    native = json.loads((ROOT / "config.json").read_text())
    research = load_config(config_paths)
    frames, inputs = {}, {}
    for pair in PAIRS:
        slug = pair.replace("/", "_").replace(":", "_")
        for kind, tf in (("futures", "4h"), ("mark", "1h"), ("funding_rate", "1h")):
            source = Path("data/futures") / f"{slug}-{tf}-{kind}.feather"
            inputs[pair + "|" + kind] = {"path": source.as_posix(), "sha256": file_hash(source)}
            if kind == "futures":
                frames[pair] = pd.read_feather(source)
    dates = pd.DatetimeIndex(frames[PAIRS[0]].date)
    for other in list(frames.values())[1:]:
        dates = dates.intersection(pd.DatetimeIndex(other.date))
    # A fixed native 100-bar context is conservative relative to the current
    # longest feature period 24; it is not the native 365d+100 startup promise.
    warmup, horizon = 100, native["freqai"]["feature_parameters"]["label_period_candles"]
    usable = dates[warmup:-horizon]
    stop = dates[599] + pd.Timedelta(hours=4)
    prefix = {pair: frame.loc[frame.date < stop].copy() for pair, frame in frames.items()}
    schemas = {
        pair: [c for c in populate_native_features(native, prefix, pair) if c.startswith("%")]
        for pair in PAIRS
    }
    production_paths = [
        "config.json",
        "MyStrategy.py",
        "quant/models/freqai/XGBoostRegressorES.py",
        "quant/execution/freqtrade_strategy.py",
        *[str(p.relative_to(ROOT)) for p in (ROOT / "quant/features").glob("*.py")],
        *[str(p.relative_to(ROOT)) for p in (ROOT / "quant/labels").glob("*.py")],
        str(Path(inspect.getsourcefile(populate_native_features)).relative_to(ROOT)),
    ]
    contract = {
        "schema_version": 1,
        "contract_version": "btc-eth-bnb-production-task-development-v1",
        "scope": "development",
        "frozen_at": datetime.now(UTC).isoformat(),
        "git": git_state(),
        "objective_order": ["prediction ability", "net-of-cost trading value"],
        "pairs": list(PAIRS),
        "conditional_universe": "User-named current contracts conditional on the supplied history; no survivorship-bias-free claim",
        "label": {
            "mode": native["my_experiment"]["label"],
            "horizon_candles": horizon,
            "timeframe": native["timeframe"],
            "volatility_period": 14,
            "formula": "(close[t+3]/close[t]-1)/(TA-Lib ATR(14)[t]/close[t]); zero denominator and incomplete tail are unavailable",
            "feature_available_at": "candle open + 4h (close)",
            "label_interval": "[feature_available_at, actual future horizon candle close], inclusive end",
            "purge_rule": "label_end_time >= test_start is excluded",
        },
        "feature_version": research.feature_version,
        "feature_schema_by_pair": schemas,
        "feature_availability": "Actual native expansion; source close, causal shift/rolling and correlation pairs BTC/ETH; no dynamic universe",
        "feature_context_candles": warmup,
        "model": {
            "name": native["freqaimodel"],
            "parameters": native["freqai"]["model_training_parameters"],
            "seed": research.seed,
        },
        "native_training_schedule": {
            "train_period_days": native["freqai"]["train_period_days"],
            "backtest_period_days": native["freqai"]["backtest_period_days"],
        },
        "validation": asdict(research.validation),
        "sample_interval": {
            "first_open": usable[0].isoformat(),
            "last_open": usable[-1].isoformat(),
            "global_timestamps": len(usable),
        },
        "development_probe": {
            "selection": "earliest exact globally aligned prefix",
            "global_timestamps": 4380,
            "prefix_fixture_holdout_fraction": 0.15,
            "purpose": "infrastructure validation only; no candidate selection",
        },
        "holdout": {
            "fraction": 0.15,
            "axis": "global unique eligible sample available_at; floor(N*0.85) boundary",
            "numeric_access_locked": True,
            "historical_independence": "BLOCKED",
            "exposure": "Previously used in dated OOS windows and training_repair_20261018T010644Z development training; renaming cannot restore independence",
            "metadata_access": "identities/times only, logged; source inventory may read bytes/rows without model fitting or metrics",
        },
        "baselines": ["zero", "mean_inner_train"],
        "metrics": {
            "mae": "mean(abs(y-p))",
            "rmse": "sqrt(mean((y-p)^2))",
            "direction": "mean(sign(y)==sign(p)), zero is a third sign",
            "correlation": "Pearson and Spearman; null with explicit reason for constant or insufficient samples",
            "groups": ["fold", "pair", "pooled diagnostic"],
            "market_regimes": "not defined; no post-hoc stratification",
            "selection": "no winners or profitability thresholds",
        },
        "cost_policy": {
            "fee_per_side": native["fee"],
            "predeclared_fee_multipliers": [1.0, 2.0],
            "slippage": "unknown, never implicitly zero",
            "funding": "authoritative historical payment evidence required",
            "trading_evaluation": "BLOCKED until evidence complete",
        },
        "input_files": inputs,
        "production_source_sha256": {p: file_hash(ROOT / p) for p in sorted(set(production_paths))},
        "research_config_files": [{"path": p, "sha256": file_hash(p)} for p in config_paths],
        "environment": admission_environment(),
        "formal_oos_allowed": False,
        "production_update_allowed": False,
    }
    validate_research_equivalence(contract, native, research)
    if any(file_hash(ROOT / item["path"]) != item["sha256"] for item in inputs.values()):
        raise ValueError("Input changed while freezing contract")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, contract)
    path.with_suffix(path.suffix + ".sha256").write_text(file_hash(path) + "\n")
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("-c", "--config", action="append", required=True)
    args = parser.parse_args()
    freeze(args.output, args.config)
    print(json.dumps({"contract_sha256": file_hash(args.output), "formal_oos_allowed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
