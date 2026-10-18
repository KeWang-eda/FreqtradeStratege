"""Inventory errors keep their source identity and never authorize native use."""

import pandas as pd

from tools.audit_training_data import inspect_source


def test_missing_source_keeps_kind_timeframe_and_quarantine(tmp_path):
    result = inspect_source(tmp_path / "missing.feather", "BTC/USDT:USDT", "mark", "1h")
    assert result["status"] == "FAIL"
    assert result["kind"] == "mark"
    assert result["timeframe"] == "1h"
    assert result["formal_use"] == "quarantined"
    assert result["issues"] == [{"code": "missing_file"}]


def test_corrupt_source_keeps_actual_path_hash_and_is_not_modified(tmp_path):
    path = tmp_path / "corrupt.feather"
    path.write_bytes(b"not feather")
    result = inspect_source(path, "BTC/USDT:USDT", "futures", "4h")
    assert result["status"] == "FAIL"
    assert result["unchanged"] is True
    assert len(result["file_sha256"]) == 64
    assert result["path"].endswith("corrupt.feather")
    assert path.read_bytes() == b"not feather"


def test_external_datadir_source_identity_is_actual_input_not_default_data(tmp_path, candles):
    path = tmp_path / "funding.feather"
    frame = candles.copy()
    frame[["high", "low", "close", "volume"]] = 0.0
    frame["open"] = 0.0001
    frame.to_feather(path)
    result = inspect_source(path, "BTC/USDT:USDT", "funding_rate", "1h")
    assert result["status"] == "BLOCKED"
    assert result["formal_use"] == "quarantined"
    assert not result["path"].startswith("data/futures/")
    assert pd.read_feather(path).equals(frame)
