"""Fail-closed snapshot tests use recorded genuine metadata, never live API access."""

import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import ccxt
import pytest

from quant_strategy.execution import market_snapshot as module

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "docs/baseline/acceptance/binance-usdt-market-snapshot.json"
)
PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]


@pytest.fixture
def snapshot():
    return json.loads(SOURCE.read_text())


def write_snapshot(path, value):
    value = deepcopy(value)
    value.pop("sha256", None)
    value["sha256"] = module.digest(value)
    path.write_text(json.dumps(value))
    return path


@pytest.mark.parametrize("content", ["", "{", "[]", "null", '{"x":1,"x":2}'])
def test_invalid_json_shape_is_rejected(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(module.SnapshotError):
        module.load_snapshot(path, PAIRS)


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "duplicate_pairs",
        "missing_pair",
        "ccxt",
        "freqtrade",
        "future",
        "invalid_time",
        "naive_time",
        "reversed_time",
    ],
)
def test_signed_but_invalid_envelopes_are_rejected(tmp_path, snapshot, change):
    if change == "unknown":
        snapshot["unknown"] = True
    elif change == "duplicate_pairs":
        snapshot["pairs"].append(PAIRS[0])
    elif change == "missing_pair":
        snapshot["pairs"] = [PAIRS[0]]
    elif change in {"ccxt", "freqtrade"}:
        snapshot["versions"][change] = "unsupported"
    elif change == "future":
        snapshot["acquired_at"] = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    elif change == "invalid_time":
        snapshot["acquired_at"] = "not a timestamp"
    elif change == "naive_time":
        snapshot["acquired_at"] = "2026-10-17T12:04:06"
    elif change == "reversed_time":
        snapshot["request_started_at"] = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    with pytest.raises(module.SnapshotError):
        module.load_snapshot(write_snapshot(tmp_path / "bad.json", snapshot), PAIRS, 36500)


@pytest.mark.parametrize("rule", ["PRICE_FILTER", "LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL"])
def test_ccxt_fallback_cannot_hide_missing_raw_filters(snapshot, rule):
    market = next(m for m in snapshot["raw_response"]["symbols"] if m["symbol"] == "BTCUSDT")
    market["filters"] = [f for f in market["filters"] if f["filterType"] != rule]
    with pytest.raises(module.SnapshotError, match="Missing market rule"):
        module.parse_response(snapshot["raw_response"], PAIRS)


@pytest.mark.parametrize("field", ["precision", "limits", "contractSize"])
def test_missing_normalized_rules_rejected(tmp_path, snapshot, field):
    del snapshot["normalized"]["markets"][PAIRS[0]][field]
    with pytest.raises(module.SnapshotError, match="Normalized rules"):
        module.load_snapshot(write_snapshot(tmp_path / "bad.json", snapshot), PAIRS, 36500)


@pytest.mark.parametrize(
    "change", ["duplicate_symbol", "duplicate_filter", "invalid_number", "missing_leverage"]
)
def test_missing_or_ambiguous_rules_rejected(tmp_path, snapshot, change):
    market = next(m for m in snapshot["raw_response"]["symbols"] if m["symbol"] == "BTCUSDT")
    if change == "missing_leverage":
        del snapshot["leverage_rules"]["pairs"][PAIRS[0]]
    elif change == "duplicate_symbol":
        snapshot["raw_response"]["symbols"].append(deepcopy(market))
    elif change == "duplicate_filter":
        market["filters"].append(deepcopy(market["filters"][0]))
    else:
        next(f for f in market["filters"] if f["filterType"] == "LOT_SIZE")["stepSize"] = "NaN"
    snapshot["raw_sha256"] = module.digest(snapshot["raw_response"])
    with pytest.raises(module.SnapshotError):
        module.load_snapshot(write_snapshot(tmp_path / "bad.json", snapshot), PAIRS, 36500)


@pytest.fixture
def replay_api(monkeypatch, snapshot):
    # Capture unit tests replay a recorded response; these are not online acceptance.
    monkeypatch.setattr(
        ccxt.binance, "fapiPublicGetExchangeInfo", lambda self: snapshot["raw_response"]
    )


@pytest.mark.parametrize("error", [ccxt.RequestTimeout("timeout"), ccxt.ExchangeError("API error")])
def test_capture_api_errors_leave_no_file(tmp_path, monkeypatch, error):
    def fail(self):
        raise error

    monkeypatch.setattr(ccxt.binance, "fapiPublicGetExchangeInfo", fail)
    with pytest.raises(module.SnapshotError, match="acquisition failed"):
        module.capture_snapshot(tmp_path / "markets.json", PAIRS)
    assert not list(tmp_path.iterdir())


def test_capture_incomplete_response_leaves_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ccxt.binance, "fapiPublicGetExchangeInfo", lambda self: {"symbols": []})
    with pytest.raises(module.SnapshotError):
        module.capture_snapshot(tmp_path / "markets.json", PAIRS)
    assert not list(tmp_path.iterdir())


def test_capture_does_not_overwrite_or_follow_symlinks(tmp_path, monkeypatch):
    def forbidden(self):
        pytest.fail("Existing snapshot must fail before API access")

    monkeypatch.setattr(ccxt.binance, "fapiPublicGetExchangeInfo", forbidden)
    existing = tmp_path / "existing.json"
    existing.write_text("trusted")
    symlink = tmp_path / "link.json"
    symlink.symlink_to(tmp_path / "absent.json")
    for path in (existing, symlink):
        with pytest.raises(module.SnapshotError):
            module.capture_snapshot(path, PAIRS)
    assert existing.read_text() == "trusted" and not (tmp_path / "absent.json").exists()


