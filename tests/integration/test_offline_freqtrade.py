"""Real metadata and native backtesting must work without HTTP/DNS/IP networking.

The committed reference contains only trusted locally generated regression artifacts;
it is never used as a model or as market metadata by the production adapter.
"""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from freqtrade.enums import RunMode

from quant.execution.market_snapshot import SnapshotError, digest, load_snapshot
from quant.execution.offline_backtest import (
    LocalBinanceAsyncClient,
    LocalBinanceClient,
    OfflineNetworkError,
    SnapshotBinance,
)
from tools.verify_freqtrade_regression import compare_runs

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/baseline/acceptance"
SNAPSHOT = EVIDENCE / "binance-usdt-market-snapshot.json"
PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]


@pytest.fixture
def native_config():
    config = json.loads((ROOT / "config.json").read_text())
    config["runmode"] = RunMode.BACKTEST
    config["exchange"]["pair_whitelist"] = PAIRS.copy()
    return config


def test_genuine_snapshot_preserves_raw_rules():
    snapshot = load_snapshot(SNAPSHOT, PAIRS, max_age_days=36500)
    btc = snapshot["normalized"]["markets"][PAIRS[0]]
    filters = {item["filterType"]: item for item in btc["info"]["filters"]}
    assert btc["precision"]["price"] == float(filters["PRICE_FILTER"]["tickSize"])
    assert btc["precision"]["amount"] == float(filters["LOT_SIZE"]["stepSize"])
    assert btc["limits"]["amount"]["min"] == float(filters["LOT_SIZE"]["minQty"])
    assert snapshot["leverage_rules"]["pairs"][PAIRS[0]]


@pytest.mark.parametrize(
    "failure", ["checksum", "normalized", "raw", "version", "exchange", "leverage", "expired"]
)
def test_invalid_snapshots_fail_closed_even_with_updated_envelope(tmp_path, failure):
    snapshot = json.loads(SNAPSHOT.read_text())
    if failure in {"checksum", "normalized"}:
        snapshot["normalized"]["markets"][PAIRS[0]]["contractSize"] = 12345
    elif failure == "raw":
        snapshot["raw_response"]["symbols"][0]["symbol"] = "CORRUPTED"
    elif failure == "version":
        snapshot["versions"]["ccxt"] = "unsupported"
    elif failure == "exchange":
        snapshot["exchange"] = "other"
    elif failure == "leverage":
        snapshot["leverage_rules"]["sha256"] = "0" * 64
    elif failure == "expired":
        timestamp = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        snapshot["request_started_at"] = snapshot["acquired_at"] = timestamp
    if failure != "checksum":
        snapshot.pop("sha256")
        snapshot["sha256"] = digest(snapshot)
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(snapshot))
    with pytest.raises(SnapshotError):
        load_snapshot(path, PAIRS)


def test_missing_duplicate_json_and_incomplete_pair_scope_fail(tmp_path):
    with pytest.raises(SnapshotError, match="Cannot validate"):
        load_snapshot(tmp_path / "absent.json", PAIRS)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version": 1, "schema_version": 1}')
    with pytest.raises(SnapshotError, match="Duplicate JSON key"):
        load_snapshot(duplicate, PAIRS)
    with pytest.raises(SnapshotError, match="pair scope"):
        load_snapshot(SNAPSHOT, ["SOL/USDT:USDT"], max_age_days=36500)


@pytest.mark.parametrize("mode", [RunMode.LIVE, RunMode.DRY_RUN, RunMode.HYPEROPT])
def test_adapter_rejects_non_backtest_modes_before_exchange_init(native_config, mode):
    native_config["runmode"] = mode
    with pytest.raises(SnapshotError, match="only in RunMode.BACKTEST"):
        SnapshotBinance(native_config, SNAPSHOT)


