"""Detector success must never be reported as native leakage gate success."""

import json
from pathlib import Path

from quant_strategy.market_data import load_ohlcv
from quant_strategy.validation.native_boundaries import audit_native_boundaries


def test_actual_native_split_exposes_overlapping_training_labels(candles):
    config = json.loads(Path("config.json").read_text())
    report = audit_native_boundaries(config, candles)
    assert report["status"] == "FAIL"
    assert (
        report["label_boundary_violations"]
        == config["freqai"]["feature_parameters"]["label_period_candles"]
    )
    assert len(report["violations"]) == report["label_boundary_violations"]
    assert set(report["train_indices"]).isdisjoint(report["validation_indices"])


def test_outer_training_tail_is_unlabeled_not_false_future_backtest_leak(candles):
    config = json.loads(Path("config.json").read_text())
    report = audit_native_boundaries(config, candles.iloc[:180])
    assert report["outer_label_tail_missing"] == 3
    assert report["outer_label_end_max"] == report["raw_last_available_at"]


def test_real_btc_native_boundary_gate_cannot_pass_by_exit_code_only():
    config = json.loads(Path("config.json").read_text())
    raw = load_ohlcv("data/futures/BTC_USDT_USDT-4h-futures.feather").iloc[-600:]
    report = audit_native_boundaries(config, raw)
    assert report["status"] == "FAIL"
    assert report["label_boundary_violations"] == 3


def test_native_shuffle_is_detected_not_reinterpreted_as_walk_forward(candles):
    config = json.loads(Path("config.json").read_text())
    config["freqai"]["data_split_parameters"]["shuffle"] = True
    report = audit_native_boundaries(config, candles)
    assert report["status"] == "FAIL"
    assert report["reversed_or_shuffled_time"] is True
