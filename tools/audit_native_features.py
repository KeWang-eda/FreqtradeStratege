"""Audit the actual native schema against a fixed common window of real local candles.

No exchange, model trainer, DataProvider, downloader or network client is created.
Source files are fingerprinted before and after loading. The requested bar count
is never silently reduced for a pair with insufficient history.
"""

import argparse
import hashlib
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from quant_strategy.infrastructure.experiment_store import git_state
from quant_strategy.validation.native_features import (
    audit_native_features,
    populate_native_features,
)


def _sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fingerprint_changes(receipts: list[tuple[Path, str]]) -> list[dict]:
    """Reject sources/config/code changed during a long-running audit."""
    return [
        {"filename": path.name, "reason": "input_changed_during_audit"}
        for path, before in receipts
        if not path.is_file() or _sha(path) != before
    ]


def main() -> int:
    """Write an immutable, evidence-bearing audit; exit nonzero for non-PASS."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", action="append", required=True)
    parser.add_argument("--datadir", type=Path)
    parser.add_argument("--bars", type=int, default=600)
    parser.add_argument("--pairs", nargs="+")
    parser.add_argument("--end", help="UTC inclusive candle OPEN timestamp; default common latest")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--save-populated", action="store_true")
    args = parser.parse_args()
    if args.bars < 80:
        parser.error("--bars must be >= 80 to observe actual production feature warm-up")
    from freqtrade.configuration.load_config import load_from_files
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

    from quant_strategy.backends.freqai import add_freqai_period_features
    from quant_strategy.execution.freqtrade_strategy import QuantStrategy
    from quant_strategy.features import (
        add_baseline_features,
        add_basic_price_features,
        add_period_expanded_features,
    )
    from quant_strategy.labels import set_regression_target
    from quant_strategy.market_data.time_index import timeframe_delta

    started_at = datetime.now(UTC).isoformat()
    config_receipts = [(Path(path), _sha(Path(path))) for path in args.config]
    code = [
        Path(__file__),
        Path(inspect.getsourcefile(audit_native_features)),
        Path(inspect.getsourcefile(QuantStrategy)),
        Path(inspect.getsourcefile(FreqaiDataKitchen)),
        *[
            Path(inspect.getsourcefile(function))
            for function in (
                add_freqai_period_features,
                add_period_expanded_features,
                add_basic_price_features,
                add_baseline_features,
                set_regression_target,
            )
        ],
    ]
    code_receipts = [(path, _sha(path)) for path in code]
    config = load_from_files(args.config)
    pairs = args.pairs if args.pairs else config["exchange"]["pair_whitelist"]
    sources = list(
        dict.fromkeys(
            [*pairs, *config["freqai"]["feature_parameters"].get("include_corr_pairlist", [])]
        )
    )
    datadir = args.datadir if args.datadir else Path(config["datadir"])
    frames, input_files, errors, source_receipts = {}, [], [], []
    for pair in sources:
        for tf in config["freqai"]["feature_parameters"]["include_timeframes"]:
            filename = pair.replace("/", "_").replace(":", "_") + f"-{tf}-futures.feather"
            path = datadir / "futures" / filename
            if not path.is_file():
                errors.append({"pair": pair, "timeframe": tf, "reason": "missing_file"})
                continue
            before = _sha(path)
            source_receipts.append((path, before))
            value = pd.read_feather(path)
            if before != _sha(path):
                raise RuntimeError("Source changed during read-only native audit")
            input_files.append(
                {"pair": pair, "timeframe": tf, "filename": filename, "sha256": before}
            )
            frames[pair, tf] = value
    args.output.mkdir(parents=True, exist_ok=False)
    if frames:
        end = (
            pd.Timestamp(args.end)
            if args.end
            else min(value.date.max() for value in frames.values())
        )
        if end.tzinfo is None:
            raise ValueError("--end must include a timezone")
        for (pair, tf), value in list(frames.items()):
            # The common window is defined before the audit, not chosen by results.
            start = end - (args.bars - 1) * timeframe_delta(config["timeframe"])
            current = value.loc[value.date.between(start, end)].copy().reset_index(drop=True)
            if tf == config["timeframe"] and len(current) != args.bars:
                errors.append(
                    {
                        "pair": pair,
                        "timeframe": tf,
                        "reason": "insufficient_requested_window",
                        "expected": args.bars,
                        "actual": len(current),
                    }
                )
            frames[pair, tf] = current
        report = audit_native_features(
            config,
            frames,
            pairs=pairs,
            cut_points=[args.bars // 3, 2 * args.bars // 3, args.bars - 20],
        )
        report["requested_common_window"] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "base_bars": args.bars,
        }
    else:
        report = {"status": "BLOCKED", "reason": "No real input frames"}
    if errors and report["status"] == "PASS":
        report["status"] = "BLOCKED"
    report.update(
        run_id=args.output.parent.name,
        executed_at=datetime.now(UTC).isoformat(),
        started_at=started_at,
        git=git_state(),
        input_files=input_files,
        source_errors=errors,
        config_files=[
            {"filename": path.name, "sha256": before} for path, before in config_receipts
        ],
        config_paths=[
            Path(path).resolve().relative_to(Path.cwd()).as_posix() for path in args.config
        ],
    )
    report["code_files"] = [
        {"filename": path.name, "sha256": before} for path, before in code_receipts
    ]
    if args.save_populated:
        report["populated_artifacts"] = []
        for pair in pairs:
            if report.get("pairs", {}).get(pair, {}).get("status") != "PASS":
                continue
            populated = populate_native_features(config, frames, pair)
            filename = pair.replace("/", "_").replace(":", "_") + "-populated.parquet"
            populated.to_parquet(args.output / filename, index=False)
            report["populated_artifacts"].append(
                {"pair": pair, "filename": filename, "sha256": _sha(args.output / filename)}
            )
    changes = fingerprint_changes([*config_receipts, *code_receipts, *source_receipts])
    report["input_integrity"] = {"unchanged": not changes, "changes": changes}
    if changes:
        report["status"] = "FAIL"
    (args.output / "native_features.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "audited_pairs": len(report.get("pairs", {})),
                "output": args.output.name,
            }
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
