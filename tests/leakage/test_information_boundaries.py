"""Future perturbation, training isolation and candle-close alignment audits."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from quant.config import ExperimentConfig, ModelConfig, ValidationConfig
from quant.dataset import Dataset, build_dataset
from quant.errors import DataContractError
from quant.execution.coordinator import candidates_from_batch
from quant.features import build_features
from quant.market_data.time_index import align_closed_candles
from quant.prediction import PredictionBatch, PredictionRecord
from quant.backends.standalone import StandaloneBackend
from quant.training.contracts import TrainingRequest
from quant.validation import TimeSeriesSplitter


@pytest.mark.parametrize("optional", [(), ("laguerre",), ("vwmacd",), ("tke",), ("vfi",), ("rmi",)])
def test_future_perturbation_does_not_change_historical_features(candles, optional):
    # Prefix equality exercises every enabled optional feature, too.
    complete = build_features(candles, enabled_features=optional)
    prefix = build_features(candles.iloc[:180].copy(), enabled_features=optional)
    pd.testing.assert_frame_equal(complete.iloc[:180], prefix)


def test_test_distribution_cannot_change_fit_parameters(candles):
    config = ExperimentConfig(validation=ValidationConfig(method="fixed_holdout", n_splits=1))
    dataset = build_dataset({"BTC": candles}, config)
    fold = TimeSeriesSplitter(config.validation).split(
        pd.DatetimeIndex(dataset.metadata.available_at), dataset.metadata.label_end_time
    )[0]
    backend = StandaloneBackend()
    original = backend.run_training(TrainingRequest(dataset, fold, config, "original"))
    perturbed_X = dataset.X.copy()
    perturbed_X.iloc[fold.test_indices] = 1e8
    perturbed_y = dataset.y.copy()
    perturbed_y.iloc[fold.test_indices] = -1000
    changed = backend.run_training(
        TrainingRequest(
            Dataset(perturbed_X, perturbed_y, dataset.metadata, {}), fold, config, "changed"
        )
    )
    np.testing.assert_array_equal(
        original.models["BTC"][0]["scale"].mean_, changed.models["BTC"][0]["scale"].mean_
    )
    np.testing.assert_array_equal(
        original.models["BTC"][1].estimator.coef_, changed.models["BTC"][1].estimator.coef_
    )


def test_early_stopping_uses_inner_validation_only(candles):
    config = ExperimentConfig(
        model=ModelConfig(
            name="xgboost", params={"n_estimators": 20, "early_stopping_rounds": 3, "max_depth": 2}
        ),
        validation=ValidationConfig(method="fixed_holdout", n_splits=1),
    )
    dataset = build_dataset({"BTC": candles}, config)
    fold = TimeSeriesSplitter(config.validation).split(
        pd.DatetimeIndex(dataset.metadata.available_at), dataset.metadata.label_end_time
    )[0]
    first = StandaloneBackend().run_training(TrainingRequest(dataset, fold, config, "a"))
    y = dataset.y.copy()
    y.iloc[fold.test_indices] *= -1e6
    second = StandaloneBackend().run_training(
        TrainingRequest(Dataset(dataset.X, y, dataset.metadata, {}), fold, config, "b")
    )
    np.testing.assert_array_equal(
        first.predictions.to_frame().prediction, second.predictions.to_frame().prediction
    )
    inner = first.audit[1]
    assert pd.Timestamp(inner["inner_training_end"]) < pd.Timestamp(inner["inner_validation_start"])
    for record in first.predictions.records:
        assert record.training_data_end < record.candle_timestamp + pd.Timedelta(hours=4)


def test_unclosed_daily_candle_not_available_to_four_hour_signal(candles):
    daily = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC"),
            "%daily": [10.0, 999.0, 777.0],
        }
    )
    aligned = align_closed_candles(candles[["date"]].iloc[:18], daily, "4h", "1d")
    assert aligned["%daily"].iloc[:5].isna().all()
    assert aligned["%daily"].iloc[5] == 10
    changed = daily.copy()
    changed.loc[1:, "%daily"] *= -1e5
    perturbed = align_closed_candles(candles[["date"]].iloc[:11], changed, "4h", "1d")
    pd.testing.assert_series_equal(aligned["%daily"].iloc[:11], perturbed["%daily"])


def test_alignment_accepts_mixed_timestamp_resolutions(candles):
    base = candles[["date"]].iloc[:12].copy()
    base["date"] = base.date.astype("datetime64[ms, UTC]")
    daily = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=2, freq="D", tz="UTC").as_unit("ns"),
            "%daily": [10, 20],
        }
    )
    aligned = align_closed_candles(base, daily, "4h", "1d")
    assert aligned["%daily"].iloc[5] == 10


def test_mixed_pair_timestamps_fail_and_missing_snapshot_defers():
    date = pd.Timestamp("2024-01-01", tz="UTC")
    record = PredictionRecord("BTC", date, 1, "raw_return", "ridge", "v1", "v1", "raw", 3, True)
    batch = PredictionBatch((record,), "test", "standalone")
    assert candidates_from_batch(batch, ["BTC", "ETH"], date) is None
    assert (
        candidates_from_batch(
            PredictionBatch((replace(record, is_ready=False),), "test", "standalone"), ["BTC"], date
        )
        == ()
    )
    mixed = PredictionBatch(
        (record, replace(record, pair="ETH", candle_timestamp=date + pd.Timedelta(hours=4))),
        "test",
        "standalone",
    )
    with pytest.raises(DataContractError):
        candidates_from_batch(mixed, ["BTC", "ETH"], date)
