"""Feature timing contracts must discover injected future dependencies."""

from dataclasses import replace
from importlib import import_module

import numpy as np
import pandas as pd
import pytest

from quant.config import ExperimentConfig, LabelConfig
from quant.features import build_features
from quant.labels import build_labels
from tests.conftest import make_ohlcv


@pytest.fixture
def contracts():
    return import_module("quant.validation.feature_contracts")


def test_contracts_match_actual_schema_and_explicit_close_availability(contracts, candles):
    config = ExperimentConfig(periods=(6, 14))
    columns = list(build_features(candles, config.periods, config.features))
    report = contracts.build_feature_contracts(config, columns)
    assert report["status"] == "PASS" and set(report["columns"]) == set(columns)
    assert report["feature_count"] == len(columns)
    for value in report["columns"].values():
        assert value["available_at"] == "candle_open + timeframe"
        assert value["latest_dependency"]["offset_candles"] == 0
        assert value["sources"]


def test_recursive_state_starts_at_continuous_segment(contracts):
    config = ExperimentConfig()
    report = contracts.build_feature_contracts(
        config, ["%-rsi-period-6", "%-sma-distance-period-6", "%-volatility-24"]
    )
    rsi = report["columns"]["%-rsi-period-6"]
    assert rsi["recursive_from_segment_start"]
    assert rsi["earliest_dependency"] == {"kind": "segment_start"}
    sma = report["columns"]["%-sma-distance-period-6"]
    assert not sma["recursive_from_segment_start"]
    assert sma["earliest_dependency"]["offset_candles"] == -5
    assert report["columns"]["%-volatility-24"]["earliest_dependency"]["offset_candles"] == -24


@pytest.mark.parametrize("column", ["%-future-mean", "&-s_return", "%-rsi-period-7", "%-laguerre"])
def test_unknown_unconfigured_or_label_column_cannot_get_a_fake_contract(contracts, column):
    report = contracts.build_feature_contracts(ExperimentConfig(), [column])
    assert report["status"] == "BLOCKED"
    assert report["columns"][column]["status"] == "BLOCKED"


def test_empty_and_duplicate_schema_fail(contracts):
    for columns in [[], ["%-return", "%-return"]]:
        assert contracts.build_feature_contracts(ExperimentConfig(), columns)["status"] == "FAIL"


def test_baseline_all_columns_pass_actual_future_perturbation_and_truncation(contracts, candles):
    before = candles.copy(deep=True)
    report = contracts.audit_causality(candles, ExperimentConfig(), cut_points=[80, 160, 220])
    assert report["status"] == "PASS" and report["passed"]
    assert report["feature_count"] == len(build_features(candles).columns)
    assert {item["kind"] for item in report["checks"]} == {"future_perturbation", "truncation"}
    assert all(value > 0 for value in report["finite_prefix_observations"].values())
    assert report["tolerance"] == {"rtol": 0.0, "atol": 0.0}
    pd.testing.assert_frame_equal(before, candles)


@pytest.mark.parametrize("optional", ["laguerre", "vwmacd", "tke", "vfi", "rmi"])
def test_enabled_optional_features_are_audited_without_hardcoded_feature_count(
    contracts, candles, optional
):
    config = replace(ExperimentConfig(), features=(optional,))
    # Default VFI's nested 130-bar operations first produce a finite value at
    # row 259. The ordinary 240-row fixture cannot validate that feature.
    if optional == "vfi":
        short = contracts.audit_causality(candles, config, cut_points=[180, 220])
        assert short["status"] == "BLOCKED"
        assert {"%-vfi", "%-vfi-hist"} <= set(short["unverified_columns"])
        candles = make_ohlcv(400)
        cuts = [300, 360]
    else:
        cuts = [180, 220]
    report = contracts.audit_causality(candles, config, cut_points=cuts)
    assert report["status"] == "PASS", report
    assert report["feature_count"] == len(
        build_features(candles, config.periods, config.features).columns
    )


@pytest.mark.parametrize("leak", ["future_shift", "whole_frame_mean", "backfill"])
def test_injected_known_schema_leak_is_detected_by_values_not_registry(contracts, candles, leak):
    def leaking(frame, periods, enabled_features):
        result = build_features(frame, periods, enabled_features)
        if leak == "future_shift":
            result["%-return"] = frame.close.shift(-1)
        elif leak == "whole_frame_mean":
            result["%-return"] = frame.close.mean()
        else:
            result["%-return"] = frame.close.where(frame.index % 100 == 99).bfill()
        return result

    report = contracts.audit_causality(
        candles, ExperimentConfig(), cut_points=[80, 160, 220], feature_builder=leaking
    )
    assert report["status"] == "FAIL" and not report["passed"]
    assert any(not item["passed"] for item in report["checks"])
    assert report["differences"]


