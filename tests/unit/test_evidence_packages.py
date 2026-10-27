"""Synthetic-only tests for the Funding and PIT-universe evidence contracts."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quant.research.evidence import validate_funding_package, validate_universe_package


def _raw(root: Path, name: str, content: str = "authoritative raw response\n") -> tuple[str, str]:
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path.name, hashlib.sha256(path.read_bytes()).hexdigest()


def _funding(root: Path) -> Path:
    times = ["2025-01-01T00:00:00+00:00", "2025-01-01T08:00:00+00:00"]
    event_records = {
        "records": [
            {
                "source_record_id": f"record-{index}",
                "event_time_utc": stamp,
                "funding_rate": 0.0001,
                "instrument_id": "BTCUSDT-PERP",
                "venue": "fixture_venue",
            }
            for index, stamp in enumerate(times)
        ]
    }
    event_path = root / "funding-source.json"
    event_path.write_text(json.dumps(event_records), encoding="utf-8")
    event_source, event_sha = event_path.name, hashlib.sha256(event_path.read_bytes()).hexdigest()
    rule_source, rule_sha = _raw(root, "funding-rule.json")
    coverage_path = root / "funding-coverage.json"
    coverage_path.write_text(json.dumps({"event_times": times}), encoding="utf-8")
    coverage_source = coverage_path.name
    coverage_sha = hashlib.sha256(coverage_path.read_bytes()).hexdigest()
    events = [
        {
            "schema_version": 1,
            "event_id": f"btc-{index}",
            "venue": "fixture_venue",
            "instrument_id": "BTCUSDT-PERP",
            "pair": "BTC/USDT:USDT",
            "event_time_utc": stamp,
            "funding_rate": 0.0001,
            "settlement_rule_id": "fixture-8h",
            "settlement_rule_version": "1",
            "source_type": "authoritative_archive",
            "source_uri": event_source,
            "retrieved_at_utc": "2025-01-02T00:00:00+00:00",
            "raw_payload_sha256": event_sha,
            "source_record_id": f"record-{index}",
            "parser_version": "fixture-parser-1",
            "transformation_version": "fixture-transform-1",
            "evidence_grade": "authoritative_archive",
        }
        for index, stamp in enumerate(times)
    ]
    payload = {
        "schema_version": 1,
        "evidence_type": "funding_payment_events",
        "synthetic_fixture": True,
        "pairs": ["BTC/USDT:USDT"],
        "source_documents": [
            {"source_uri": event_source, "sha256": event_sha},
            {"source_uri": rule_source, "sha256": rule_sha},
            {"source_uri": coverage_source, "sha256": coverage_sha},
        ],
        "authority_documents": [
            {
                "source_uri": event_source,
                "verification_method": "independent_archive_chain",
                "authority_reference": "fixture-independent-attestation",
            }
        ],
        "coverage_documents": [
            {
                "pair": "BTC/USDT:USDT",
                "source_uri": coverage_source,
                "raw_payload_sha256": coverage_sha,
            }
        ],
        "rules": [
            {
                "rule_id": "fixture-8h",
                "rule_version": "1",
                "venue": "fixture_venue",
                "instrument_id": "BTCUSDT-PERP",
                "effective_from_utc": "2025-01-01T00:00:00+00:00",
                "effective_to_utc": None,
                "source_uri": rule_source,
                "raw_payload_sha256": rule_sha,
                "retrieved_at_utc": "2025-01-02T00:00:00+00:00",
                "parser_version": "fixture-parser-1",
            }
        ],
        "events": events,
    }
    path = root / "funding.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _universe(root: Path) -> Path:
    source, digest = _raw(root, "universe-source.json")
    payload = {
        "schema_version": 1,
        "evidence_type": "point_in_time_universe",
        "synthetic_fixture": True,
        "pairs": ["BTC/USDT:USDT"],
        "source_documents": [{"source_uri": source, "sha256": digest}],
        "authority_documents": [
            {
                "source_uri": source,
                "verification_method": "independent_archive_chain",
                "authority_reference": "fixture-independent-attestation",
            }
        ],
        "records": [
            {
                "schema_version": 1,
                "venue": "fixture_venue",
                "instrument_id": "BTCUSDT-PERP",
                "pair": "BTC/USDT:USDT",
                "effective_from_utc": "2025-01-01T00:00:00+00:00",
                "effective_to_utc": "2025-01-02T00:00:00+00:00",
                "trading_status": "tradable",
                "status_reason": "fixture listing",
                "source_type": "authoritative_archive",
                "source_uri": source,
                "retrieved_at_utc": "2025-01-02T00:00:00+00:00",
                "raw_payload_sha256": digest,
                "rule_version": "1",
                "evidence_grade": "authoritative_archive",
            }
        ],
    }
    path = root / "universe.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_synthetic_funding_is_structurally_valid_but_not_formal(tmp_path):
    report = validate_funding_package(_funding(tmp_path), pairs=["BTC/USDT:USDT"])
    assert report["schema_status"] == "PASS"
    assert report["provenance_status"] == "PASS"
    assert report["historical_coverage_status"] == "PASS"
    assert report["formal_admission_ready"] is False
    assert report["status"] == "BLOCKED"


def test_funding_requires_exact_mark_event_time(tmp_path):
    report = validate_funding_package(
        _funding(tmp_path),
        pairs=["BTC/USDT:USDT"],
        mark_times={"BTCUSDT-PERP": ["2025-01-01T00:00:00+00:00"]},
    )
    assert report["status"] == "BLOCKED"
    assert "funding_event_without_exact_mark_timestamp" in report["issues"]


def test_equivalent_utc_offsets_are_one_event_identity(tmp_path):
    path = _funding(tmp_path)
    payload = json.loads(path.read_text())
    payload["events"][1]["event_time_utc"] = "2024-12-31T19:00:00-05:00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_funding_package(path, pairs=["BTC/USDT:USDT"])
    assert "duplicate_funding_event" in report["issues"]


@pytest.mark.parametrize("field", ["venue", "settlement_rule_id"])
def test_funding_rule_identity_fields_are_required_for_matching(tmp_path, field):
    path = _funding(tmp_path)
    payload = json.loads(path.read_text())
    if field == "venue":
        payload["rules"][0][field] = "other"
    else:
        payload["events"][0][field] = "other"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_funding_package(path, pairs=["BTC/USDT:USDT"])
    assert "event_without_exactly_one_applicable_rule" in report["issues"]


def test_authoritative_label_without_independent_proof_is_blocked(tmp_path):
    path = _funding(tmp_path)
    payload = json.loads(path.read_text())
    payload.pop("authority_documents")
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_funding_package(path, pairs=["BTC/USDT:USDT"])
    assert report["source_integrity_status"] == "PASS"
    assert report["source_authority_status"] == "BLOCKED"
    assert report["formal_admission_ready"] is False


def test_expected_event_times_alone_do_not_prove_coverage(tmp_path):
    path = _funding(tmp_path)
    payload = json.loads(path.read_text())
    payload.pop("coverage_documents")
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_funding_package(path, pairs=["BTC/USDT:USDT"])
    assert report["historical_coverage_status"] == "BLOCKED"


def test_source_hash_match_with_changed_event_content_is_rejected(tmp_path):
    path = _funding(tmp_path)
    payload = json.loads(path.read_text())
    payload["events"][0]["funding_rate"] = 0.5
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_funding_package(path, pairs=["BTC/USDT:USDT"])
    assert "source_record_event_content_mismatch" in report["issues"]


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("hash", "source_hash_mismatch"),
        ("duplicate", "duplicate_funding_event"),
        ("missing_rule", "event_without_exactly_one_applicable_rule"),
        ("current", "inferred_or_current_source_cannot_prove_history"),
        ("source", "funding_event_required_fields_missing"),
    ],
)
def test_funding_faults_fail_closed(tmp_path, fault, expected):
    path = _funding(tmp_path)
    payload = json.loads(path.read_text())
    if fault == "hash":
        payload["events"][0]["raw_payload_sha256"] = "0" * 64
    elif fault == "duplicate":
        payload["events"].append(dict(payload["events"][0]))
    elif fault == "missing_rule":
        payload["events"][0]["settlement_rule_version"] = "missing"
    elif fault == "current":
        payload["events"][0]["source_type"] = "current_exchange_info"
    else:
        payload["events"][0].pop("source_uri")
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_funding_package(path, pairs=["BTC/USDT:USDT"])
    assert report["status"] == "BLOCKED"
    assert any(expected in issue for issue in report["issues"])


def test_synthetic_universe_is_structurally_valid_but_not_formal(tmp_path):
    report = validate_universe_package(
        _universe(tmp_path),
        pairs=["BTC/USDT:USDT"],
        candle_times={"BTCUSDT-PERP": ["2025-01-01T12:00:00+00:00"]},
    )
    assert report["schema_status"] == "PASS"
    assert report["provenance_status"] == "PASS"
    assert report["historical_coverage_status"] == "PASS"
    assert report["formal_admission_ready"] is False


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("overlap", "overlapping_universe_intervals"),
        ("unknown", "unknown_as_of_state"),
        ("snapshot", "inferred_or_current_source_cannot_prove_history"),
        ("hash", "source_hash_mismatch"),
    ],
)
def test_universe_faults_fail_closed(tmp_path, fault, expected):
    path = _universe(tmp_path)
    payload = json.loads(path.read_text())
    if fault == "overlap":
        payload["records"].append(
            dict(
                payload["records"][0],
                effective_from_utc="2025-01-01T12:00:00+00:00",
            )
        )
    elif fault == "unknown":
        pass
    elif fault == "snapshot":
        payload["records"][0]["source_type"] = "current_exchange_info"
    else:
        payload["records"][0]["raw_payload_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_universe_package(
        path,
        pairs=["BTC/USDT:USDT"],
        candle_times={"BTCUSDT-PERP": ["2024-12-31T23:00:00+00:00"]}
        if fault == "unknown"
        else None,
    )
    if fault == "unknown":
        assert any(expected in issue for issue in report["issues"])
    else:
        assert any(expected in issue for issue in report["issues"])
    assert report["status"] == "BLOCKED"


def test_unknown_as_of_state_is_rejected(tmp_path):
    report = validate_universe_package(
        _universe(tmp_path),
        pairs=["BTC/USDT:USDT"],
        candle_times={"BTCUSDT-PERP": ["2024-12-31T23:00:00+00:00"]},
    )
    assert report["status"] == "BLOCKED"
    assert any("unknown_as_of_state" in issue for issue in report["issues"])


def test_universe_requires_historical_candle_input(tmp_path):
    report = validate_universe_package(_universe(tmp_path), pairs=["BTC/USDT:USDT"])
    assert report["historical_coverage_status"] == "BLOCKED"
    assert "historical_candle_times_required" in report["issues"]


def test_universe_requested_window_requires_covered_candles(tmp_path):
    report = validate_universe_package(
        _universe(tmp_path),
        pairs=["BTC/USDT:USDT"],
        start="2025-01-01T00:00:00+00:00",
        end="2025-01-03T00:00:00+00:00",
        candle_times={
            "BTCUSDT-PERP": [
                "2025-01-01T12:00:00+00:00",
                "2025-01-02T12:00:00+00:00",
            ]
        },
    )
    assert report["historical_coverage_status"] == "BLOCKED"
    assert any("unknown_as_of_state" in issue for issue in report["issues"])


def test_cli_recomputes_synthetic_package_and_returns_blocked(tmp_path):
    package = _funding(tmp_path)
    environment = {**os.environ, "PYTHONPATH": "."}
    result = subprocess.run(
        [
            sys.executable,
            "tools/validate_evidence.py",
            "--funding",
            str(package),
            "--pairs",
            "BTC/USDT:USDT",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 2
    output = json.loads(result.stdout)
    assert output["funding"]["status"] == "BLOCKED"
    assert output["funding"]["formal_admission_ready"] is False
