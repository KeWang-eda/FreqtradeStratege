"""Actual installed Freqtrade callback and FreqAI model fit contracts."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from MyStrategy import MyStrategy
from quant_strategy.backends.freqai import FreqAIBackendAdapter
from quant_strategy.infrastructure.snapshot_store import PredictionSnapshotStore


def strategy_with_pool(pairs=("BTC", "ETH")):
    strategy = MyStrategy(
        {"runmode": "backtest", "my_experiment": {}, "freqai": {"identifier": "test"}}
    )
    strategy.freqai_info = {"feature_parameters": {"label_period_candles": 3}}
    strategy.dp = SimpleNamespace(current_whitelist=lambda: list(pairs))
    return strategy


def predicted_frame(values, start="2024-01-01"):
    return pd.DataFrame(
        {
            "date": pd.date_range(start, periods=len(values), freq="4h", tz="UTC"),
            "&-s_return": values,
            "do_predict": 1,
        }
    )


def test_incomplete_pool_retries_then_rotates_and_signals():
    strategy = strategy_with_pool()
    stamp = pd.Timestamp("2024-01-01", tz="UTC")
    strategy._snapshots.remember("BTC", predicted_frame([0.1]))
    assert strategy._pool_candidates(stamp) is None
    held = SimpleNamespace(is_short=False)
    assert strategy.custom_exit("BTC", held, stamp, 100, 0) is None
    strategy._snapshots.remember("ETH", predicted_frame([-0.5]))
    assert strategy._target_position(stamp).pair == "ETH"
    assert strategy.confirm_trade_entry("ETH", "limit", 1, 1, "GTC", stamp, None, "short")
    assert not strategy.confirm_trade_entry("BTC", "limit", 1, 1, "GTC", stamp, None, "long")
    assert strategy.custom_exit("BTC", held, stamp, 100, 0) == "rotate_to_stronger_pair"
    assert strategy.custom_exit("ETH", SimpleNamespace(is_short=True), stamp, 100, 0) is None


def test_complete_invalid_pool_exits_and_nonfinite_signals_are_filtered():
    strategy = strategy_with_pool(("BTC",))
    frame = predicted_frame([np.nan])
    strategy._snapshots.remember("BTC", frame)
    assert (
        strategy.custom_exit("BTC", SimpleNamespace(is_short=False), frame.date.iloc[0], 100, 0)
        == "no_eligible_target"
    )
    signals = strategy.populate_entry_trend(
        predicted_frame([0.001, -0.001, 0, np.inf, -np.inf, np.nan]), {}
    )
    assert list(signals.enter_long) == [1, 0, 0, 0, 0, 0]
    assert list(signals.enter_short) == [0, 1, 0, 0, 0, 0]
    exits = strategy.populate_exit_trend(signals, {})
    assert not exits[["exit_long", "exit_short"]].to_numpy().any()


def test_freqai_lifecycle_delegation(candles):
    strategy = strategy_with_pool(("BTC",))
    output = predicted_frame([0.1])

    def start(frame, metadata, instance):
        assert instance is strategy and frame is candles and metadata == {"pair": "BTC"}
        return output

    strategy.freqai = SimpleNamespace(start=start)
    assert strategy.populate_indicators(candles, {"pair": "BTC"}) is output
    assert strategy._snapshots.get_row("BTC", output.date.iloc[0]) is not None
    assert FreqAIBackendAdapter().describe_capabilities().early_stopping


def test_live_snapshot_is_bounded_and_exact_time_only():
    store = PredictionSnapshotStore(2, False)
    frame = predicted_frame([1, 2, 3])
    store.remember("BTC", frame)
    assert store.get_row("BTC", frame.date.iloc[0]) is None
    assert store.get_row("BTC", frame.date.iloc[-1])[0]["&-s_return"] == 3
    store.remember("BTC", frame.iloc[-1:].assign(**{"&-s_return": 4}))
    assert store.get_row("BTC", frame.date.iloc[-1])[0]["&-s_return"] == 4
    assert store.get_row("BTC", frame.date.iloc[-1] + pd.Timedelta(hours=4)) is None


@pytest.mark.parametrize("model_name", ["MomentumRidgeRegressor", "XGBoostRegressorES"])
def test_installed_freqai_train_predict_lifecycle(tmp_path, candles, model_name):
    # Use actual FreqAI data kitchen, transforms and BaseRegressionModel methods.
    from freqtrade.configuration.config_validation import validate_config_schema
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

    from freqaimodels.MomentumRidgeRegressor import MomentumRidgeRegressor
    from freqaimodels.XGBoostRegressorES import XGBoostRegressorES

    config = json.loads(Path("config.json").read_text())
    config["user_data_dir"] = tmp_path
    config["freqai"]["identifier"] = model_name
    config["freqai"]["activate_tensorboard"] = False
    config["freqai"]["feature_parameters"]["DI_threshold"] = 0
    config["freqai"]["model_training_parameters"] = (
        {"ridge_alpha": 10}
        if model_name == "MomentumRidgeRegressor"
        else {
            "n_estimators": 15,
            "max_depth": 2,
            "early_stopping_rounds": 3,
            "n_jobs": 1,
            "eval_metric": "rmse",
        }
    )
    validate_config_schema(config)
    model_type = (
        MomentumRidgeRegressor if model_name == "MomentumRidgeRegressor" else XGBoostRegressorES
    )
    model = model_type(config)
    model.live = False
    kitchen = FreqaiDataKitchen(config, live=True, pair="BTC/USDT:USDT")
    kitchen.data_path = tmp_path / "training"
    kitchen.data_path.mkdir()
    strategy = strategy_with_pool()
    features = strategy.feature_engineering_expand_all(candles.copy(), 14, {})
    features = strategy.set_freqai_targets(features, {})
    kitchen.find_features(features)
    kitchen.find_labels(features)
    model.model = model.train(features.iloc[:-20].copy(), "BTC/USDT:USDT", kitchen)
    output, ready = model.predict(features.iloc[-20:].copy(), kitchen)
    assert len(output) == len(ready) == 20
    assert "&-s_return" in output
    assert np.isfinite(output["&-s_return"]).all()
