"""Native split isolation: violations must fail before any learned transform."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_strategy.errors import DataContractError
from quant_strategy.training.native_isolation import (
    bind_cache_contract,
    purge_native_split,
    validate_native_config,
    validate_training_alignment,
)


def _split(candles, config, *, horizon=3, weight_factor=0):
    from freqtrade.configuration.config_validation import validate_config_schema
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

    current = deepcopy(config)
    current["freqai"]["feature_parameters"]["label_period_candles"] = horizon
    current["freqai"]["feature_parameters"]["weight_factor"] = weight_factor
    validate_config_schema(current)
    raw = candles.copy()
    raw.index = pd.Index(np.arange(len(raw)) + 1000)
    raw["%feature"] = raw.close
    raw["&-s_return"] = raw.close.shift(-horizon) / raw.close - 1
    dk = FreqaiDataKitchen(current, live=True, pair="BTC/USDT:USDT")
    dk.find_features(raw)
    dk.find_labels(raw)
    features, labels = dk.filter_features(
        raw, dk.training_features_list, dk.label_list, training_filter=True
    )
    dd = dk.make_train_test_datasets(features, labels)
    return current, raw, dk, dd


@pytest.fixture
def native_config():
    return json.loads(Path("config.json").read_text())


def test_equality_greater_and_less_than_boundary(candles, native_config):
    current, raw, dk, dd = _split(candles, native_config)
    samples = purge_native_split(raw, dk.pair, dk, dd, current)
    purged = samples[samples.assignment == "purged"]
    kept = samples[samples.assignment == "train"]
    boundary = samples[samples.assignment == "validation"].available_at.min()
    assert len(purged) == 3
    assert (purged.label_end_time == boundary).sum() == 1
    assert (purged.label_end_time > boundary).sum() == 2
    assert (kept.label_end_time < boundary).all()
    assert dd["train_features"].index.equals(dd["train_labels"].index)
    assert len(dd["train_weights"]) == len(kept)
    assert dd["train_features"].index.min() == 1000


def test_weight_and_metadata_alignment(candles, native_config):
    current, raw, dk, dd = _split(candles, native_config, weight_factor=0.5)
    before = pd.Series(dd["train_weights"], index=dd["train_features"].index)
    samples = purge_native_split(raw, dk.pair, dk, dd, current)
    np.testing.assert_array_equal(dd["train_weights"], before.loc[dd["train_features"].index])
    kept = samples[samples.assignment == "train"]
    assert kept.source_index.tolist() == dd["train_features"].index.map(str).tolist()
    np.testing.assert_array_equal(kept.weight, dd["train_weights"])
    assert samples.sample_id.is_unique
    # Native trained_dates is a filtered-history artifact, not just the train split.
    assert len(dk.train_dates) == len(raw) - 3


@pytest.mark.parametrize("kind", ["train_labels", "test_labels", "train_weights", "test_weights"])
def test_misaligned_labels_or_weights_fail(candles, native_config, kind):
    current, raw, dk, dd = _split(candles, native_config, weight_factor=0.5)
    dd[kind] = dd[kind].iloc[::-1] if isinstance(dd[kind], pd.DataFrame) else dd[kind][::-1]
    with pytest.raises(DataContractError, match="align|weight"):
        purge_native_split(raw, dk.pair, dk, dd, current)


@pytest.mark.parametrize(
    "fault", ["missing_date", "duplicate_date", "gap", "duplicate_index", "empty"]
)
def test_bad_time_or_identity_fails(candles, native_config, fault):
    current, raw, dk, dd = _split(candles, native_config)
    if fault == "missing_date":
        raw.loc[raw.index[4], "date"] = pd.NaT
    elif fault == "duplicate_date":
        raw.loc[raw.index[4], "date"] = raw.date.iloc[3]
    elif fault == "gap":
        raw.loc[raw.index[4] :, "date"] += pd.Timedelta("4h")
    elif fault == "duplicate_index":
        raw.index = [0] * len(raw)
    else:
        raw = raw.iloc[:0]
    with pytest.raises(DataContractError):
        purge_native_split(raw, dk.pair, dk, dd, current)


def test_no_validation_still_tracks_training(candles, native_config):
    native_config["freqai"]["data_split_parameters"]["test_size"] = 0
    current, raw, dk, dd = _split(candles, native_config)
    samples = purge_native_split(raw, dk.pair, dk, dd, current)
    assert (samples.assignment == "purged").sum() == 0
    assert (samples.assignment == "train").sum() == len(raw) - 3


@pytest.mark.parametrize(
    "flag",
    ["shuffle", "shuffle_after_split", "reverse_train_test_order", "svm", "dbscan", "zero_horizon"],
)
def test_unsupported_modes_fail_before_client_or_fit(native_config, flag):
    if flag == "shuffle":
        native_config["freqai"]["data_split_parameters"]["shuffle"] = True
    elif flag == "zero_horizon":
        native_config["freqai"]["feature_parameters"]["label_period_candles"] = 0
    else:
        key = {"svm": "use_SVM_to_remove_outliers", "dbscan": "use_DBSCAN_to_remove_outliers"}.get(
            flag, flag
        )
        native_config["freqai"]["feature_parameters"][key] = True
    with pytest.raises(DataContractError):
        validate_native_config(native_config)


def test_unmarked_old_cache_and_changed_contract_fail(tmp_path, native_config):
    native_config["user_data_dir"] = tmp_path
    native_config["freqai"]["identifier"] = "isolated"
    root = tmp_path / "models" / "isolated"
    root.mkdir(parents=True)
    (root / "old_model.joblib").write_bytes(b"old model is never loaded")
    with pytest.raises(DataContractError, match="cache|manifest"):
        bind_cache_contract(native_config)
    (root / "old_model.joblib").unlink()
    bind_cache_contract(native_config)
    bind_cache_contract(native_config)
    native_config["freqai"]["feature_parameters"]["label_period_candles"] = 4
    with pytest.raises(DataContractError, match="cache|contract"):
        bind_cache_contract(native_config)


@pytest.mark.parametrize("fault", ["boundary", "purged_row", "labels", "weights"])
def test_post_purge_faults_are_not_repaired_into_a_pass(candles, native_config, fault):
    current, raw, dk, dd = _split(candles, native_config, weight_factor=0.5)
    samples = purge_native_split(raw, dk.pair, dk, dd, current)
    if fault == "boundary":
        samples.loc[dd["train_features"].index[0], "label_end_time"] = (
            samples.validation_start.dropna().iloc[0]
        )
    elif fault == "purged_row":
        unsafe = samples.index[samples.assignment == "purged"][0]
        dd["train_features"].index = [*dd["train_features"].index[:-1], unsafe]
        dd["train_labels"].index = dd["train_features"].index
    elif fault == "labels":
        dd["train_labels"] = dd["train_labels"].iloc[::-1]
    else:
        dd["train_weights"] = dd["train_weights"][::-1]
    with pytest.raises(DataContractError):
        validate_training_alignment(samples, dd)


def test_cache_cannot_reuse_predictions_after_source_file_change(tmp_path, native_config):
    native_config["user_data_dir"] = tmp_path / "userdir"
    native_config["datadir"] = tmp_path / "input"
    native_config["exchange"]["pair_whitelist"] = ["BTC/USDT:USDT"]
    native_config["freqai"]["feature_parameters"]["include_corr_pairlist"] = []
    path = tmp_path / "input/futures/BTC_USDT_USDT-4h-futures.feather"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"actual cache key follows bytes, not mtime")
    bind_cache_contract(native_config)
    path.write_bytes(b"input was replaced")
    with pytest.raises(DataContractError, match="contract"):
        bind_cache_contract(native_config)


@pytest.mark.parametrize(
    "fault",
    ["truncated_marker", "duplicate_key", "unproven_model", "old_metadata", "unproven_prediction"],
)
def test_valid_cache_root_does_not_bless_invalid_artifacts(tmp_path, native_config, fault):
    native_config["user_data_dir"] = tmp_path
    native_config["freqai"]["identifier"] = "cache-fault-test"
    bind_cache_contract(native_config)
    root = tmp_path / "models/cache-fault-test"
    if fault == "truncated_marker":
        (root / "native_training_contract.json").write_text("{")
    elif fault == "duplicate_key":
        (root / "native_training_contract.json").write_text('{"version":1,"version":2}')
    elif fault == "unproven_model":
        (root / "old_model.joblib").write_bytes(b"old cache must not load")
    elif fault == "old_metadata":
        (root / "old_metadata.json").write_text('{"model_filename":"old"}')
    else:
        (root / "old_prediction.feather").write_bytes(b"unknown prediction cache")
    with pytest.raises(DataContractError, match="cache"):
        bind_cache_contract(native_config)
