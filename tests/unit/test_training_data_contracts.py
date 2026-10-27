"""Data contracts use small unit fixtures; real-file checks are separate evidence."""

import importlib

import numpy as np
import pandas as pd
import pytest

from quant.errors import DataContractError


@pytest.fixture
def contracts():
    return importlib.import_module("quant.market_data.contracts")


@pytest.fixture
def raw():
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=12, freq="4h", tz="UTC"),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 10.0,
        }
    )


def test_fingerprint_changes_with_column_semantics_order_dtype_and_value(contracts, raw):
    expected = contracts.frame_fingerprint(raw)
    assert expected == contracts.frame_fingerprint(raw.copy())
    for changed in [
        raw.rename(columns={"close": "another_close"}),
        raw[list(reversed(raw.columns))],
        raw.astype({"volume": "float32"}),
        raw.assign(close=100.0),
    ]:
        assert contracts.frame_fingerprint(changed) != expected


@pytest.mark.parametrize("unit", ["ns", "us", "ms"])
def test_timestamp_units_and_timezone_share_canonical_utc_fingerprint(contracts, raw, unit):
    changed = raw.copy()
    changed["date"] = changed.date.dt.tz_convert("Asia/Shanghai").dt.as_unit(unit)
    assert contracts.frame_fingerprint(changed) == contracts.frame_fingerprint(raw)


def test_row_index_is_not_the_identity_of_a_candle(contracts, raw):
    reindexed = raw.copy()
    reindexed.index += 900
    assert contracts.frame_fingerprint(raw) == contracts.frame_fingerprint(reindexed)


def test_duplicate_columns_are_not_fingerprintable(contracts, raw):
    raw.columns = ["date", "open", "high", "low", "close", "close"]
    with pytest.raises(DataContractError):
        contracts.frame_fingerprint(raw)


def test_grid_accepts_whole_bar_gap_but_reports_it_as_partial(contracts, raw):
    missing = raw.drop(index=[3, 4])
    contracts.validate_candle_grid(missing, "4h")
    report = contracts.audit_source(missing, kind="futures", timeframe="4h")
    assert report["status"] == "PARTIAL"
    assert report["missing_rows"] == 2
    assert report["missing_intervals"] == [
        {
            "start": "2025-01-01T12:00:00+00:00",
            "end_exclusive": "2025-01-01T20:00:00+00:00",
            "rows": 2,
        }
    ]
    assert len(missing) == 10


@pytest.mark.parametrize(
    "change", ["off_grid", "nonintegral_difference", "naive", "duplicate", "unsorted", "nat"]
)
def test_invalid_candle_grid_fails_closed(contracts, raw, change):
    if change == "off_grid":
        raw.date += pd.Timedelta(minutes=1)
    elif change == "nonintegral_difference":
        raw.loc[3, "date"] += pd.Timedelta(hours=1)
    elif change == "naive":
        raw.date = raw.date.dt.tz_localize(None)
    elif change == "duplicate":
        raw.loc[1, "date"] = raw.loc[0, "date"]
    elif change == "unsorted":
        raw = raw.iloc[::-1]
    elif change == "nat":
        raw.loc[1, "date"] = pd.NaT
    with pytest.raises(DataContractError):
        contracts.validate_candle_grid(raw, "4h")
    assert contracts.audit_source(raw, kind="futures", timeframe="4h")["status"] == "FAIL"


def test_regular_source_contract_declares_units_and_availability(contracts, raw):
    before = raw.copy(deep=True)
    report = contracts.audit_source(raw, kind="futures", timeframe="4h")
    assert report["status"] == "PASS"
    assert report["contract"]["timestamp"] == "UTC candle open"
    assert report["contract"]["available_at"] == "candle_open + timeframe"
    assert report["contract"]["value_units"]["volume"] == "exchange-defined raw candle volume"
    assert report["raw_rows"] == 12 and report["missing_rows"] == 0
    assert report["fingerprint"] == contracts.frame_fingerprint(raw)
    pd.testing.assert_frame_equal(raw, before)


