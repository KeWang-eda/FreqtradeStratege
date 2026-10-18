"""Read-only source inventory for the explicitly selected three-pair research scope.

This is a source-quality check, not a training or formal-research authorization.
Funding's storage timeframe and observed cadence never establish the exchange's
historical payment schedule. Current exchangeInfo does not establish a historical
point-in-time universe either. No downloader, exchange client or data filler is used.
"""

import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from quant_strategy.infrastructure.experiment_store import canonical_hash, file_hash
from quant_strategy.market_data.contracts import audit_source
from quant_strategy.market_data.time_index import timeframe_delta

ROOT = Path(__file__).resolve().parents[3]
PAIRS = ("BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT")


def _public_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "${EXTERNAL}/" + path.name


def assess_funding_evidence(
    frame: pd.DataFrame, declaration: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Compare declared events without mistaking a declaration for provenance.

    An explicit historical event list can reveal contradictions, but even an exact
    match remains BLOCKED until a source-specific authoritative evidence adapter
    verifies acquisition, historical coverage and payment/publication semantics.
    Fixed intervals and current exchange rules cannot supply that missing proof.
    """
    report: dict[str, Any] = {
        "status": "BLOCKED",
        "historical_payment_schedule_verified": False,
        "payment_events_complete": None,
        "publication_time_verified": False,
        "current_rule_proves_historical_schedule": False,
        "observed_interval_is_payment_schedule": False,
        "event_comparison_status": "NOT_EXECUTED",
        "required_evidence": [
            "Authoritative historical payment-event list and acquisition provenance",
            "Pair-specific historical coverage, rule changes and payment-time semantics",
            "Independent source-specific provenance verification",
        ],
        "issues": ["authoritative_historical_funding_evidence_missing"],
    }
    try:
        if "date" not in frame or not isinstance(frame.date.dtype, pd.DatetimeTZDtype):
            raise ValueError("Funding events require timezone-aware dates")
        dates = pd.DatetimeIndex(frame.date).tz_convert("UTC").as_unit("ns")
        if (
            dates.empty
            or dates.hasnans
            or dates.has_duplicates
            or not dates.is_monotonic_increasing
        ):
            raise ValueError("Funding events must be nonempty, unique, sorted and nonmissing")
        report["observed_event_count"] = len(dates)
        report["observed_first_event"] = dates[0].isoformat()
        report["observed_last_event"] = dates[-1].isoformat()
        if declaration is None:
            return report
        if not isinstance(declaration, dict):
            raise ValueError("Funding evidence declaration must be a mapping")
        report["declared_source_type"] = declaration.get("source_type")
        if "expected_payment_events" not in declaration:
            report["issues"].append("fixed_cadence_or_current_rule_is_not_historical_evidence")
            return report
        declared = declaration["expected_payment_events"]
        if not isinstance(declared, list) or not declared:
            raise ValueError("An event declaration requires a nonempty explicit event list")
        timestamps = [pd.Timestamp(value) for value in declared]
        if any(pd.isna(value) or value.tzinfo is None for value in timestamps):
            raise ValueError("Declared payment timestamps must be timezone-aware")
        expected = pd.DatetimeIndex(timestamps).tz_convert("UTC").as_unit("ns")
        if expected.has_duplicates or not expected.is_monotonic_increasing:
            raise ValueError("Declared events must be unique and sorted")
        absent = expected.difference(dates)
        unexpected = dates.difference(expected)
        report.update(
            missing_declared_events=[stamp.isoformat() for stamp in absent],
            unexpected_observed_events=[stamp.isoformat() for stamp in unexpected],
            event_comparison_status="FAIL" if len(absent) or len(unexpected) else "PASS",
        )
        if len(absent) or len(unexpected):
            report["status"] = "FAIL"
            report["issues"].append("observed_events_contradict_declared_event_list")
        else:
            report["issues"].append("matching_events_do_not_authenticate_their_own_source")
    except (ValueError, TypeError, OverflowError) as error:
        report.update(status="FAIL", error=str(error))
    return report


def _source(path: Path, pair: str, kind: str, timeframe: str) -> tuple[dict, pd.DataFrame | None]:
    report: dict[str, Any] = {
        "pair": pair,
        "kind": kind,
        "timeframe": timeframe,
        "path": _public_path(path),
        "exists": path.is_file(),
        "captured_at": None,
        "provenance": "Existing local native-history file; acquisition provenance unavailable",
        "file_sha256": None,
        "normalized_sha256": None,
        "unchanged_during_read": None,
        "unchanged_through_audit": None,
        "duplicate_timestamps": None,
        "null_timestamps": None,
        "status": "FAIL",
        "issues": [],
    }
    if not path.is_file():
        report["issues"].append({"code": "missing_file"})
        return report, None
    before = file_hash(path)
    report["file_sha256"] = before
    frame = None
    try:
        frame = pd.read_feather(path) if path.suffix == ".feather" else pd.read_parquet(path)
        report.update(audit_source(frame, kind=kind, timeframe=timeframe))
        report["normalized_sha256"] = report.get("fingerprint")
        report["rows"] = len(frame)
        if "date" in frame:
            report["duplicate_timestamps"] = int(frame.date.duplicated().sum())
            report["null_timestamps"] = int(frame.date.isna().sum())
            report["timezone"] = (
                str(frame.date.dt.tz) if isinstance(frame.date.dtype, pd.DatetimeTZDtype) else None
            )
            report["sorted"] = bool(frame.date.is_monotonic_increasing)
        if kind == "funding_rate":
            report["historical_evidence"] = assess_funding_evidence(frame)
            report["event_completeness"] = "UNKNOWN_without_authoritative_historical_schedule"
            report["missing_rows"] = None
            report["missing_intervals"] = None
    except (OSError, ValueError, TypeError, OverflowError) as error:
        report.update(status="FAIL", error=type(error).__name__)
        report["issues"].append({"code": "unreadable_or_invalid_source"})
    try:
        report["unchanged_during_read"] = before == file_hash(path)
    except OSError:
        report["unchanged_during_read"] = False
    if not report["unchanged_during_read"]:
        report["status"] = "FAIL"
        report["issues"].append({"code": "source_changed_during_read"})
    return report, frame


def _native_startup(config: dict) -> dict:
    """Derive the reviewed DataProvider formula, retaining its actual strategy source."""
    path = ROOT / "src/quant_strategy/execution/freqtrade_strategy.py"
    module = ast.parse(path.read_text())
    strategy = next(node for node in module.body if isinstance(node, ast.ClassDef))
    strategy_startup = next(
        ast.literal_eval(node.value)
        for node in strategy.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "startup_candle_count" for t in node.targets)
    )
    startup = config.get("startup_candle_count", strategy_startup)
    features = config["freqai"]["feature_parameters"]
    periods = features["indicator_periods_candles"]
    days = config["freqai"]["train_period_days"]
    if (
        type(startup) is not int
        or startup < 0
        or not isinstance(periods, list)
        or not periods
        or any(type(period) is not int or period <= 0 for period in periods)
        or type(days) is not int
        or days <= 0
    ):
        raise ValueError("Invalid native startup or training-period configuration")
    count = int(max(startup, max(periods)) + days * pd.Timedelta(days=1) / timeframe_delta("4h"))
    return {
        "candles": count,
        "strategy_startup_candles": strategy_startup,
        "configured_startup_candles": startup,
        "train_period_days": days,
        "formula": "int(max(startup_candle_count, max(indicator_periods)) + train_days*86400/timeframe_seconds)",
        "reviewed_framework": "Freqtrade 2026.7 DataProvider.get_required_startup",
        "strategy_path": _public_path(path),
        "strategy_sha256": file_hash(path),
        "scope": "Raw-history prehistory requirement; not a substitute for actual feature eligibility",
    }


def _historical_universe(pairs: list[str]) -> dict:
    """Preserve limited current-response facts without reconstructing a past universe."""
    report: dict[str, Any] = {
        "status": "BLOCKED",
        "scope": "Conditional research on today's explicitly specified BTC/ETH/BNB universe",
        "survivorship_bias_absent": False,
        "historical_tradable_status_verified": False,
        "required_evidence": "Authoritative dated listing/delisting and contract-status history",
        "current_snapshot": None,
    }
    path = ROOT / "docs/baseline/acceptance/binance-usdt-market-snapshot.json"
    if path.is_file():
        before = file_hash(path)
        snapshot = json.loads(path.read_text())
        from quant_strategy.execution.market_snapshot import digest

        content = {key: value for key, value in snapshot.items() if key != "sha256"}
        integrity = (
            snapshot.get("sha256") == digest(content)
            and snapshot.get("raw_sha256") == digest(snapshot.get("raw_response"))
            and before == file_hash(path)
        )
        current = {
            "path": _public_path(path),
            "file_sha256": before,
            "integrity_status": "PASS" if integrity else "FAIL",
            "acquired_at": snapshot.get("acquired_at"),
            "source": snapshot.get("source"),
            "proof_limit": "Integrity and current response claims do not authenticate historical tradability",
            "pairs": {},
        }
        if integrity:
            symbols = {
                item.get("symbol"): item
                for item in snapshot.get("raw_response", {}).get("symbols", [])
            }
            for pair in pairs:
                market = symbols.get(pair.split("/")[0] + "USDT", {})
                current["pairs"][pair] = {
                    "current_contract_type": market.get("contractType"),
                    "status_at_snapshot": market.get("status"),
                    "onboard_date_claim": (
                        pd.to_datetime(market["onboardDate"], unit="ms", utc=True).isoformat()
                        if isinstance(market.get("onboardDate"), int)
                        else None
                    ),
                }
        report["current_snapshot"] = current
    history = ROOT / "RESEARCH_LOG.md"
    if history.is_file():
        report["prior_terminal_data_exposure"] = {
            "status": "BLOCKED",
            "path": _public_path(history),
            "sha256": file_hash(history),
            "recorded_research_period": "2025-09-10 through 2026-10-01",
            "effect": "Renaming a terminal holdout cannot restore independence after prior model comparison",
            "source": "Existing dated model-comparison entries; not newly executed research",
        }
    return report


def audit_three_pair_sources(config: dict, pairs: list[str]) -> dict[str, Any]:
    """Audit actual local files and distinguish prediction preparation from trading proof.

    Whole-file regular-bar gaps are reported for futures/mark. For funding, only
    observed event timestamps/cadences are reported until authoritative historical
    evidence exists; no expected payments, zero rates or synthetic bars are created.
    """
    if (
        not isinstance(pairs, list)
        or not pairs
        or any(not isinstance(pair, str) for pair in pairs)
        or len(pairs) != len(set(pairs))
        or any(pair not in PAIRS for pair in pairs)
    ):
        raise ValueError("Explicit unique BTC/ETH/BNB perpetual research pairs are required")
    if (
        config.get("exchange", {}).get("name") != "binance"
        or config.get("trading_mode") != "futures"
        or config.get("timeframe") != "4h"
        or type(config.get("freqai", {}).get("feature_parameters", {}).get("label_period_candles"))
        is not int
        or config["freqai"]["feature_parameters"]["label_period_candles"] != 3
        or any(pair not in config["exchange"].get("pair_whitelist", []) for pair in pairs)
    ):
        raise ValueError(
            "Source audit requires the approved Binance futures 4h/horizon=3 configuration"
        )
    extension = config.get("dataformat_ohlcv", "feather")
    if extension not in {"feather", "parquet"}:
        raise ValueError("Source audit supports unfilled Feather/Parquet inputs only")
    root = Path(config["datadir"]) / "futures"
    startup = _native_startup(config)
    sources, frames, paths = [], {}, {}
    for pair in pairs:
        slug = pair.replace("/", "_").replace(":", "_")
        for kind, timeframe in (("futures", "4h"), ("mark", "1h"), ("funding_rate", "1h")):
            path = root / f"{slug}-{timeframe}-{kind}.{extension}"
            item, frame = _source(path, pair, kind, timeframe)
            sources.append(item)
            frames[pair, kind] = frame
            paths[pair, kind] = path
    for item in sources:
        path = paths[item["pair"], item["kind"]]
        try:
            item["unchanged_through_audit"] = item["file_sha256"] is not None and item[
                "file_sha256"
            ] == file_hash(path)
        except OSError:
            item["unchanged_through_audit"] = False
        if item["exists"] and not item["unchanged_through_audit"]:
            item["status"] = "FAIL"
            item["issues"].append({"code": "source_changed_through_audit"})
    per_pair = []
    for pair in pairs:
        selected = {item["kind"]: item for item in sources if item["pair"] == pair}
        futures, mark, funding = (
            frames[pair, kind] for kind in ("futures", "mark", "funding_rate")
        )
        future_ok = selected["futures"]["status"] == "PASS"
        item = {
            "pair": pair,
            "source_prediction_preparation_status": "PASS" if future_ok else "BLOCKED",
            "source_prediction_scope": "OHLCV source quality only; actual feature/sample eligibility checked separately",
            "trade_cost_evaluation_status": "BLOCKED",
            "native_backtest_first_prehistory_candidate": (
                (futures.date.iloc[0] + startup["candles"] * timeframe_delta("4h")).isoformat()
                if future_ok and len(futures) > startup["candles"] + 3
                else None
            ),
            "source_label_last_eligible_candle_open": (
                futures.date.iloc[-4].isoformat() if future_ok and len(futures) > 3 else None
            ),
            "last_three_futures_rows_have_incomplete_labels": min(len(futures), 3)
            if futures is not None
            else None,
            "funding_events_without_observed_mark": None,
            "mark_coverage_earlier_than_futures": None,
        }
        if (
            selected["mark"]["status"] == "PASS"
            and selected["funding_rate"]["status"] == "BLOCKED"
            and mark is not None
            and funding is not None
            and "date" in funding
        ):
            absent = pd.DatetimeIndex(funding.date).difference(pd.DatetimeIndex(mark.date))
            item["funding_events_without_observed_mark"] = [value.isoformat() for value in absent]
        if future_ok and selected["mark"]["status"] == "PASS":
            item["mark_coverage_earlier_than_futures"] = mark.date.iloc[0] < futures.date.iloc[0]
            item["observed_mark_available_through"] = mark.date.iloc[-1].isoformat()
        per_pair.append(item)
    raw_failed = any(item["status"] == "FAIL" for item in sources)
    source_fingerprint = canonical_hash(
        [
            {
                key: item.get(key)
                for key in ("pair", "kind", "timeframe", "file_sha256", "normalized_sha256")
            }
            for item in sources
        ]
    )
    return {
        "schema_version": 1,
        "scope": "development_source_inventory",
        "status": "FAIL" if raw_failed else "BLOCKED",
        "formal_research_allowed": False,
        "audited_at": datetime.now(UTC).isoformat(),
        "pairs": pairs,
        "timeframe": "4h",
        "horizon": 3,
        "native_config_sha256": canonical_hash(config),
        "source_set_sha256": source_fingerprint,
        "all_existing_files_unchanged": all(
            item["unchanged_during_read"] and item["unchanged_through_audit"]
            for item in sources
            if item["exists"]
        ),
        "sources": sources,
        "per_pair": per_pair,
        "native_startup_requirement": startup,
        "historical_universe": _historical_universe(pairs),
        "blockers": [
            "Authoritative historical funding payment schedule and acquisition provenance unavailable",
            "Historical point-in-time tradable universe unavailable; current specified-pair scope only",
            "Past model comparison/diagnostic access cannot be erased by a newly named holdout",
        ],
        "policy": {
            "read_only": True,
            "downloaded": False,
            "imputed_bars_or_rates": 0,
            "missing_rate_must_be_globally_zero": False,
            "observed_cadence_proves_payment_schedule": False,
            "file_hash_proves_source_authenticity": False,
        },
    }
