"""Compare exact legacy outputs captured before editing the production modules."""

import json
from pathlib import Path

import numpy as np
from conftest import make_ohlcv

from quant_strategy.backends.freqai import add_freqai_period_features
from quant_strategy.features import add_baseline_features, add_basic_price_features
from quant_strategy.labels import set_regression_target
from quant_strategy.portfolio import (
    build_candidate,
    decide_position_action,
    resolve_target_position,
)


def test_features_and_labels_against_frozen_code():
    golden = json.loads(Path(__file__).with_name("baseline.json").read_text())
    frame = make_ohlcv(golden["candles"])
    for period in (6, 14, 24):
        actual = add_freqai_period_features(frame.copy(), period).filter(regex="^%")
        expected = golden["outputs"][f"period_{period}"]
        assert list(actual.columns) == list(expected)
        for column in actual:
            np.testing.assert_allclose(
                actual[column],
                np.asarray(expected[column], dtype=float),
                rtol=1e-10,
                atol=1e-14,
                equal_nan=True,
            )
    actual = add_baseline_features(add_basic_price_features(frame.copy()), [])
    for column, values in golden["outputs"]["standard"].items():
        np.testing.assert_allclose(
            actual[column], np.asarray(values, dtype=float), rtol=1e-10, atol=1e-14, equal_nan=True
        )
    for mode in ("raw", "volnorm"):
        actual = set_regression_target(frame.copy(), 3, mode)
        np.testing.assert_allclose(
            actual["&-s_return"],
            np.asarray(golden["outputs"]["label_" + mode], dtype=float),
            rtol=1e-10,
            atol=1e-14,
            equal_nan=True,
        )


def test_frozen_tie_and_zero_prediction_rules():
    # Legacy max() selected the first input for equal absolute predictions.
    candidates = [build_candidate("ETH", -1.0, True), build_candidate("BTC", 1.0, True)]
    assert resolve_target_position(candidates).pair == "ETH"
    zero = resolve_target_position([build_candidate("BTC", 0.0, True)])
    assert zero.side == "short"
    assert decide_position_action("BTC", "long", zero).reason == "rotate_to_opposite_side"


def test_native_configuration_parameters_are_unchanged():
    def without_comments(value):
        if isinstance(value, dict):
            return {
                key: without_comments(item)
                for key, item in value.items()
                if not key.startswith("_comment")
            }
        if isinstance(value, list):
            return [without_comments(item) for item in value]
        return value

    before = json.loads(Path("docs/baseline/config.json").read_text())
    after = json.loads(Path("config.json").read_text())
    # The correctness fix changes the training sample set. Explicitly require
    # its incompatible cache namespace; every actual parameter stays frozen.
    assert before["freqai"].pop("identifier") == "mystrategy-4h-regression-72pair-corr-s1-v1"
    assert after["freqai"].pop("identifier") == "mystrategy-4h-regression-72pair-corr-s1-purged-v2"
    assert without_comments(before) == without_comments(after)