def test_requested_range_is_half_open_and_reports_boundary_missing(contracts, raw):
    report = contracts.audit_source(
        raw,
        kind="mark",
        timeframe="4h",
        expected_start=pd.Timestamp("2024-12-31T20:00Z"),
        expected_end=pd.Timestamp("2025-01-03T04:00Z"),
    )
    assert report["status"] == "PARTIAL" and report["missing_rows"] == 2
    assert report["missing_intervals"][0]["start"] == "2024-12-31T20:00:00+00:00"
    assert report["missing_intervals"][-1]["end_exclusive"] == "2025-01-03T04:00:00+00:00"


@pytest.mark.parametrize(
    "change",
    [
        "string",
        "boolean",
        "nan",
        "infinite",
        "negative_price",
        "negative_volume",
        "bounds",
        "schema",
        "empty",
    ],
)
def test_corrupt_source_reports_fail_instead_of_zero_imputation(contracts, raw, change):
    if change == "string":
        raw["volume"] = raw.volume.astype(str)
    elif change == "boolean":
        raw["volume"] = True
    elif change == "nan":
        raw.loc[2, "close"] = np.nan
    elif change == "infinite":
        raw.loc[2, "volume"] = np.inf
    elif change == "negative_price":
        raw.loc[2, "close"] = -1
    elif change == "negative_volume":
        raw.loc[2, "volume"] = -1
    elif change == "bounds":
        raw.loc[2, "high"] = 90
    elif change == "schema":
        raw = raw.drop(columns="close")
    elif change == "empty":
        raw = raw.iloc[:0]
    report = contracts.audit_source(raw, kind="futures", timeframe="4h")
    assert report["status"] == "FAIL" and report["issues"]


def funding():
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=6, freq="8h", tz="UTC"),
            "open": -0.0001,
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "volume": 0.0,
        }
    )


def test_funding_without_verified_payment_interval_is_blocked(contracts):
    report = contracts.audit_source(funding(), kind="funding_rate", timeframe="1h")
    assert report["status"] == "BLOCKED"
    assert report["missing_rows"] is None
    assert report["observed_interval_seconds"] == {"28800": 5}
    assert report["issues"][0]["code"] == "funding_schedule_missing"


def test_funding_accepts_negative_rate_and_zero_native_placeholder_fields(contracts):
    report = contracts.audit_source(
        funding(), kind="funding_rate", timeframe="1h", funding_interval_hours=8
    )
    assert report["status"] == "PASS"
    assert (
        report["contract"]["available_at"]
        == "recorded funding event timestamp; publication delay not verified"
    )
    assert (
        report["contract"]["value_units"]["open"]
        == "dimensionless funding fraction per payment event"
    )
    assert report["missing_rows"] == 0


def test_funding_missing_event_never_becomes_zero_rate(contracts):
    raw = funding().drop(index=[2])
    report = contracts.audit_source(
        raw, kind="funding_rate", timeframe="1h", funding_interval_hours=8
    )
    assert report["status"] == "PARTIAL" and report["missing_rows"] == 1
    assert len(raw) == 5 and set(raw.open) == {-0.0001}


def test_observed_frequency_change_does_not_create_fictional_funding_gaps(contracts):
    raw = funding()
    raw.loc[2, "date"] -= pd.Timedelta(hours=4)
    report = contracts.audit_source(raw, kind="funding_rate", timeframe="1h")
    assert report["status"] == "BLOCKED" and report["missing_rows"] is None
    assert len(report["observed_interval_seconds"]) > 1


@pytest.mark.parametrize("interval", [0, -1, True, np.inf, np.nan, "8"])
def test_invalid_supplied_funding_schedule_fails(contracts, interval):
    assert (
        contracts.audit_source(
            funding(), kind="funding_rate", timeframe="1h", funding_interval_hours=interval
        )["status"]
        == "FAIL"
    )


def test_known_funding_schedule_incompatible_event_is_corrupt(contracts):
    raw = funding()
    raw.loc[2, "date"] -= pd.Timedelta(hours=1)
    report = contracts.audit_source(
        raw, kind="funding_rate", timeframe="1h", funding_interval_hours=8
    )
    assert report["status"] == "FAIL"


def test_unknown_source_kind_cannot_pass(contracts, raw):
    assert contracts.audit_source(raw, kind="ticker", timeframe="4h")["status"] == "FAIL"


def test_contract_import_does_not_load_freqtrade_or_ccxt():
    import os
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import quant.market_data.contracts; import quant.models; "
            "assert 'freqtrade' not in sys.modules; assert 'ccxt' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])},
    )
    assert result.returncode == 0, result.stderr
