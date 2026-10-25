"""Versioned, fail-closed Funding and point-in-time universe evidence checks.

This module validates evidence *about* historical facts.  A structurally valid
synthetic package is never treated as proof of a real exchange history unless
its source authority and coverage are independently supplied.
"""

from __future__ import annotations

import hashlib
import json
import math
import csv
from datetime import UTC
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from quant_strategy.errors import DataContractError

SCHEMA_VERSION = 1
AUTHORITATIVE_GRADES = {"authoritative_primary", "authoritative_archive"}
ALLOWED_GRADES = AUTHORITATIVE_GRADES | {
    "secondary_reconciled",
    "self_declared",
    "unknown",
}
UNIVERSE_STATES = {"tradable", "non_tradable", "suspended", "unknown"}
_FUNDING_EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "venue",
    "instrument_id",
    "pair",
    "event_time_utc",
    "funding_rate",
    "settlement_rule_id",
    "settlement_rule_version",
    "source_type",
    "source_uri",
    "retrieved_at_utc",
    "raw_payload_sha256",
    "source_record_id",
    "parser_version",
    "transformation_version",
    "evidence_grade",
}
_RULE_FIELDS = {
    "rule_id",
    "rule_version",
    "venue",
    "instrument_id",
    "effective_from_utc",
    "effective_to_utc",
    "source_uri",
    "raw_payload_sha256",
    "retrieved_at_utc",
    "parser_version",
}
_UNIVERSE_FIELDS = {
    "schema_version",
    "venue",
    "instrument_id",
    "pair",
    "effective_from_utc",
    "effective_to_utc",
    "trading_status",
    "status_reason",
    "source_type",
    "source_uri",
    "retrieved_at_utc",
    "raw_payload_sha256",
    "rule_version",
    "evidence_grade",
}


