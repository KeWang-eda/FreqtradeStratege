"""Interchangeable model/splitter contracts include unsupported capabilities."""

import numpy as np
import pandas as pd
import pytest

from quant.backends.freqai import FreqAIBackendAdapter
from quant.config import ModelConfig, StrategyConfig, ValidationConfig
from quant.errors import DataContractError, UnsupportedCapabilityError
from quant.models import create_estimator, create_regressor
from quant.models.standalone import StandaloneRegressor
from quant.validation import TimeSeriesSplitter
from quant.validation.leakage import audit_fold


@pytest.mark.parametrize("name", ["ridge", "xgboost", "xgboost_direction"])
def test_model_fit_predict_save_load(tmp_path, name):
    X = pd.DataFrame({"%a": np.arange(40, dtype=float), "%b": np.sin(np.arange(40))})
    y = X["%a"] * 0.03
    if name == "xgboost_direction":
        y = y - y.mean()
    params = {} if name == "ridge" else {"n_estimators": 12, "max_depth": 2}
    model = create_regressor(ModelConfig(name=name, params=params))
    model.fit(X.iloc[:30], y.iloc[:30])
    expected = model.predict(X.iloc[30:])
    model.save(tmp_path / "model.bin")
    loaded = StandaloneRegressor.load(tmp_path / "model.bin")
    np.testing.assert_allclose(loaded.predict(X.iloc[30:]), expected)
    with pytest.raises(DataContractError):
        loaded.predict(X[["%b", "%a"]])


@pytest.mark.parametrize("name", ["ridge", "xgboost", "xgboost_direction"])
def test_standalone_and_freqai_share_estimator_constructor(name):
    params = {} if name == "ridge" else {"n_estimators": 5, "max_depth": 2}
    common = create_estimator(
        name,
        params,
        seed=42,
        defaults={"n_jobs": 1, "tree_method": "hist"}
        if name in {"xgboost", "xgboost_direction"}
        else None,
    )
    standalone = create_regressor(ModelConfig(name=name, params=params), seed=42)
    assert type(standalone.estimator) is type(common)
    assert standalone.estimator.get_params() == common.get_params()


@pytest.mark.parametrize(
    "method", ["fixed_holdout", "expanding_window", "rolling_window", "purged_walk_forward"]
)
def test_split_contract_global_pair_boundaries(method):
    dates = pd.date_range("2024-01-01", periods=80, freq="4h", tz="UTC")
    times = dates.repeat(2)
    ends = pd.Series(times + pd.Timedelta(hours=12))
    config = ValidationConfig(
        method=method,
        train_window_size=20 if method == "rolling_window" else None,
        embargo_candles=4,
    )
    folds = TimeSeriesSplitter(config).split(times, ends)
    for fold in folds:
        assert audit_fold(fold, times, ends)["passed"]
        assert not set(times[fold.train_indices]).intersection(times[fold.test_indices])
        assert len(fold.purged_indices) == 6  # Equality at the boundary is purged.
        assert len(fold.embargoed_indices) == 2  # Fourth preceding timestamp.
        assert fold.train_indices.size % 2 == fold.test_indices.size % 2 == 0
        if method == "rolling_window":
            assert len(times[fold.train_indices].unique()) <= 20


def test_freqai_capability_rejections():
    adapter = FreqAIBackendAdapter()
    assert not adapter.describe_capabilities().independent_splits
    with pytest.raises(UnsupportedCapabilityError):
        adapter.run_training(None)
    with pytest.raises(UnsupportedCapabilityError):
        adapter.predict(None)
    with pytest.raises(UnsupportedCapabilityError):
        create_regressor(ModelConfig(backend="freqai", name="XGBoostRegressorES"))


def test_freqai_predictions_have_explicit_semantics():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=2, freq="4h", tz="UTC"),
            "&-s_return": [0.8, np.nan],
            "do_predict": [1, 0],
        }
    )
    batch = FreqAIBackendAdapter().from_frame(
        frame,
        "BTC",
        StrategyConfig(label="volnorm", label_period_candles=3),
        model_name="XGBoostRegressorES",
        model_version="frozen-v1",
    )
    assert batch.backend == "freqai"
    assert batch.records[0].prediction_kind == "volnorm_return"
    assert batch.records[0].training_data_end is None
    assert not batch.records[1].is_ready
    assert len(batch.to_frame()) == 2
