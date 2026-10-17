"""Configuration and target boundaries required by the migration contract."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import talib.abstract as ta

from quant_strategy.config import (
    LabelConfig,
    ModelConfig,
    StrategyConfig,
    ValidationConfig,
    load_config,
)
from quant_strategy.errors import ConfigurationError, DataContractError
from quant_strategy.features import (
    add_baseline_features,
    add_period_expanded_features,
    build_features,
)
from quant_strategy.labels import build_labels, set_regression_target
from quant_strategy.market_data import validate_ohlcv
from quant_strategy.validation import prediction_metrics


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "typo"},
        {"prediction_horizon": 0},
        {"prediction_horizon": 1.5},
        {"prediction_horizon": True},
        {"volatility_period": 1},
    ],
)
def test_invalid_label_config(kwargs):
    with pytest.raises(ConfigurationError):
        LabelConfig(**kwargs)


@pytest.mark.parametrize(
    "kwargs", [{"backend": "typo"}, {"name": "lightgbm"}, {"backend": "freqai", "name": "ridge"}]
)
def test_unknown_models_rejected(kwargs):
    with pytest.raises(ConfigurationError):
        ModelConfig(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "shuffle"},
        {"n_splits": 1},
        {"test_size": 0},
        {"test_size": 1},
        {"embargo_candles": -1},
        {"purge_candles": 3},
        {"method": "rolling_window"},
        {"final_holdout_fraction": 0},
    ],
)
def test_invalid_validation_config(kwargs):
    with pytest.raises(ConfigurationError):
        ValidationConfig(**kwargs)


@pytest.mark.parametrize(
    "raw",
    [
        {"label": "bad"},
        {"features": ["unknown"]},
        {"features": "rmi"},
        {"probe": "false"},
        {"labell": "raw"},
    ],
)
def test_legacy_config_is_validated(raw):
    with pytest.raises(ConfigurationError):
        StrategyConfig.from_strategy(
            {"my_experiment": raw}, {"feature_parameters": {"label_period_candles": 3}}
        )


def test_layering_and_explicit_overrides(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text("research:\n  model:\n    name: ridge\n    params:\n      alpha: 5\n")
    override = tmp_path / "experiment.yaml"
    override.write_text("research:\n  label:\n    mode: volnorm\n")
    config = load_config([base, override], ["seed=7", "model.params.alpha=12"])
    assert config.model.params == {"alpha": 12}
    assert config.seed == 7 and config.label.mode == "volnorm"
    with pytest.raises(ConfigurationError):
        load_config([base], ["modle.name=ridge"])


@pytest.mark.parametrize("mode", ["raw", "volnorm"])
def test_label_formulas_and_information_end(candles, mode):
    config = LabelConfig(mode, 3, 14)
    result = build_labels(candles, config, "4h")
    expected = candles.close.shift(-3) / candles.close - 1
    if mode == "volnorm":
        expected /= ta.ATR(candles, timeperiod=14) / candles.close
    np.testing.assert_allclose(result.target, expected, equal_nan=True)
    assert result.target.iloc[-3:].isna().all()
    assert result.label_end_time.iloc[0] == candles.date.iloc[3] + pd.Timedelta(hours=4)
    assert result.label_end_time.iloc[-3:].isna().all()


def test_period_names_unique_and_index_preserved(candles):
    result = add_period_expanded_features(candles.copy(), 6)
    result = add_period_expanded_features(result, 14)
    assert "%-rsi-period-6" in result and "%-rsi-period-14" in result
    assert result.index.equals(candles.index)
    with pytest.raises(ConfigurationError):
        add_baseline_features(candles.copy(), ["unknown"])


def test_feature_matrix_isolates_labels(candles):
    labeled = set_regression_target(candles.copy(), 3, "raw")
    actual = build_features(labeled)
    labeled["&-s_return"] = 1e12
    pd.testing.assert_frame_equal(actual, build_features(labeled))
    assert all(column.startswith("%") for column in actual)
    with pytest.raises(DataContractError):
        build_features(candles, periods=[6, 6])


@pytest.mark.parametrize(
    "defect", ["duplicate", "unordered", "naive", "nonfinite", "zero", "range"]
)
def test_ohlcv_contract(candles, defect):
    frame = candles.copy()
    if defect == "duplicate":
        frame.loc[1, "date"] = frame.loc[0, "date"]
    elif defect == "unordered":
        frame = frame.iloc[::-1]
    elif defect == "naive":
        frame["date"] = frame.date.dt.tz_localize(None)
    elif defect == "nonfinite":
        frame.loc[0, "volume"] = np.inf
    elif defect == "zero":
        frame.loc[0, "close"] = 0
    else:
        frame.loc[0, "high"] = 0.1
    with pytest.raises(DataContractError):
        validate_ohlcv(frame)


def test_metrics_empty_constant_and_known_values():
    assert prediction_metrics([], [])["rmse"] is None
    assert prediction_metrics([1, 2], [1, 1])["pearson_ic"] is None
    result = prediction_metrics([1, -1], [1, 1])
    assert result["mae"] == 1 and result["direction_accuracy"] == 0.5
    with pytest.raises(ValueError):
        prediction_metrics([1], [1, 2])


def test_resolved_config_rejects_invalid_periods():
    from quant_strategy.config import ExperimentConfig

    with pytest.raises(ConfigurationError):
        replace(ExperimentConfig(), periods=(6, 6))


def test_switching_estimators_drops_incompatible_parameters():
    config = load_config(["configs/base.yaml", "configs/estimators/xgboost.yaml"])
    assert config.model.name == "xgboost"
    assert "alpha" not in config.model.params


@pytest.mark.parametrize("model", ["ridge", "xgboost"])
def test_unknown_model_parameters_fail_before_training(model):
    from quant_strategy.backends import create_regressor

    with pytest.raises(ConfigurationError, match="Unknown model parameters"):
        create_regressor(ModelConfig(name=model, params={"param_typo": 1}))
