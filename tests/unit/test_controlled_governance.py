"""Fault injection uses disposable data; actual local data are audited separately."""

import json
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from quant.infrastructure.experiment_store import file_hash
from quant.research.governance import (
    PAIRS,
    assess_funding_evidence,
    audit_three_pair_sources,
)


def _frame(periods=48, frequency="4h", start="2025-01-01"):
    return pd.DataFrame(
        {
            "date": pd.date_range(start, periods=periods, freq=frequency, tz="UTC"),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 20.0,
        }
    )


@pytest.fixture
def local_config(tmp_path):
    config = json.loads(Path("config.json").read_text())
    config["datadir"] = str(tmp_path)
    directory = tmp_path / "futures"
    directory.mkdir()
    for pair in PAIRS:
        slug = pair.replace("/", "_").replace(":", "_")
        for kind, timeframe, frequency in (
            ("futures", "4h", "4h"),
            ("mark", "1h", "1h"),
            ("funding_rate", "1h", "8h"),
        ):
            frame = _frame(periods=384 if kind == "mark" else 48, frequency=frequency)
            if kind == "funding_rate":
                frame[["high", "low", "close", "volume"]] = 0.0
                frame["open"] = -0.0001
            frame.to_feather(directory / f"{slug}-{timeframe}-{kind}.feather")
    return config


def _path(config, kind="futures", pair="BTC"):
    return (
        Path(config["datadir"])
        / "futures"
        / f"{pair}_USDT_USDT-{'4h' if kind == 'futures' else '1h'}-{kind}.feather"
    )


def test_complete_source_quality_does_not_authorize_costs_or_formal_research(local_config):
    before_config = deepcopy(local_config)
    paths = sorted((Path(local_config["datadir"]) / "futures").glob("*"))
    before = {path: file_hash(path) for path in paths}
    first = audit_three_pair_sources(local_config, list(PAIRS))
    second = audit_three_pair_sources(local_config, list(PAIRS))
    assert first["status"] == "BLOCKED"
    assert first["source_set_sha256"] == second["source_set_sha256"]
    assert all(item["source_prediction_preparation_status"] == "PASS" for item in first["per_pair"])
    assert all(item["trade_cost_evaluation_status"] == "BLOCKED" for item in first["per_pair"])
    assert first["formal_research_allowed"] is False
    assert first["historical_universe"]["status"] == "BLOCKED"
    assert first["all_existing_files_unchanged"] is True
    assert first["native_startup_requirement"]["candles"] == 2290
    assert local_config == before_config
    assert before == {path: file_hash(path) for path in paths}


def test_funding_storage_timeframe_and_regular_cadence_are_not_historical_proof(local_config):
    report = audit_three_pair_sources(local_config, list(PAIRS))
    funds = [item for item in report["sources"] if item["kind"] == "funding_rate"]
    assert all(item["observed_interval_seconds"] == {"28800": 47} for item in funds)
    assert all(item["missing_rows"] is None and item["missing_intervals"] is None for item in funds)
    assert all(item["status"] == "BLOCKED" for item in funds)
    assert all(not item["historical_evidence"]["payment_events_complete"] for item in funds)


def test_missing_funding_is_not_filled_and_does_not_hide_prediction_source_quality(local_config):
    path = _path(local_config, "funding_rate")
    path.unlink()
    result = audit_three_pair_sources(local_config, list(PAIRS))
    assert result["status"] == "FAIL"
    missing = next(
        item
        for item in result["sources"]
        if item["pair"] == PAIRS[0] and item["kind"] == "funding_rate"
    )
    assert missing["issues"] == [{"code": "missing_file"}]
    assert result["per_pair"][0]["source_prediction_preparation_status"] == "PASS"
    assert not path.exists()
    assert result["policy"]["imputed_bars_or_rates"] == 0


@pytest.mark.parametrize(
    "source_type", ["current_exchange_info", "observed_cadence", "caller_declared"]
)
def test_current_or_inferred_fixed_interval_cannot_prove_historical_schedule(source_type):
    frame = _frame(frequency="8h")
    result = assess_funding_evidence(frame, {"source_type": source_type, "interval_hours": 8})
    assert result["status"] == "BLOCKED"
    assert result["historical_payment_schedule_verified"] is False


def test_wrong_declared_payment_events_are_detected():
    frame = _frame(frequency="8h")
    declaration = {"expected_payment_events": [value.isoformat() for value in frame.date]}
    declaration["expected_payment_events"].append(
        (frame.date.iloc[-1] + pd.Timedelta(hours=8)).isoformat()
    )
    result = assess_funding_evidence(frame, declaration)
    assert result["status"] == "FAIL"
    assert len(result["missing_declared_events"]) == 1
    assert result["payment_events_complete"] is None