def _sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def _timestamp(value: Any, field: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataContractError(f"{field} is not a timestamp") from exc
    if stamp.tzinfo is None:
        raise DataContractError(f"{field} must be timezone-aware UTC")
    return stamp.tz_convert("UTC")


def _source_path(package: Path, uri: str) -> Path:
    if not isinstance(uri, str) or not uri or uri.startswith(("http://", "https://")):
        raise DataContractError("source_uri must be a nonempty local audit path")
    path = (package.parent / uri).resolve()
    allowed_root = package.parent.parent.resolve()
    if not path.is_relative_to(allowed_root):
        raise DataContractError("source_uri escapes the evidence package")
    return path


def _source_check(package: Path, record: dict[str, Any], issues: list[str]) -> None:
    uri = record.get("source_uri")
    try:
        path = _source_path(package, uri)
    except DataContractError as exc:
        issues.append(str(exc))
        return
    expected = record.get("raw_payload_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        issues.append("missing_or_invalid_raw_payload_sha256")
    elif not path.is_file():
        issues.append(f"source_missing:{uri}")
    elif _sha256(path) != expected:
        issues.append(f"source_hash_mismatch:{uri}")


def _common_package(package: Path, payload: dict[str, Any], expected_type: str) -> list[str]:
    issues: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        issues.append("unsupported_schema_version")
    if payload.get("evidence_type") != expected_type:
        issues.append("wrong_evidence_type")
    if payload.get("synthetic_fixture") is True and payload.get("formal_admission_ready") is True:
        issues.append("synthetic_fixture_cannot_be_formal_ready")
    documents = payload.get("source_documents")
    if not isinstance(documents, list) or not documents:
        issues.append("source_documents_required")
    else:
        for document in documents:
            if not isinstance(document, dict) or not isinstance(document.get("source_uri"), str):
                issues.append("source_document_locator_missing")
                continue
            expected = document.get("sha256")
            try:
                path = _source_path(package, document["source_uri"])
                if not path.is_file():
                    issues.append(f"source_missing:{document['source_uri']}")
                elif not isinstance(expected, str) or _sha256(path) != expected:
                    issues.append(f"source_hash_mismatch:{document['source_uri']}")
            except DataContractError as exc:
                issues.append(str(exc))
    return issues


def _authority(grade: Any, source_type: Any, issues: list[str]) -> None:
    if grade not in ALLOWED_GRADES:
        issues.append("invalid_evidence_grade")
    if source_type in {"current_exchange_info", "observed_cadence", "caller_declared"}:
        issues.append("inferred_or_current_source_cannot_prove_history")


def _canonical_time(value: Any, field: str) -> str:
    return _timestamp(value, field).isoformat()


def _authority_documents(package: Path, payload: dict[str, Any], issues: list[str]) -> None:
    """Require an independent authority basis in addition to caller labels."""
    documents = payload.get("authority_documents")
    if not isinstance(documents, list) or not documents:
        issues.append("independent_authority_evidence_missing")
        return
    for document in documents:
        if not isinstance(document, dict) or not document.get("source_uri"):
            issues.append("authority_document_locator_missing")
            continue
        if document.get("verification_method") not in {
            "venue_signature",
            "independent_archive_chain",
            "audited_primary_export",
        }:
            issues.append("authority_verification_method_missing")
        if document.get("authority_reference") in {None, ""}:
            issues.append("authority_reference_missing")


def _source_record_match(
    package: Path, event: dict[str, Any], issues: list[str]
) -> None:
    """Bind event values to a record in the hashed raw source payload."""
    try:
        path = _source_path(package, event["source_uri"])
        if path.suffix.lower() == ".csv":
            records = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
            record = next(
                item
                for item in records
                if item.get("calc_time") == str(event["source_record_id"])
            )
            record = {
                "event_time_utc": pd.to_datetime(
                    int(record["calc_time"]), unit="ms", utc=True
                ).isoformat(),
                "funding_rate": record["last_funding_rate"],
            }
        else:
            raw = json.loads(path.read_text(encoding="utf-8"))
            records = raw.get("records", []) if isinstance(raw, dict) else raw
            record = next(
                item
                for item in records
                if isinstance(item, dict)
                and item.get("source_record_id") == event["source_record_id"]
            )
    except (OSError, ValueError, DataContractError, StopIteration, TypeError, KeyError):
        issues.append("source_record_event_record_missing")
        return
    try:
        if (
            _canonical_time(record["event_time_utc"], "event_time_utc")
            != _canonical_time(event["event_time_utc"], "event_time_utc")
            or float(record["funding_rate"]) != float(event["funding_rate"])
            or (
                "instrument_id" in record
                and record["instrument_id"] != event["instrument_id"]
            )
            or ("venue" in record and record["venue"] != event["venue"])
        ):
            issues.append("source_record_event_content_mismatch")
    except (KeyError, TypeError, ValueError, DataContractError):
        issues.append("source_record_event_content_invalid")


def _intervals(
    records: Iterable[dict[str, Any]],
    start_key: str,
    end_key: str,
    issues: list[str],
) -> list[tuple[pd.Timestamp, pd.Timestamp, dict[str, Any]]]:
    result = []
    for record in records:
        if not isinstance(record, dict):
            issues.append("interval_record_must_be_object")
            continue
        try:
            start = _timestamp(record[start_key], start_key)
            end = _timestamp(record[end_key], end_key) if record.get(end_key) else None
            if end is not None and end <= start:
                issues.append("invalid_effective_interval")
            result.append((start, end or pd.Timestamp.max.tz_localize("UTC"), record))
        except (KeyError, DataContractError, TypeError) as exc:
            issues.append(str(exc))
    return result


def validate_funding_package(
    package_path: str | Path,
    *,
    pairs: Iterable[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    mark_times: dict[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Independently validate Funding events, rules, hashes and coverage."""
    package = Path(package_path).resolve()
    issues: list[str] = []
    try:
        payload = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "schema_status": "FAIL",
            "provenance_status": "FAIL",
            "historical_coverage_status": "BLOCKED",
            "formal_admission_ready": False,
            "issues": [f"package_unreadable:{type(exc).__name__}"],
        }
    if not isinstance(payload, dict):
        issues.append("package_must_be_object")
        payload = {}
    issues.extend(_common_package(package, payload, "funding_payment_events"))
    _authority_documents(package, payload, issues)
    selected = set(pairs or payload.get("pairs", []))
    if not selected:
        issues.append("target_pairs_required")
    events = payload.get("events", [])
    rules = payload.get("rules", [])
    coverage_documents = payload.get("coverage_documents")
    if not isinstance(events, list) or not events:
        issues.append("events_required")
        events = []
    if not isinstance(rules, list) or not rules:
        issues.append("rules_required")
        rules = []
    event_ids: set[str] = set()
    seen_identity: set[tuple[str, str, str]] = set()
    parsed_events: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict) or not _FUNDING_EVENT_FIELDS <= set(event):
            issues.append("funding_event_required_fields_missing")
            continue
        event_id = event["event_id"]
        canonical_time = _canonical_time(event["event_time_utc"], "event_time_utc")
        identity = (event["instrument_id"], event["pair"], canonical_time)
        if event_id in event_ids or identity in seen_identity:
            issues.append("duplicate_funding_event")
        event_ids.add(event_id)
        seen_identity.add(identity)
        try:
            timestamp = _timestamp(event["event_time_utc"], "event_time_utc")
            rate = float(event["funding_rate"])
            if not math.isfinite(rate):
                raise ValueError
            _timestamp(event["retrieved_at_utc"], "retrieved_at_utc")
        except (DataContractError, TypeError, ValueError, OverflowError):
            issues.append("invalid_funding_event_value")
            continue
        _authority(event["evidence_grade"], event["source_type"], issues)
        _source_check(package, event, issues)
        _source_record_match(package, event, issues)
        parsed_events.append({**event, "_time": timestamp, "_event_time": timestamp})
    rule_intervals = _intervals(rules, "effective_from_utc", "effective_to_utc", issues)
    for index, left in enumerate(rule_intervals):
        for right in rule_intervals[index + 1 :]:
            left_identity = tuple(
                left[2].get(key)
                for key in ("venue", "instrument_id", "rule_id", "rule_version")
            )
            right_identity = tuple(
                right[2].get(key)
                for key in ("venue", "instrument_id", "rule_id", "rule_version")
            )
            if left_identity == right_identity and left[0] < right[1] and right[0] < left[1]:
                issues.append("overlapping_funding_rule_intervals")
    for rule_identity in {
        tuple(item.get(key) for key in ("venue", "instrument_id", "rule_id", "rule_version"))
        for item in rules
        if isinstance(item, dict)
    }:
        ordered = sorted(
            (
                item
                for item in rule_intervals
                if tuple(
                    item[2].get(key)
                    for key in ("venue", "instrument_id", "rule_id", "rule_version")
                )
                == rule_identity
            ),
            key=lambda item: item[0],
        )
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] > previous[1]:
                issues.append("funding_rule_interval_gap")
    for rule in rules:
        if not isinstance(rule, dict) or not _RULE_FIELDS <= set(rule):
            issues.append("funding_rule_required_fields_missing")
            continue
        _source_check(package, rule, issues)
        for event in parsed_events:
            if (
                event["venue"] == rule["venue"]
                and event["instrument_id"] == rule["instrument_id"]
                and event["settlement_rule_id"] == rule["rule_id"]
                and event["settlement_rule_version"] == rule["rule_version"]
                and _timestamp(rule["effective_from_utc"], "effective_from_utc")
                <= event["_event_time"]
                < (
                    _timestamp(rule["effective_to_utc"], "effective_to_utc")
                    if rule.get("effective_to_utc")
                    else pd.Timestamp.max.tz_localize("UTC")
                )
            ):
                break
    for event in parsed_events:
        if selected and event["pair"] not in selected:
            issues.append("event_outside_requested_pairs")
        matching = [
            rule
            for rule in rules
            if rule.get("venue") == event["venue"]
            and rule.get("instrument_id") == event["instrument_id"]
            and rule.get("rule_id") == event["settlement_rule_id"]
            and rule.get("rule_version") == event["settlement_rule_version"]
            and _timestamp(rule["effective_from_utc"], "effective_from_utc")
            <= event["_event_time"]
            < (
                _timestamp(rule["effective_to_utc"], "effective_to_utc")
                if rule.get("effective_to_utc")
                else pd.Timestamp.max.tz_localize("UTC")
            )
        ]
        if len(matching) != 1:
            issues.append("event_without_exactly_one_applicable_rule")
    if mark_times is not None:
        for event in parsed_events:
            if event["event_time_utc"] not in set(mark_times.get(event["instrument_id"], [])):
                issues.append("funding_event_without_exact_mark_timestamp")
    window_start = _timestamp(start, "start") if start else None
    window_end = _timestamp(end, "end") if end else None
    coverage_status = "PASS"
    if not selected:
        coverage_status = "BLOCKED"
    if not isinstance(coverage_documents, list) or not coverage_documents:
        coverage_status = "BLOCKED"
        issues.append("independent_event_coverage_evidence_missing")
    for pair in selected:
        document = next(
            (item for item in coverage_documents or [] if item.get("pair") == pair), None
        )
        actual = {event["_event_time"] for event in parsed_events if event["pair"] == pair}
        expected_times: set[pd.Timestamp] = set()
        if document is None:
            issues.append(f"independent_event_coverage_missing:{pair}")
        else:
            try:
                source = _source_path(package, document["source_uri"])
                if _sha256(source) != document["raw_payload_sha256"]:
                    issues.append("coverage_source_hash_mismatch")
                raw = json.loads(source.read_text(encoding="utf-8"))
                expected_times = {
                    _timestamp(value, "coverage_event_time") for value in raw["event_times"]
                }
            except (OSError, ValueError, KeyError, TypeError, DataContractError):
                issues.append("coverage_source_invalid")
        if document is not None and expected_times != actual:
            coverage_status = "BLOCKED"
            issues.append(f"event_coverage_mismatch:{pair}")
        if window_start and window_end and not any(
            window_start <= event["_time"] < window_end
            for event in parsed_events
            if event["pair"] == pair
        ):
            coverage_status = "BLOCKED"
            issues.append(f"pair_outside_requested_window:{pair}")
    schema_status = "PASS" if not any(
        x in issues
        for x in (
            "unsupported_schema_version",
            "wrong_evidence_type",
            "events_required",
            "rules_required",
            "funding_event_required_fields_missing",
            "funding_rule_required_fields_missing",
        )
    ) else "FAIL"
    source_integrity_status = "PASS" if not any(
        x in issues
        for x in (
            "source_documents_required",
            "source_document_locator_missing",
            "source_missing",
            "coverage_source_hash_mismatch",
            "coverage_source_invalid",
        )
    ) and not any(
        "hash_mismatch" in x or "missing_or_invalid_raw_payload_sha256" in x
        for x in issues
    ) else "FAIL"
    source_authority_status = (
        "PASS"
        if not any(
            "authority_" in x
            or "inferred_or_current" in x
            or "invalid_evidence_grade" in x
            for x in issues
        )
        and all(event["evidence_grade"] in AUTHORITATIVE_GRADES for event in parsed_events)
        else "BLOCKED"
    )
    formal = (
        schema_status == source_integrity_status == "PASS"
        and source_authority_status == "PASS"
        and coverage_status == "PASS"
        and not issues
        and payload.get("synthetic_fixture") is not True
    )
    return {
        "schema_status": schema_status,
        "provenance_status": source_integrity_status,
        "source_integrity_status": source_integrity_status,
        "source_authority_status": source_authority_status,
        "historical_coverage_status": coverage_status,
        "formal_admission_ready": formal,
        "event_count": len(parsed_events),
        "rule_count": len(rules),
        "issues": sorted(set(issues)),
        "status": "PASS" if formal else "BLOCKED",
    }


def validate_universe_package(
    package_path: str | Path,
    *,
    pairs: Iterable[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    candle_times: dict[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Validate non-overlapping as-of state intervals and source evidence."""
    package = Path(package_path).resolve()
    issues: list[str] = []
    try:
        payload = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "schema_status": "FAIL",
            "provenance_status": "FAIL",
            "historical_coverage_status": "BLOCKED",
            "formal_admission_ready": False,
            "issues": [f"package_unreadable:{type(exc).__name__}"],
        }
    if not isinstance(payload, dict):
        payload = {}; issues.append("package_must_be_object")
    issues.extend(_common_package(package, payload, "point_in_time_universe"))
    _authority_documents(package, payload, issues)
    records = payload.get("records", [])
    if not isinstance(records, list) or not records:
        issues.append("universe_records_required"); records = []
    selected = set(pairs or payload.get("pairs", []))
    if not selected:
        issues.append("target_pairs_required")
    parsed = []
    for record in records:
        if not isinstance(record, dict) or not _UNIVERSE_FIELDS <= set(record):
            issues.append("universe_record_required_fields_missing"); continue
        if record["trading_status"] not in UNIVERSE_STATES:
            issues.append("invalid_trading_status")
        _authority(record["evidence_grade"], record["source_type"], issues)
        _source_check(package, record, issues)
        try:
            start_time = _timestamp(record["effective_from_utc"], "effective_from_utc")
            end_time = (
                _timestamp(record["effective_to_utc"], "effective_to_utc")
                if record.get("effective_to_utc")
                else pd.Timestamp.max.tz_localize("UTC")
            )
            if end_time <= start_time: issues.append("invalid_effective_interval")
            parsed.append((record["instrument_id"], start_time, end_time, record))
        except (DataContractError, TypeError, ValueError):
            issues.append("invalid_universe_interval")
    for instrument in {x[0] for x in parsed}:
        rows = sorted((x for x in parsed if x[0] == instrument), key=lambda x: x[1])
        for previous, current in zip(rows, rows[1:]):
            if current[1] < previous[2]: issues.append("overlapping_universe_intervals")
            if current[1] > previous[2]: issues.append("universe_interval_gap")
    ws = _timestamp(start, "start") if start else None
    we = _timestamp(end, "end") if end else None
    if candle_times is not None:
        for instrument, times in candle_times.items():
            for raw in times:
                stamp = _timestamp(raw, "candle_time")
                if not any(i == instrument and a <= stamp < b for i, a, b, _ in parsed):
                    issues.append(f"unknown_as_of_state:{instrument}:{stamp.isoformat()}")
    else:
        issues.append("historical_candle_times_required")
    if any(record[3].get("trading_status") == "unknown" for record in parsed):
        issues.append("unknown_universe_status")
    if selected and any(x[3].get("pair") not in selected for x in parsed):
        issues.append("record_outside_requested_pairs")
    if ws and we and any(not (a < we and ws < b) for _, a, b, _ in parsed):
        issues.append("records_outside_requested_window")
    schema_status = "PASS" if not any(
        x in issues
        for x in (
            "unsupported_schema_version",
            "wrong_evidence_type",
            "universe_records_required",
            "universe_record_required_fields_missing",
        )
    ) else "FAIL"
    source_integrity_status = (
        "PASS"
        if not any(
            x in issues
            for x in (
                "source_documents_required",
                "source_document_locator_missing",
                "source_missing",
            )
        )
        and not any(
            "hash_mismatch" in x or "missing_or_invalid_raw_payload_sha256" in x
            for x in issues
        )
        else "FAIL"
    )
    source_authority_status = (
        "PASS"
        if not any(
            "authority_" in x
            or "inferred_or_current" in x
            or "invalid_evidence_grade" in x
            for x in issues
        )
        and all(record[3]["evidence_grade"] in AUTHORITATIVE_GRADES for record in parsed)
        else "BLOCKED"
    )
    coverage_status = (
        "PASS"
        if not any(
            "overlapping" in x
            or "gap" in x
            or "unknown_as_of" in x
            or "historical_candle_times_required" in x
            or "unknown_universe_status" in x
            or "target_pairs_required" in x
            for x in issues
        )
        else "BLOCKED"
    )
    formal = (
        schema_status == source_integrity_status == "PASS"
        and source_authority_status == "PASS"
        and coverage_status == "PASS"
        and not issues
        and payload.get("synthetic_fixture") is not True
    )
    return {
        "schema_status": schema_status,
        "provenance_status": source_integrity_status,
        "source_integrity_status": source_integrity_status,
        "source_authority_status": source_authority_status,
        "historical_coverage_status": coverage_status,
        "formal_admission_ready": formal,
        "record_count": len(parsed),
        "issues": sorted(set(issues)),
        "status": "PASS" if formal else "BLOCKED",
    }
