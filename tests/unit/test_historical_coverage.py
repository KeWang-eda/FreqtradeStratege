"""Raw-data audit rejects defects; synthetic frames here are unit fixtures only."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools import audit_historical_coverage as audit

START = pd.Timestamp("2025-01-01", tz="UTC")
STOP = START + pd.Timedelta(days=1)


def candles(dates=None):
    dates = dates if dates is not None else pd.date_range(START, STOP, freq="4h", inclusive="left")
    return pd.DataFrame(
        {"date": dates, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 1.0}
    )


def inspect(tmp_path, frame, kind="futures", timeframe="4h", baseline=None):
    path = tmp_path / "fixture.feather"
    frame.to_feather(path)
    return audit.inspect_file(path, kind, timeframe, START, STOP, baseline)[0]


def test_missing_file_fails_closed_without_filling(tmp_path):
    report, frame = audit.inspect_file(tmp_path / "missing.feather", "futures", "4h", START, STOP)
    assert frame is None and report["usable"] is False
    assert report["errors"] == ["missing_file"]


def test_empty_file_is_unusable(tmp_path):
    report = inspect(tmp_path, candles().iloc[:0])
    assert not report["usable"] and "empty_file" in report["errors"]


def test_corrupt_feather_is_reported(tmp_path):
    path = tmp_path / "bad.feather"
    path.write_text("not a feather")
    report, frame = audit.inspect_file(path, "futures", "4h", START, STOP)
    assert frame is None
    assert any(value.startswith("unreadable_file:") for value in report["errors"])


@pytest.mark.parametrize("unit", ["ns", "us", "ms"])
def test_real_datetime_resolution_does_not_change_alignment(tmp_path, unit):
    frame = candles()
    frame["date"] = frame["date"].dt.as_unit(unit)
    report = inspect(tmp_path, frame)
    assert report["usable"] and report["off_grid_rows"] == 0
    assert report["coverage"]["expected_rows"] == 6


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("duplicate", "invalid_time_index"),
        ("unsorted", "invalid_time_index"),
        ("naive", "date_requires_timezone_aware_datetime"),
        ("non_utc", "date_timezone_is_not_UTC"),
        ("nat", "invalid_time_index"),
        ("off_grid", "off_grid_timestamps"),
        ("missing_column", "invalid_ohlcv_schema"),
        ("infinite", "non_finite_or_non_numeric_values"),
        ("nan", "non_finite_or_non_numeric_values"),
        ("non_numeric", "non_finite_or_non_numeric_values"),
        ("negative_price", "invalid_prices_or_ohlc_bounds"),
        ("invalid_bounds", "invalid_prices_or_ohlc_bounds"),
        ("negative_volume", "negative_volume"),
    ],
)
def test_invalid_raw_data_is_not_usable(tmp_path, mutation, expected):
    frame = candles()
    if mutation == "duplicate":
        frame.loc[1, "date"] = frame.loc[0, "date"]
    elif mutation == "unsorted":
        frame = frame.iloc[::-1]
    elif mutation == "naive":
        frame["date"] = frame.date.dt.tz_localize(None)
    elif mutation == "non_utc":
        frame["date"] = frame.date.dt.tz_convert("Asia/Shanghai")
    elif mutation == "nat":
        frame.loc[1, "date"] = pd.NaT
    elif mutation == "off_grid":
        frame.loc[1, "date"] += pd.Timedelta(minutes=1)
    elif mutation == "missing_column":
        frame = frame.drop(columns="volume")
    elif mutation in {"infinite", "nan", "negative_price"}:
        frame.loc[1, "close"] = {"infinite": np.inf, "nan": np.nan, "negative_price": -1}[mutation]
    elif mutation == "non_numeric":
        frame["open"] = "invalid"
    elif mutation == "invalid_bounds":
        frame.loc[1, "high"] = 5
    elif mutation == "negative_volume":
        frame.loc[1, "volume"] = -1
    report = inspect(tmp_path, frame)
    assert not report["usable"] and expected in report["errors"]


def test_exact_missing_interval_does_not_reindex_raw_data(tmp_path):
    frame = candles().drop(index=[1, 2])
    report = inspect(tmp_path, frame)
    assert len(frame) == report["rows"] == 4
    assert report["coverage"]["missing_rows"] == 2
    assert report["coverage"]["missing_intervals"] == [
        {
            "start": "2025-01-01T04:00:00+00:00",
            "stop_exclusive": "2025-01-01T12:00:00+00:00",
            "rows": 2,
        }
    ]
    assert not report["usable"]


def test_hourly_funding_filename_does_not_imply_hourly_payments(tmp_path):
    frame = candles(pd.date_range(START, STOP, freq="8h", inclusive="left"))
    frame.loc[:, ["high", "low", "close", "volume"]] = 0
    frame["open"] = -0.0001
    report = inspect(tmp_path, frame, "funding_rate", "1h")
    assert report["usable"] and report["coverage"]["expected_rows"] == 3
    assert report["observed_interval_seconds"] == {"28800": 2}
    assert report["filename_timeframe_is_payment_cadence"] is False
    assert report["global_gaps"] is None


def test_variable_funding_interval_requires_schedule_evidence(tmp_path):
    frame = candles(
        pd.DatetimeIndex([START, START + pd.Timedelta(hours=4), START + pd.Timedelta(hours=12)])
    )
    report = inspect(tmp_path, frame, "funding_rate", "1h")
    assert report["cadence"] == "variable_requires_schedule_verification"
    assert report["global_gaps"] is None
    assert report["coverage"]["reason"] == "unknown_payment_schedule_no_events_inferred"
    assert "funding_schedule_requires_verification" in report["errors"]


def test_checksum_mismatch_rejects_updated_data(tmp_path):
    report = inspect(tmp_path, candles(), baseline="0" * 64)
    assert not report["usable"] and "changed_since_baseline" in report["errors"]


def test_modification_during_audit_is_detected(tmp_path, monkeypatch):
    checksums = iter(["initial", "changed"])
    monkeypatch.setattr(audit, "file_hash", lambda path: next(checksums))
    report = inspect(tmp_path, candles())
    assert report["changed_during_audit"] and not report["usable"]


def test_native_strategy_startup_is_resolved_without_a_network_client():
    config, strategy, requirements = audit.load_requirements(
        ["config.json"], "20250101-20250115", "MyStrategy"
    )
    assert requirements["strategy_startup_candles"] == strategy.startup_candle_count
    tf = requirements["timeframe"]
    from freqtrade.exchange import timeframe_to_seconds

    expected = int(
        max(strategy.startup_candle_count, max(requirements["indicator_periods_candles"]))
        + config["freqai"]["train_period_days"] * 86400 / timeframe_to_seconds(tf)
    )
    assert requirements["required_startup_candles"][tf] == expected


def test_actual_target_tail_cannot_see_rows_outside_each_training_window():
    _, strategy, requirements = audit.load_requirements(
        ["config.json"], "20250101-20250115", "MyStrategy"
    )
    dates = pd.date_range(
        requirements["required_starts"][requirements["timeframe"]],
        requirements["stop_exclusive"],
        freq="4h",
        inclusive="left",
    )
    frame = candles(dates)
    report = audit.audit_labels(frame, strategy, requirements, "BTC/USDT:USDT")
    horizon = requirements["label_horizon_candles"]
    assert report["ready"] and report["horizon_timestamp_misalignments"] == 0
    assert all(window["missing_labels"] == horizon for window in report["training_windows"])
    # Unit-only removed candle proves a row shift cannot masquerade as a time shift.
    broken = audit.audit_labels(frame.drop(index=[300]), strategy, requirements, "BTC/USDT:USDT")
    assert not broken["ready"] and broken["horizon_timestamp_misalignments"] > 0


def test_public_paths_do_not_publish_workstation_identity(tmp_path):
    assert audit.public_path(tmp_path / "file.feather") == "${EXTERNAL}/file.feather"
    assert audit.public_path(Path("config.json")) == "config.json"


def test_actual_audit_with_missing_local_files_fails_gate_without_downloading(tmp_path):
    config = json.loads(Path("config.json").read_text())
    config["datadir"] = str(tmp_path / "missing-data")
    config["exchange"]["pair_whitelist"] = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    report = audit.audit(
        [str(path)],
        "20250101-20250115",
        "MyStrategy",
        Path("docs/acceptance/phase0_inventory.json"),
        Path("docs/baseline/acceptance/binance-usdt-market-snapshot.json"),
    )
    assert report["minimum_scope_ready"] is False
    assert report["summary"]["existing_files"] == 0
    assert report["summary"]["file_count"] == 6
    assert not (tmp_path / "missing-data").exists()
    assert all(not pair["raw_data_ready"] for pair in report["pairs"])


def test_invalid_local_timezone_is_a_pair_failure_not_whole_audit_exception(tmp_path):
    config = json.loads(Path("config.json").read_text())
    config["datadir"] = str(tmp_path)
    config["exchange"]["pair_whitelist"] = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    # Unit fixture only; other absent files remain explicit failures.
    directory = tmp_path / "futures"
    directory.mkdir()
    frame = candles()
    frame["date"] = frame.date.dt.tz_localize(None)
    frame.to_feather(directory / "BTC_USDT_USDT-4h-futures.feather")
    report = audit.audit(
        [str(path)],
        "20250101-20250115",
        "MyStrategy",
        Path("docs/acceptance/phase0_inventory.json"),
        Path("docs/baseline/acceptance/binance-usdt-market-snapshot.json"),
    )
    assert report["minimum_scope_ready"] is False
    btc = next(pair for pair in report["pairs"] if pair["pair"].startswith("BTC/"))
    assert "date_requires_timezone_aware_datetime" in btc["files"][0]["errors"]


def test_cli_distinguishes_audit_failure_from_detected_gaps(tmp_path, monkeypatch):
    summary = {"all_requested_pairs_ready": False}
    monkeypatch.setattr(audit, "audit", lambda *args: {"summary": summary})
    output = tmp_path / "report.json"
    assert (
        audit.main(
            ["--config", "config.json", "--timerange", "20250101-20250115", "--output", str(output)]
        )
        == 1
    )
    assert json.loads(output.read_text())["summary"] == summary

    def fail(*args):
        raise ValueError("invalid snapshot")

    monkeypatch.setattr(audit, "audit", fail)
    assert (
        audit.main(
            ["--config", "config.json", "--timerange", "20250101-20250115", "--output", str(output)]
        )
        == 2
    )
