"""Real-file lineage and file mutation detection; no exchange client required."""

from pathlib import Path

import pandas as pd
import pytest

from quant_strategy.config import ExperimentConfig
from quant_strategy.dataset import build_dataset
from quant_strategy.errors import DataContractError
from quant_strategy.market_data import load_ohlcv
from quant_strategy.market_data.contracts import frame_fingerprint


def test_file_change_during_read_fails_before_dataset(monkeypatch, tmp_path, candles):
    path = tmp_path / "source.feather"
    candles.to_feather(path)
    read = pd.read_feather

    def mutate_after_read(*args, **kwargs):
        result = read(*args, **kwargs)
        candles.assign(volume=candles.volume + 1).to_feather(path)
        return result

    monkeypatch.setattr(pd, "read_feather", mutate_after_read)
    with pytest.raises(DataContractError, match="changed while reading"):
        load_ohlcv(path)


def test_same_real_data_rebuilds_identical_schema_samples_and_exclusions():
    paths = {
        pair: Path("data/futures") / f"{pair}_USDT_USDT-4h-futures.feather"
        for pair in ("BTC", "ETH")
    }
    assert all(path.is_file() for path in paths.values()), (
        "Real-data integration prerequisite missing"
    )
    frames = {pair: load_ohlcv(path).iloc[-600:].copy() for pair, path in paths.items()}
    before = {pair: frame_fingerprint(frame) for pair, frame in frames.items()}
    first = build_dataset(frames, ExperimentConfig())
    second = build_dataset(dict(reversed(list(frames.items()))), ExperimentConfig())
    pd.testing.assert_frame_equal(first.X, second.X)
    pd.testing.assert_series_equal(first.y, second.y)
    pd.testing.assert_frame_equal(first.metadata, second.metadata)
    pd.testing.assert_frame_equal(first.exclusions, second.exclusions)
    assert before == {pair: frame_fingerprint(frame) for pair, frame in frames.items()}


def test_schema_changes_are_part_of_dataset_identity(candles):
    from quant_strategy.experiments.runner import _dataset_hash

    good = build_dataset({"BTC": candles}, ExperimentConfig())
    before = _dataset_hash(good)
    good.X.rename(columns={good.X.columns[0]: "%different_semantics"}, inplace=True)
    assert _dataset_hash(good) != before
