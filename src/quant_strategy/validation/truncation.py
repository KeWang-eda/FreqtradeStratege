"""Symmetric overlap comparison of exported Freqtrade backtests.

This is a regression audit, not proof that every possible leak is absent.
"""

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from quant_strategy.errors import DataContractError
from quant_strategy.infrastructure.experiment_store import write_json


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Normalize Freqtrade's dated strings to UTC; reject missing dates."""
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise DataContractError("Missing backtest timestamp")
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def load_backtest(path: str | Path, strategy: str | None = None) -> dict:
    """Select actual result JSON, ignoring metadata/config JSON in the zip."""
    with zipfile.ZipFile(path) as archive:
        candidates = []
        for name in archive.namelist():
            if name.endswith(".json"):
                value = json.loads(archive.read(name))
                if isinstance(value, dict) and isinstance(value.get("strategy"), dict):
                    candidates.append(value["strategy"])
        if len(candidates) != 1:
            raise DataContractError("Archive requires exactly one backtest result document")
    strategies = candidates[0]
    if strategy is None:
        if len(strategies) != 1:
            raise DataContractError("Multiple strategies: select --strategy explicitly")
        strategy = next(iter(strategies))
    if strategy not in strategies:
        raise DataContractError(f"Missing strategy: {strategy}")
    result = strategies[strategy]
    required = {"trades", "backtest_start", "backtest_end"}
    if not required.issubset(result) or not isinstance(result["trades"], list):
        raise DataContractError("Backtest result requires trades and explicit time boundaries")
    start, end = utc_timestamp(result["backtest_start"]), utc_timestamp(result["backtest_end"])
    if start >= end:
        raise DataContractError("Backtest boundaries must increase")
    for trade in result["trades"]:
        if not {"pair", "open_date", "is_short", "open_rate", "close_date", "exit_reason"}.issubset(
            trade
        ):
            raise DataContractError("Incomplete trade in backtest export")
    return {"strategy": strategy, "start": start, "end": end, "trades": result["trades"]}


def trade_key(trade: dict) -> tuple:
    """Normalize pair, UTC open time, direction and price for comparison."""
    return (
        trade["pair"],
        utc_timestamp(trade["open_date"]).isoformat(),
        bool(trade["is_short"]),
        round(float(trade["open_rate"]), 10),
    )


def compare_backtests(short: dict, long: dict) -> dict:
    """Compare both entry sets; exclude terminal forced closures from exit checks."""
    if short["strategy"] != long["strategy"]:
        raise DataContractError("Cannot compare different strategy names")
    start, end = max(short["start"], long["start"]), min(short["end"], long["end"])
    if start >= end:
        raise DataContractError("Backtest intervals do not overlap")

    def indexed(result: dict) -> dict:
        trades = [
            trade for trade in result["trades"] if start <= utc_timestamp(trade["open_date"]) < end
        ]
        keyed = {trade_key(trade): trade for trade in trades}
        if len(trades) != len(keyed):
            raise DataContractError("Duplicate trade identity in backtest export")
        return keyed

    left, right = indexed(short), indexed(long)
    only_short, only_long = sorted(left.keys() - right.keys()), sorted(right.keys() - left.keys())
    differences, skipped = [], []
    for key in sorted(left.keys() & right.keys()):
        a, b = left[key], right[key]
        if (
            a["exit_reason"] == "force_exit"
            or b["exit_reason"] == "force_exit"
            or max(utc_timestamp(a["close_date"]), utc_timestamp(b["close_date"])) >= end
        ):
            skipped.append(key)
        elif (
            utc_timestamp(a["close_date"]) != utc_timestamp(b["close_date"])
            or a["exit_reason"] != b["exit_reason"]
        ):
            differences.append(
                {
                    "trade": key,
                    "short": {k: a[k] for k in ("close_date", "exit_reason")},
                    "long": {k: b[k] for k in ("close_date", "exit_reason")},
                }
            )
    return {
        "passed": not (only_short or only_long or differences),
        "overlap_start": str(start),
        "overlap_end_exclusive": str(end),
        "short_entries": len(left),
        "long_entries": len(right),
        "only_short": only_short,
        "only_long": only_long,
        "exit_differences": differences,
        "boundary_exits_skipped": skipped,
        "scope": "overlap trade regression; does not prove absence of all future-data leakage",
    }


def main(argv: list[str] | None = None) -> int:
    """Emit JSON and return 0=equal, 1=different, 2=invalid input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("short_zip")
    parser.add_argument("long_zip")
    parser.add_argument("--strategy")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare_backtests(
            load_backtest(args.short_zip, args.strategy),
            load_backtest(args.long_zip, args.strategy),
        )
    except (DataContractError, ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        report = {"passed": False, "error": str(exc), "status": "invalid_input"}
        code = 2
    else:
        code = 0 if report["passed"] else 1
    if args.report:
        write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code