def test_native_validation_refresh_and_network_guard(native_config):
    exchange = SnapshotBinance(native_config, SNAPSHOT, max_age_days=36500)
    try:
        assert native_config["dry_run"]
        assert exchange._leverage_tiers[PAIRS[0]]
        before = dict(exchange.markets)
        exchange.reload_markets(force=True)
        assert dict(exchange.markets) == before
        assert isinstance(exchange._api, LocalBinanceClient)
        assert isinstance(exchange._api_async, LocalBinanceAsyncClient)
        with pytest.raises(OfflineNetworkError):
            exchange._api.fetch("https://fapi.binance.com/fapi/v1/exchangeInfo")
        with pytest.raises(OfflineNetworkError):
            exchange.loop.run_until_complete(exchange._api_async.fetch("https://fapi.binance.com"))
    finally:
        exchange.close()


def test_native_timeframe_validation_is_not_bypassed(native_config):
    from freqtrade.exceptions import OperationalException

    native_config["timeframe"] = "7h"
    with pytest.raises(OperationalException, match="7h"):
        SnapshotBinance(native_config, SNAPSHOT, max_age_days=36500)


def test_regular_exchange_and_ccxt_classes_keep_native_network_methods():
    import ccxt
    import ccxt.pro
    from freqtrade.exchange import Exchange
    from freqtrade.exchange.binance import Binance

    assert Binance._init_ccxt is Exchange._init_ccxt
    assert Binance._api_reload_markets is Exchange._api_reload_markets
    assert ccxt.binance.fetch is not LocalBinanceClient.fetch
    assert ccxt.pro.binance.fetch is not LocalBinanceAsyncClient.fetch
    assert asyncio.iscoroutinefunction(LocalBinanceAsyncClient.fetch)


def offline_command(tmp_path, snapshot):
    userdir = tmp_path / "run"
    (userdir / "results").mkdir(parents=True)
    report = tmp_path / "audit.json"
    command = [
        sys.executable,
        str(ROOT / "tools/audit_local_network.py"),
        "--policy",
        "deny-all",
        "--report",
        str(report),
        "offline-backtest",
        "backtesting",
        "--snapshot",
        str(snapshot),
        "--snapshot-max-age-days",
        "36500",
        "--",
        "-c",
        str(ROOT / "config.json"),
        "-c",
        str(ROOT / "configs/backtest-local.json"),
        "-c",
        str(ROOT / "configs/environment/freqtrade-mihomo.json"),
        "--userdir",
        str(userdir),
        "--datadir",
        str(ROOT / "data"),
        "--strategy-path",
        str(ROOT),
        "--freqaimodel-path",
        str(ROOT / "quant" / "models" / "freqai"),
        "--strategy",
        "MyStrategy",
        "--timerange",
        "20250101-20250115",
        "--pairs",
        *PAIRS,
        "--cache",
        "none",
        "--export",
        "signals",
        "--backtest-directory",
        str(userdir / "results"),
    ]
    return command, report, userdir


def run_audited(command, *, extra_environment=None):
    return subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT), **(extra_environment or {})},
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_native_entry_rejects_missing_or_corrupt_snapshot_without_network(tmp_path, failure):
    snapshot = tmp_path / "snapshot.json"
    if failure == "corrupt":
        snapshot.write_text('{"broken": true}')
    command, report, userdir = offline_command(tmp_path, snapshot)
    result = run_audited(command)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Cannot validate market snapshot" in result.stderr
    evidence = json.loads(report.read_text())
    assert evidence["http_requests"] == evidence["socket_events"] == []
    assert not list(userdir.rglob("*.zip"))