@pytest.mark.parametrize("failure", ["write", "sync", "publish"])
def test_atomic_publication_failure_cleans_temporary_and_never_leaves_final(
    tmp_path, monkeypatch, replay_api, failure
):
    def fail(*args, **kwargs):
        if failure == "write":
            args[1].write("{")
        raise OSError("injected I/O interruption")

    if failure == "write":
        monkeypatch.setattr(module.json, "dump", fail)
    elif failure == "sync":
        monkeypatch.setattr(module.os, "fsync", fail)
    else:
        monkeypatch.setattr(module.os, "link", fail)
    with pytest.raises(module.SnapshotError, match="atomically publish"):
        module.capture_snapshot(tmp_path / "markets.json", PAIRS)
    assert not list(tmp_path.iterdir())


def test_atomic_publication_rejects_concurrent_writer_and_ignores_stale_temp(tmp_path, snapshot):
    final = tmp_path / "markets.json"
    stale = tmp_path / ".markets.json.dead.tmp"
    stale.write_text("{")
    module.publish_snapshot(final, snapshot)
    assert module.load_snapshot(final, PAIRS, 36500)["sha256"] == snapshot["sha256"]
    with pytest.raises(module.SnapshotError):
        module.publish_snapshot(final, {"wrong": "writer"})
    assert json.loads(final.read_text()) == snapshot
    assert stale.read_text() == "{" and len(list(tmp_path.iterdir())) == 2


def test_capture_rejects_duplicate_pair_scope_before_api(tmp_path):
    with pytest.raises(module.SnapshotError, match="unique"):
        module.capture_snapshot(tmp_path / "markets.json", [PAIRS[0], PAIRS[0]])


@pytest.mark.parametrize(
    "bad_tiers",
    [
        {},
        {PAIRS[0]: [], PAIRS[1]: []},
        {
            PAIRS[0]: [
                {"minNotional": 0, "maxNotional": 1, "maxLeverage": 0, "maintenanceMarginRate": 0.1}
            ],
            PAIRS[1]: [],
        },
    ],
)
def test_missing_or_invalid_native_leverage_file_fails(tmp_path, monkeypatch, bad_tiers):
    import freqtrade.exchange.binance as native

    monkeypatch.setattr(native, "__file__", str(tmp_path / "binance.py"))
    (tmp_path / "binance_leverage_tiers.json").write_text(json.dumps(bad_tiers))
    with pytest.raises(module.SnapshotError):
        module.leverage_rules(PAIRS)


def test_killed_writer_leaves_only_unusable_temp_not_final(tmp_path):
    final = tmp_path / "markets.json"
    marker = tmp_path / "writing"
    script = """
import sys,time
from pathlib import Path
from quant_strategy.execution import market_snapshot as module
def interruptible_dump(value, handle, **kwargs):
    handle.write("{"); handle.flush()
    Path(sys.argv[2]).write_text("started")
    time.sleep(30)
module.json.dump=interruptible_dump
module.publish_snapshot(Path(sys.argv[1]), {"value":1})
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(final), str(marker)],
        env={**os.environ, "PYTHONPATH": str(SOURCE.parents[3] / "src")},
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "Writer failed to reach the interrupted-write point"
        process.kill()
        process.wait(timeout=5)
        assert not final.exists()
        temporary = list(tmp_path.glob(".markets.json.*.tmp"))
        assert len(temporary) == 1 and temporary[0].read_text() == "{"
        with pytest.raises(module.SnapshotError):
            module.load_snapshot(temporary[0], PAIRS)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize(
    "failure", ["schema_boolean", "authentication_number", "age_boolean", "order_types_string"]
)
def test_json_primitive_types_do_not_coerce_to_valid_contracts(tmp_path, snapshot, failure):
    age = 36500
    if failure == "schema_boolean":
        snapshot["schema_version"] = True
    elif failure == "authentication_number":
        snapshot["source"]["authenticated"] = 0
    elif failure == "age_boolean":
        age = True
    else:
        next(m for m in snapshot["raw_response"]["symbols"] if m["symbol"] == "BTCUSDT")[
            "orderTypes"
        ] = "LIMIT"
        snapshot["raw_sha256"] = module.digest(snapshot["raw_response"])
    with pytest.raises(module.SnapshotError):
        module.load_snapshot(write_snapshot(tmp_path / "bad.json", snapshot), PAIRS, age)


@pytest.mark.parametrize("field,value", [("contractSize", True), ("linear", 1), ("swap", 1)])
def test_normalized_market_types_are_strict(tmp_path, snapshot, field, value):
    snapshot["normalized"]["markets"][PAIRS[0]][field] = value
    with pytest.raises(module.SnapshotError, match="Normalized rules"):
        module.load_snapshot(write_snapshot(tmp_path / "bad.json", snapshot), PAIRS, 36500)


def test_recorded_leverage_primitive_types_are_strict(tmp_path, snapshot):
    snapshot["leverage_rules"]["pairs"][PAIRS[0]][0]["tier"] = True
    with pytest.raises(module.SnapshotError, match="leverage bundle"):
        module.load_snapshot(write_snapshot(tmp_path / "bad.json", snapshot), PAIRS, 36500)
