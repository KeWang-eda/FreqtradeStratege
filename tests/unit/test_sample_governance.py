"""Data gaps must quarantine affected samples, never change horizon silently."""

from dataclasses import replace

import pandas as pd
import pytest

from quant.config import ExperimentConfig
from quant.dataset import Dataset, build_dataset
from quant.errors import DataContractError


def test_gap_excludes_labels_crossing_missing_bar_and_restarts_warmup(candles):
    missing = candles.date.iloc[100]
    raw = candles.drop(index=100).reset_index(drop=True)
    dataset = build_dataset({"BTC": raw}, ExperimentConfig())
    assert not (
        (dataset.metadata.candle_timestamp < missing) & (dataset.metadata.label_end_time > missing)
    ).any()
    assert not dataset.metadata.candle_timestamp.between(
        missing + pd.Timedelta(hours=4), missing + pd.Timedelta(hours=24 * 4)
    ).any()
    assert "label_window_gap" in set(dataset.exclusions.reason)
    assert "feature_warmup" in set(dataset.exclusions.reason)


def test_every_input_row_has_eligibility_identity_and_exclusion_reason(candles):
    dataset = build_dataset({"BTC": candles}, ExperimentConfig())
    assert dataset.metadata.sample_id.is_unique
    assert dataset.metadata.data_version.str.fullmatch(r"[0-9a-f]{64}").all()
    assert (dataset.metadata.available_at <= dataset.metadata.label_end_time).all()
    assert (dataset.metadata.feature_start_time <= dataset.metadata.candle_timestamp).all()
    assert set(dataset.metadata.sample_id).isdisjoint(dataset.exclusions.sample_id)
    assert dataset.exclusions.sample_id.nunique() + len(dataset.X) == len(candles)
    assert dataset.exclusions.reason.notna().all()


def test_dataset_rejects_invented_or_duplicated_provenance(candles):
    good = build_dataset({"BTC": candles}, ExperimentConfig())
    with pytest.raises(DataContractError):
        Dataset(good.X, good.y, pd.DataFrame({"anything": range(len(good.X))}), {})
    bad = good.metadata.copy()
    bad.loc[bad.index[0], "label_end_time"] = bad.candle_timestamp.iloc[0]
    with pytest.raises(DataContractError):
        replace(good, metadata=bad)
    bad = good.metadata.copy()
    bad.iloc[1] = bad.iloc[0]
    with pytest.raises(DataContractError):
        replace(good, metadata=bad)


def test_off_grid_and_zero_eligible_are_hard_failures(candles):
    with pytest.raises(DataContractError):
        build_dataset(
            {"BTC": candles.assign(date=candles.date + pd.Timedelta(minutes=1))}, ExperimentConfig()
        )
    with pytest.raises(DataContractError):
        build_dataset({"BTC": candles.iloc[:10]}, ExperimentConfig())


def test_dataset_build_is_repeatable_and_read_only(candles):
    before = candles.copy(deep=True)
    first = build_dataset({"BTC": candles}, ExperimentConfig())
    second = build_dataset({"BTC": candles}, ExperimentConfig())
    pd.testing.assert_frame_equal(first.X, second.X)
    pd.testing.assert_frame_equal(first.metadata, second.metadata)
    pd.testing.assert_frame_equal(first.exclusions, second.exclusions)
    pd.testing.assert_frame_equal(candles, before)


def test_an_empty_pair_cannot_be_silently_hidden_by_other_pair(candles):
    with pytest.raises(DataContractError, match="BTC"):
        build_dataset({"BTC": candles.iloc[:10], "ETH": candles}, ExperimentConfig())


@pytest.mark.parametrize("replacement", [True, "100.0"])
def test_false_numeric_dtypes_cannot_enter_samples(candles, replacement):
    with pytest.raises(DataContractError, match="numeric"):
        build_dataset({"BTC": candles.assign(volume=replacement)}, ExperimentConfig())