def test_an_unknown_causal_column_remains_blocked(contracts, candles):
    def unknown(frame, periods, enabled_features):
        return build_features(frame, periods, enabled_features).assign(
            **{"%-unreviewed": frame.close}
        )

    report = contracts.audit_causality(candles, ExperimentConfig(), feature_builder=unknown)
    assert report["status"] == "BLOCKED" and not report["passed"]


def test_sub_picounit_future_leak_cannot_hide_under_numeric_tolerance(contracts, candles):
    def tiny_leak(frame, periods, enabled_features):
        result = build_features(frame, periods, enabled_features)
        result["%-return"] += 1e-13 * (frame.close.iloc[-1] / frame.close.iloc[0])
        return result

    report = contracts.audit_causality(
        candles, ExperimentConfig(), cut_points=[80, 160, 220], feature_builder=tiny_leak
    )
    assert report["status"] == "FAIL" and report["differences"]
    differences = [item["maximum_absolute_difference"] for item in report["differences"]]
    assert all(0 < value < 1e-12 for value in differences)


def test_label_future_observation_is_not_misclassified_as_a_feature(contracts, candles):
    labeled = candles.assign(**{"&-s_return": build_labels(candles, LabelConfig(), "4h").target})
    report = contracts.audit_causality(labeled, ExperimentConfig())
    assert report["status"] == "PASS"
    assert "&-s_return" not in report["feature_contracts"]["columns"]
    assert report["scope"] == "features only; future labels are outside this audit"


def test_gap_is_a_state_reset_and_no_feature_depends_on_prior_segment(contracts, candles):
    frame = candles.drop(index=100).reset_index(drop=True)
    seen = []

    def recording(frame, periods, enabled_features):
        seen.append(frame.date.diff().dropna().eq(pd.Timedelta(hours=4)).all())
        return build_features(frame, periods, enabled_features)

    report = contracts.audit_causality(frame, ExperimentConfig(), feature_builder=recording)
    assert report["status"] == "PASS"
    assert report["segment_count"] == 2 and all(seen)
    assert len(report["segments"]) == 2


def test_only_warmup_missing_values_is_not_a_successful_causality_audit(contracts, candles):
    report = contracts.audit_causality(candles.iloc[:10], ExperimentConfig())
    assert report["status"] == "BLOCKED" and not report["passed"]
    assert report["unverified_columns"]


def test_long_segment_cannot_hide_an_unverified_short_segment(contracts):
    frame = make_ohlcv(320).drop(index=10).reset_index(drop=True)
    report = contracts.audit_causality(frame, ExperimentConfig())
    assert report["status"] == "BLOCKED"
    assert not report["unverified_columns"]  # Long segment does have finite values.
    assert report["unverified_segment_columns"][0]["segment_id"] == 0


def test_new_optional_dependency_version_requires_review(contracts, monkeypatch):
    monkeypatch.setattr(contracts.importlib.metadata, "version", lambda package: "unknown-future")
    config = replace(ExperimentConfig(), features=("laguerre",))
    report = contracts.build_feature_contracts(config, ["%-laguerre"])
    assert report["status"] == "BLOCKED"


@pytest.mark.parametrize("cuts", [[], [0], [-1], [99999], [True], [1.5]])
def test_invalid_cut_points_fail_explicitly(contracts, candles, cuts):
    assert (
        contracts.audit_causality(candles, ExperimentConfig(), cut_points=cuts)["status"] == "FAIL"
    )


def test_faulty_builder_schema_or_infinite_values_fails(contracts, candles):
    for builder in [
        lambda frame, periods, enabled_features: build_features(
            frame, periods, enabled_features
        ).iloc[:-1],
        lambda frame, periods, enabled_features: build_features(
            frame, periods, enabled_features
        ).assign(**{"%-return": np.inf}),
    ]:
        assert (
            contracts.audit_causality(candles, ExperimentConfig(), feature_builder=builder)[
                "status"
            ]
            == "FAIL"
        )