def test_native_backtest_in_disconnected_namespace_matches_online_reference(tmp_path):
    """Keep the old online/offline adapter baseline on its exact old trainer.

    This fixture is deliberately legacy-only. Corrected production training has
    a different sample set and must not pretend to reproduce the leaked model.
    No reference output, comparison tolerance or production class is modified.
    """
    required = ROOT / "data/futures/BTC_USDT_USDT-4h-futures.feather"
    if not required.exists():
        pytest.skip("Real local historical data is required for native integration")
    if not shutil.which("unshare") or not shutil.which("strace"):
        pytest.skip("Kernel network isolation and syscall evidence require unshare/strace")
    prefix = ["unshare", "--user", "--map-root-user", "--net"]
    probe = subprocess.run([*prefix, "true"], capture_output=True, text=True)
    if probe.returncode:
        pytest.skip(f"Network namespace unavailable: {probe.stderr}")
    command, report, userdir = offline_command(tmp_path, SNAPSHOT)
    legacy = tmp_path / "frozen_legacy_model"
    legacy.mkdir()
    source = subprocess.check_output(
        [
            "git",
            "show",
            "4ba4fe83f46a0bd58b06f9765c3368eccd1b528f:freqaimodels/XGBoostRegressorES.py",
        ],
        cwd=ROOT,
    )
    assert (
        hashlib.sha256(source).hexdigest()
        == "0d32f7ca61cd4e643c530cf658585e53c1ba7d38c3104e2668a5a91aad33d7f2"
    )
    (legacy / "XGBoostRegressorES.py").write_bytes(source)
    command[command.index("--freqaimodel-path") + 1] = str(legacy)
    trace = tmp_path / "network.strace"
    result = run_audited(
        [*prefix, "strace", "-f", "-e", "trace=network", "-o", str(trace), *command],
        extra_environment={
            "FREQTRADE__FREQAI__IDENTIFIER": "mystrategy-4h-regression-72pair-corr-s1-v1"
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(report.read_text())
    assert evidence["exit_code"] == evidence["denied_operations"] == 0
    assert evidence["http_requests"] == evidence["socket_events"] == []
    # aiohttp's import-time IPv6 loopback bind probe is harmless; no connects or
    # sends are allowed even when the Python audit layer cannot see a C library.
    for line in trace.read_text().splitlines():
        assert not any(
            operation in line for operation in ("connect(", "sendto(", "sendmsg(", "sendmmsg(")
        ), line
    reference = tmp_path / "reference"
    with tarfile.open(EVIDENCE / "native-online-reference.tar.gz") as archive:
        archive.extractall(reference, filter="data")
    regression = compare_runs(reference, userdir)
    assert regression["passed"], regression["differences"]
    assert regression["trade_count"] == {"old": 13, "new": 13}
    assert len(regression["prediction_files"]) == 4
    assert regression["order_count"] == {"old": 26, "new": 26}


def test_corrected_native_backtest_is_reproducible_in_fresh_disconnected_userdirs(tmp_path):
    """New production code must actually retrain and strictly reproduce itself."""
    outputs = []
    for attempt in ("first", "second"):
        command, report, userdir = offline_command(tmp_path / attempt, SNAPSHOT)
        result = run_audited(["unshare", "--user", "--map-root-user", "--net", *command])
        assert result.returncode == 0, result.stdout + result.stderr
        network = json.loads(report.read_text())
        assert network["http_requests"] == network["socket_events"] == []
        assert network["denied_operations"] == 0
        audits = list(userdir.rglob("native_training_audit/*/audit.json"))
        assert len(audits) == 4  # BTC/ETH, both real weekly training windows.
        for path in audits:
            audit = json.loads(path.read_text())
            assert audit["phase"] == "trained" and audit["status"] == "PASS"
            assert audit["counts"]["purged"] == 3
            assert (
                audit["preprocessor_fit"]["feature_pipeline"]["sample_ids"]
                == audit["label_statistics_fit_sample_ids"]
            )
        outputs.append(userdir)
    compared = compare_runs(*outputs)
    assert compared["passed"], compared["differences"]
    assert len(compared["prediction_files"]) == 4
    assert compared["trade_count"]["old"] == compared["trade_count"]["new"] > 0
    assert compared["order_count"]["old"] == compared["order_count"]["new"] > 0
