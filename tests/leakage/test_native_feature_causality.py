"""Actual native FreqAI expansion, including correlated inputs, is causal."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from quant.errors import DataContractError
from quant.validation.native_features import (
    audit_native_features,
    audit_snapshot_ranking,
    populate_native_features,
)
from tests.conftest import make_ohlcv


@pytest.fixture
def native_inputs():
    config = json.loads(Path("config.json").read_text())
    pairs = ["BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT"]
    config["exchange"]["pair_whitelist"] = pairs
    frames = {pair: make_ohlcv(320) for pair in pairs}
    frames[pairs[1]][["open", "high", "low", "close"]] *= 2
    return config, frames


def test_actual_native_expansion_schema_and_all_feature_contracts(native_inputs):
    config, frames = native_inputs
    report = audit_native_features(config, frames, cut_points=[180, 260])
    assert report["status"] == "PASS", report
    assert report["audited_pairs"] == config["exchange"]["pair_whitelist"]
    assert report["tolerance"] == {"rtol": 0.0, "atol": 0.0}
    counts = {pair: value["feature_count"] for pair, value in report["pairs"].items()}
    assert counts == {"BTC/USDT:USDT": 92, "ETH/USDT:USDT": 92, "BNB/USDT:USDT": 136}
    for result in report["pairs"].values():
        assert result["unverified_columns"] == []
        assert len(result["columns"]) == result["feature_count"]
        assert all(value["status"] == "PASS" for value in result["contracts"].values())
        assert all(value["available_at"] for value in result["contracts"].values())
        assert {check["kind"] for check in result["checks"]} == {
            "future_perturbation",
            "truncation",
            "correlated_future_perturbation",
        }


@pytest.mark.parametrize("leak", ["future_shift", "whole_sample", "correlated_future"])
def test_actual_pipeline_known_schema_future_faults_are_detected(native_inputs, leak):
    config, frames = native_inputs

    def leaking(current, values, pair):
        result = populate_native_features(current, values, pair)
        column = next(name for name in result if name.startswith("%"))
        own = values[pair, current["timeframe"]]
        if leak == "future_shift":
            result[column] = own.close.shift(-1)
        elif leak == "whole_sample":
            result[column] = own.close.mean()
        else:
            result[column] = values["ETH/USDT:USDT", current["timeframe"]].close.mean()
        return result

    result = audit_native_features(
        config, frames, pairs=["BTC/USDT:USDT"], cut_points=[180, 260], populator=leaking
    )
    assert result["status"] == "FAIL" and result["differences"]


def test_features_unchanged_but_future_label_changes_are_expected(native_inputs):
    config, frames = native_inputs
    pair = "BTC/USDT:USDT"
    original = populate_native_features(config, frames, pair)
    changed = deepcopy(frames)
    changed[pair].loc[181:, ["open", "high", "low", "close"]] *= 3
    current = populate_native_features(config, changed, pair)
    columns = [name for name in original if name.startswith("%")]
    pd.testing.assert_frame_equal(original.loc[:180, columns], current.loc[:180, columns])
    assert original.loc[180, "&-s_return"] != current.loc[180, "&-s_return"]


def test_native_audit_does_not_modify_input(native_inputs):
    config, frames = native_inputs
    before = deepcopy(frames)
    populate_native_features(config, frames, "BTC/USDT:USDT")
    for pair in frames:
        pd.testing.assert_frame_equal(before[pair], frames[pair])


@pytest.mark.parametrize("fault", ["missing_corr", "duplicate", "missing_date", "gap", "empty"])
def test_native_inputs_fail_closed(native_inputs, fault):
    config, frames = native_inputs
    pair = "BTC/USDT:USDT"
    if fault == "missing_corr":
        del frames["ETH/USDT:USDT"]
    elif fault == "duplicate":
        frames[pair].loc[10, "date"] = frames[pair].loc[9, "date"]
    elif fault == "missing_date":
        frames[pair].loc[10, "date"] = pd.NaT
    elif fault == "gap":
        frames[pair] = frames[pair].drop(index=20)
    else:
        frames[pair] = frames[pair].iloc[:0]
    with pytest.raises(DataContractError):
        populate_native_features(config, frames, pair)


def test_dynamic_universe_is_explicitly_blocked(native_inputs):
    config, frames = native_inputs
    config["pairlists"] = [{"method": "VolumePairList"}]
    report = audit_native_features(config, frames, cut_points=[180])
    assert report["status"] == "BLOCKED"
    assert "StaticPairList" in report["reason"]


def test_unobserved_warmup_is_blocked_not_assumed_causal(native_inputs):
    config, frames = native_inputs
    frames = {pair: frame.iloc[:10] for pair, frame in frames.items()}
    report = audit_native_features(config, frames, cut_points=[5])
    assert report["status"] == "BLOCKED"
    assert report["pairs"]["BTC/USDT:USDT"]["unverified_columns"]


@pytest.mark.parametrize("alteration", ["missing", "extra"])
def test_native_schema_incomplete_or_unreviewed_columns_cannot_pass(native_inputs, alteration):
    config, frames = native_inputs

    def changed(current, values, pair):
        result = populate_native_features(current, values, pair)
        if alteration == "missing":
            return result.drop(columns=[next(name for name in result if name.startswith("%"))])
        return result.assign(**{"%-unreviewed": result.close})

    result = audit_native_features(
        config, frames, pairs=["BTC/USDT:USDT"], cut_points=[180], populator=changed
    )
    assert result["status"] == "BLOCKED"
    assert result["pairs"]["BTC/USDT:USDT"]["unverified_columns"]


def test_actual_snapshot_and_native_strategy_ranking_ignore_future_predictions(native_inputs):
    config, frames = native_inputs
    predictions = {
        pair: frame[["date"]].assign(**{"&-s_return": frame.close.pct_change(), "do_predict": 1})
        for pair, frame in frames.items()
    }
    result = audit_snapshot_ranking(config, predictions, frames["BTC/USDT:USDT"].date.iloc[180])
    assert result["status"] == "PASS"
    assert result["checks"] == {"future_perturbation": True, "truncation": True}


def test_future_global_dynamic_ranking_is_detected(native_inputs):
    config, frames = native_inputs
    predictions = {
        pair: frame[["date"]].assign(**{"&-s_return": frame.close, "do_predict": 1})
        for pair, frame in frames.items()
    }

    def future_ranking(current, values, timestamp):
        return sorted(values, key=lambda pair: values[pair]["&-s_return"].max())

    result = audit_snapshot_ranking(
        config, predictions, frames["BTC/USDT:USDT"].date.iloc[180], evaluator=future_ranking
    )
    assert result["status"] == "FAIL"


def test_actual_btc_eth_bnb_files_full_native_features_are_causal():
    config = json.loads(Path("config.json").read_text())
    pairs = ["BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT"]
    config["exchange"]["pair_whitelist"] = pairs
    raw_frames = {
        pair: pd.read_feather(
            Path("data/futures")
            / (pair.replace("/", "_").replace(":", "_") + "-4h-futures.feather")
        )
        for pair in pairs
    }
    # Use one common early window.  BNB starts later than BTC/ETH; taking
    # ``head`` independently would compare different historical regimes and
    # could hide cross-pair timing defects.
    common_start = max(frame.date.iloc[0] for frame in raw_frames.values())
    frames = {
        pair: frame.loc[frame.date >= common_start].head(400).reset_index(drop=True)
        for pair, frame in raw_frames.items()
    }
    report = audit_native_features(config, frames, cut_points=[180, 300])
    assert report["status"] == "PASS", report
    assert len(report["pairs"]) == 3


def test_native_informative_timeframe_merges_only_closed_candles(native_inputs):
    config, original = native_inputs
    config["freqai"]["feature_parameters"]["include_timeframes"] = ["4h", "8h"]
    frames = {}
    for pair, frame in original.items():
        frames[pair, "4h"] = frame
        frames[pair, "8h"] = (
            frame.set_index("date")
            .resample("8h")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .reset_index()
        )
    report = audit_native_features(config, frames, pairs=["BTC/USDT:USDT"], cut_points=[181, 260])
    assert report["status"] == "PASS", report
    assert report["pairs"]["BTC/USDT:USDT"]["feature_count"] == 180


def test_unusable_prediction_snapshot_is_not_a_successful_ranking_audit(native_inputs):
    config, frames = native_inputs
    predictions = {
        pair: frame[["date"]].assign(**{"&-s_return": 1.0, "do_predict": 0})
        for pair, frame in frames.items()
    }
    result = audit_snapshot_ranking(config, predictions, frames["BTC/USDT:USDT"].date.iloc[180])
    assert result["status"] == "BLOCKED"


def test_audit_input_fingerprints_reject_in_run_replacement(tmp_path):
    from tools.audit_native_features import _sha, fingerprint_changes

    source = tmp_path / "config.json"
    source.write_text('{"version": 1}')
    receipts = [(source, _sha(source))]
    assert fingerprint_changes(receipts) == []
    source.write_text('{"version": 2}')
    assert fingerprint_changes(receipts) == [
        {"filename": "config.json", "reason": "input_changed_during_audit"}
    ]
    source.unlink()
    assert fingerprint_changes(receipts)


def test_real_native_audit_cli_binds_run_identity_and_immutable_inputs(tmp_path):
    output = tmp_path / "current-evidence-run" / "features"
    result = subprocess.run(
        [
            sys.executable,
            "tools/audit_native_features.py",
            "-c",
            "config.json",
            "--bars",
            "80",
            "--pairs",
            "BTC/USDT:USDT",
            "ETH/USDT:USDT",
            "BNB/USDT:USDT",
            "--output",
            str(output),
        ],
        env={**os.environ, "PYTHONPATH": str(Path(".").resolve())},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads((output / "native_features.json").read_text())
    assert receipt["run_id"] == "current-evidence-run"
    assert receipt["input_integrity"] == {"unchanged": True, "changes": []}
    assert len(receipt["input_files"]) == 3
    assert receipt["all_configured_pairs_audited"] is False