def test_exact_self_declared_payment_events_are_not_self_authenticating():
    frame = _frame(frequency="8h")
    result = assess_funding_evidence(
        frame, {"expected_payment_events": [stamp.isoformat() for stamp in frame.date]}
    )
    assert result["event_comparison_status"] == "PASS"
    assert result["status"] == "BLOCKED"


def test_absent_observed_payment_does_not_become_zero_or_inferred_schedule(local_config):
    path = _path(local_config, "funding_rate")
    frame = pd.read_feather(path).drop(index=[3]).reset_index(drop=True)
    frame.to_feather(path)
    result = audit_three_pair_sources(local_config, list(PAIRS))
    funding = next(
        item
        for item in result["sources"]
        if item["pair"] == PAIRS[0] and item["kind"] == "funding_rate"
    )
    assert funding["status"] == "BLOCKED"
    assert funding["rows"] == 47
    assert funding["missing_rows"] is None
    assert funding["observed_interval_seconds"] == {"28800": 45, "57600": 1}
    assert pd.read_feather(path).open.eq(-0.0001).all()


def test_observed_payment_without_mark_is_explicit_before_native_inner_join(local_config):
    path = _path(local_config, "mark")
    frame = pd.read_feather(path).iloc[1:].reset_index(drop=True)
    frame.to_feather(path)
    result = audit_three_pair_sources(local_config, list(PAIRS))
    assert result["per_pair"][0]["funding_events_without_observed_mark"] == [
        "2025-01-01T00:00:00+00:00"
    ]
    assert result["per_pair"][0]["trade_cost_evaluation_status"] == "BLOCKED"


def test_source_changed_after_its_read_is_detected_across_whole_audit(local_config, monkeypatch):
    original = pd.read_feather
    target = _path(local_config)
    changed = False

    def mutate_previous_source(path, *args, **kwargs):
        nonlocal changed
        frame = original(path, *args, **kwargs)
        if Path(path).name == "BTC_USDT_USDT-1h-mark.feather" and not changed:
            replacement = original(target)
            replacement.loc[0, "volume"] += 1
            replacement.to_feather(target)
            changed = True
        return frame

    monkeypatch.setattr(pd, "read_feather", mutate_previous_source)
    result = audit_three_pair_sources(local_config, list(PAIRS))
    assert result["status"] == "FAIL"
    assert result["all_existing_files_unchanged"] is False
    assert result["sources"][0]["unchanged_during_read"] is True
    assert result["sources"][0]["unchanged_through_audit"] is False


@pytest.mark.parametrize("fault", ["duplicate", "naive", "negative_price", "nan", "gap"])
def test_bad_or_gapped_futures_cannot_be_source_eligible(local_config, fault):
    path = _path(local_config)
    frame = pd.read_feather(path)
    if fault == "duplicate":
        frame.loc[1, "date"] = frame.loc[0, "date"]
    elif fault == "naive":
        frame.date = frame.date.dt.tz_localize(None)
    elif fault == "negative_price":
        frame.loc[1, "open"] = -1
    elif fault == "nan":
        frame.loc[1, "close"] = float("nan")
    else:
        frame = frame.drop(index=10).reset_index(drop=True)
    frame.to_feather(path)
    result = audit_three_pair_sources(local_config, list(PAIRS))
    assert result["per_pair"][0]["source_prediction_preparation_status"] == "BLOCKED"
    assert result["sources"][0]["status"] == ("PARTIAL" if fault == "gap" else "FAIL")
    if fault == "gap":
        assert result["sources"][0]["missing_rows"] == 1
        assert result["sources"][0]["missing_intervals"][0]["rows"] == 1


@pytest.mark.parametrize("pairs", [[], [PAIRS[0], PAIRS[0]], ["SOL/USDT:USDT"]])
def test_unapproved_or_ambiguous_pair_scope_is_rejected(local_config, pairs):
    with pytest.raises(ValueError, match="Explicit unique"):
        audit_three_pair_sources(local_config, pairs)


def test_latest_dataset_identity_changes_when_raw_input_changes(local_config):
    before = audit_three_pair_sources(local_config, list(PAIRS))
    path = _path(local_config)
    frame = pd.read_feather(path)
    frame.loc[1, "volume"] += 1
    frame.to_feather(path)
    after = audit_three_pair_sources(local_config, list(PAIRS))
    assert before["source_set_sha256"] != after["source_set_sha256"]
    assert before["sources"][0]["normalized_sha256"] != after["sources"][0]["normalized_sha256"]


def test_current_snapshot_and_past_terminal_exposure_are_explicitly_limited(local_config):
    report = audit_three_pair_sources(local_config, list(PAIRS))
    universe = report["historical_universe"]
    assert universe["historical_tradable_status_verified"] is False
    assert universe["survivorship_bias_absent"] is False
    assert universe["current_snapshot"]["integrity_status"] == "PASS"
    assert universe["prior_terminal_data_exposure"]["status"] == "BLOCKED"
