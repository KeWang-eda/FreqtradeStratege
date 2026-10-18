"""Real FreqAI preprocessors/XGBoost; spies only observe external fit boundaries."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_strategy.backends.freqai import add_freqai_period_features
from quant_strategy.errors import DataContractError
from quant_strategy.labels import set_regression_target
from quant_strategy.market_data import load_ohlcv
from quant_strategy.training.native_isolation import file_sha256


def _context(tmp_path, raw, *, test_size=0.2, weight_factor=0.5):
    from freqtrade.configuration.config_validation import validate_config_schema
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

    from freqaimodels.XGBoostRegressorES import XGBoostRegressorES

    config = json.loads(Path("config.json").read_text())
    config["user_data_dir"] = tmp_path
    config["freqai"]["identifier"] = "native-isolation-development-test"
    config["exchange"]["pair_whitelist"] = ["BTC/USDT:USDT"]
    config["freqai"]["feature_parameters"]["include_corr_pairlist"] = []
    config["freqai"]["activate_tensorboard"] = False
    config["freqai"]["feature_parameters"]["weight_factor"] = weight_factor
    config["freqai"]["data_split_parameters"]["test_size"] = test_size
    # This is an explicitly small development model, never formal OOS evidence.
    config["freqai"]["model_training_parameters"] = {
        "n_estimators": 12,
        "max_depth": 2,
        "early_stopping_rounds": 3,
        "n_jobs": 1,
        "eval_metric": "rmse",
    }
    validate_config_schema(config)
    model = XGBoostRegressorES(config)
    model.live = False
    dk = FreqaiDataKitchen(config, live=True, pair="BTC/USDT:USDT")
    dk.data_path = tmp_path / "training"
    populated = add_freqai_period_features(raw.copy(), 14)
    populated = set_regression_target(populated, 3, "volnorm")
    dk.find_features(populated)
    dk.find_labels(populated)
    return model, dk, populated


def test_actual_preprocessing_and_early_stopping_exclude_all_purged_rows(
    tmp_path, candles, monkeypatch
):
    model, dk, populated = _context(tmp_path, candles)
    observed_label_fit = []
    original_fit = dk.fit_labels

    def observed_fit():
        observed_label_fit.extend(dk.data_dictionary["train_labels"].index.tolist())
        return original_fit()

    monkeypatch.setattr(dk, "fit_labels", observed_fit)
    model.model = model.train(populated, dk.pair, dk)
    directory = model.last_native_audit_path
    report = json.loads((directory / "audit.json").read_text())
    samples = pd.read_parquet(directory / "samples.parquet")
    train = samples[samples.assignment == "train"]
    purged = samples[samples.assignment == "purged"]
    assert len(purged) == 3
    assert report["phase"] == "trained"
    assert report["status"] == "PASS"
    assert observed_label_fit == train.index.tolist()
    assert set(observed_label_fit).isdisjoint(purged.index)
    assert dk.feature_pipeline.fit_indices.equals(train.index)
    assert dk.label_pipeline.fit_indices.equals(train.index)
    assert len(model.model.evals_result()["validation_0"]["rmse"]) > 0
    transformed = dk.data_dictionary
    assert transformed["train_features"].index.equals(transformed["train_labels"].index)
    np.testing.assert_array_equal(transformed["train_weights"], train.weight)
    for filename, fingerprint in report["artifacts"].items():
        assert file_sha256(directory / filename) == fingerprint
    const_mask = dk.feature_pipeline["const"].mask
    original = populated.loc[train.index, dk.training_features_list].to_numpy()
    scaler = dk.feature_pipeline["scaler"]._skl
    np.testing.assert_array_equal(scaler.data_min_, original[:, const_mask].min(axis=0))
    np.testing.assert_array_equal(scaler.data_max_, original[:, const_mask].max(axis=0))
    assert int(scaler.n_samples_seen_) == len(train)
    assert float(dk.data["labels_mean"]["&-s_return"]) == pytest.approx(
        populated.loc[train.index, "&-s_return"].mean()
    )


def test_validation_extremes_never_fit_training_scaler(tmp_path, candles):
    model, dk, populated = _context(tmp_path, candles)
    # Keep actual labels fixed; the validation-only feature extreme must not reach fit.
    populated.loc[populated.index[-35:], dk.training_features_list[0]] = 1e9
    model.model = model.train(populated, dk.pair, dk)
    report = json.loads((model.last_native_audit_path / "audit.json").read_text())
    feature_scaler = dk.feature_pipeline["scaler"]._skl
    assert float(feature_scaler.data_max_.max()) < 1e9
    assert len(report["preprocessor_fit"]["feature_pipeline"]["sample_ids"]) == len(
        dk.data_dictionary["train_features"]
    )


@pytest.mark.parametrize("test_size", [0, 0.2])
def test_actual_real_btc_training_and_prediction(tmp_path, test_size):
    raw = load_ohlcv("data/futures/BTC_USDT_USDT-4h-futures.feather").iloc[-500:].copy()
    train_raw, predict_raw = raw.iloc[:-20], raw.iloc[-20:]
    model, dk, populated = _context(tmp_path, train_raw, test_size=test_size)
    model.model = model.train(populated, dk.pair, dk)
    prediction_frame = set_regression_target(
        add_freqai_period_features(raw.copy(), 14), 3, "volnorm"
    )
    prediction_frame = prediction_frame.loc[predict_raw.index]
    output, ready = model.predict(prediction_frame, dk)
    assert len(output) == len(ready) == 20
    assert np.isfinite(output["&-s_return"]).all()
    report = json.loads((model.last_native_audit_path / "audit.json").read_text())
    assert report["counts"].get("purged", 0) == (0 if test_size == 0 else 3)


@pytest.mark.parametrize("kind", ["train_labels", "train_weights", "test_weights"])
def test_native_split_corruption_fails_before_any_fit(tmp_path, candles, monkeypatch, kind):
    model, dk, populated = _context(tmp_path, candles)
    original_split = dk.make_train_test_datasets
    entered_fit = []

    def bad_split(features, labels):
        dd = original_split(features, labels)
        dd[kind] = dd[kind].iloc[::-1] if isinstance(dd[kind], pd.DataFrame) else dd[kind][::-1]
        return dd

    monkeypatch.setattr(dk, "make_train_test_datasets", bad_split)
    monkeypatch.setattr(dk, "fit_labels", lambda: entered_fit.append(True))
    with pytest.raises(DataContractError, match="align|weight"):
        model.train(populated, dk.pair, dk)
    assert entered_fit == []


def test_failed_real_model_fit_keeps_failed_artifact(tmp_path, candles, monkeypatch):
    model, dk, populated = _context(tmp_path, candles)

    def injected_failure(*args, **kwargs):
        raise RuntimeError("injected model boundary failure")

    monkeypatch.setattr(model, "fit", injected_failure)
    with pytest.raises(RuntimeError, match="injected"):
        model.train(populated, dk.pair, dk)
    report = json.loads((model.last_native_audit_path / "audit.json").read_text())
    assert report["status"] == "FAIL"
    assert report["phase"] == "failed"
    assert (model.last_native_audit_path / "train_after_preprocessing.parquet").exists()


def test_actual_reused_datakitchen_keeps_distinct_window_fit_identities(tmp_path):
    raw = load_ohlcv("data/futures/BTC_USDT_USDT-4h-futures.feather").iloc[-500:].copy()
    model, dk, first = _context(tmp_path, raw.iloc[:300])
    model.model = model.train(first, dk.pair, dk)
    first_path = model.last_native_audit_path
    second = set_regression_target(
        add_freqai_period_features(raw.iloc[180:].copy(), 14), 3, "volnorm"
    )
    model.model = model.train(second, dk.pair, dk)
    second_path = model.last_native_audit_path
    assert first_path != second_path
    report = json.loads((second_path / "audit.json").read_text())
    samples = pd.read_parquet(second_path / "samples.parquet")
    expected = samples[samples.assignment == "train"].sample_id.tolist()
    assert report["preprocessor_fit"]["feature_pipeline"]["sample_ids"] == expected
    assert report["preprocessor_fit"]["label_pipeline"]["sample_ids"] == expected
    assert json.loads((first_path / "audit.json").read_text())["status"] == "PASS"


def test_fresh_userdirs_have_identical_logical_audit_reference(tmp_path, candles):
    first_model, first_dk, first_input = _context(tmp_path / "first", candles)
    second_model, second_dk, second_input = _context(tmp_path / "second", candles)
    first_model.model = first_model.train(first_input, first_dk.pair, first_dk)
    second_model.model = second_model.train(second_input, second_dk.pair, second_dk)
    assert first_dk.data["native_training_audit"] == second_dk.data["native_training_audit"]
    assert first_model.last_native_audit_path.name == second_model.last_native_audit_path.name
    first_report = json.loads((first_model.last_native_audit_path / "audit.json").read_text())
    second_report = json.loads((second_model.last_native_audit_path / "audit.json").read_text())
    assert first_report["input_fingerprint"] == second_report["input_fingerprint"]
    assert first_report["cache_contract_sha256"] == second_report["cache_contract_sha256"]
    np.testing.assert_array_equal(
        first_model.model.predict(first_dk.data_dictionary["train_features"]),
        second_model.model.predict(second_dk.data_dictionary["train_features"]),
    )


def test_repeated_input_cannot_overwrite_audit_or_refit(tmp_path, candles, monkeypatch):
    model, dk, populated = _context(tmp_path, candles)
    model.model = model.train(populated, dk.pair, dk)
    audit_path = model.last_native_audit_path / "audit.json"
    first_fingerprint = file_sha256(audit_path)
    entered_fit = []
    monkeypatch.setattr(dk, "fit_labels", lambda: entered_fit.append(True))
    with pytest.raises(DataContractError, match="already exists.*fresh userdir"):
        model.train(populated, dk.pair, dk)
    assert entered_fit == []
    assert file_sha256(audit_path) == first_fingerprint
    assert json.loads(audit_path.read_text())["status"] == "PASS"
