"""Hand-calculated metrics and adversarial identity/comparability checks."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from quant_strategy.errors import DataContractError
from quant_strategy.research.evaluation import (
    METRIC_DEFINITION,
    compare_development_predictions,
    evaluate_predictions,
)


def _fixture():
    ids = ["a", "b", "c", "d"]
    metadata = pd.DataFrame(
        {
            "sample_id": ids,
            "pair": ["BTC", "ETH", "BTC", "ETH"],
            "fold_id": ["0", "0", "1", "1"],
            "target": [0.0, 1.0, -1.0, 2.0],
            "available_at": pd.date_range("2020-01-01", periods=4, freq="4h", tz="UTC"),
            "label_end_time": pd.date_range("2020-01-01 12:00", periods=4, freq="4h", tz="UTC"),
        }
    ).set_index("sample_id", drop=False)
    prediction = metadata[["sample_id", "pair", "fold_id", "target"]].copy()
    prediction["prediction"] = [0.0, 2.0, 1.0, 0.0]
    prediction["model"] = "fixture"
    prediction["do_predict"] = [1, 1, 0, 1]
    contract = {
        "data_sha256": "a" * 64,
        "label": {"mode": "volnorm", "horizon_candles": 3},
        "feature_schema_by_pair": {"BTC": ["%-a"], "ETH": ["%-a"]},
        "folds_sha256": "b" * 64,
        "prediction_sample_ids": ids,
        "metric_definition": METRIC_DEFINITION,
        "environment": {"fixture": "hand_calculation"},
        "scope": "development",
        "cost_assumptions": {"prediction": "costs_not_applied"},
    }
    return prediction, metadata, contract


def test_hand_calculated_metrics_and_zero_direction_are_reported_per_pair_fold():
    prediction, metadata, contract = _fixture()
    result = evaluate_predictions(prediction, metadata, contract)
    metrics = result["prediction_metrics"]["fixture"]
    assert metrics["pooled"]["mae"] == 1.25
    assert metrics["pooled"]["rmse"] == 1.5
    assert metrics["pooled"]["direction_accuracy"] == 0.5
    assert metrics["pooled"]["native_do_predict_zero"] == 1
    assert len(metrics["groups"]) == 8
    assert result["excluded_samples"] == []
    assert result["model_ranking"] == "not_performed"
    assert result["formal_oos_result"] is False


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_invalid_prediction_or_truth_never_disappears_from_metrics(value):
    prediction, metadata, contract = _fixture()
    prediction.loc["a", "prediction"] = value
    with pytest.raises(DataContractError, match="Nonfinite"):
        evaluate_predictions(prediction, metadata, contract)
    prediction, metadata, contract = _fixture()
    metadata.loc["a", "target"] = value
    with pytest.raises(DataContractError, match="finite"):
        evaluate_predictions(prediction, metadata, contract)


@pytest.mark.parametrize(
    "failure", ["missing", "extra", "duplicate", "truth", "pair", "fold", "index"]
)
def test_identity_truth_and_coverage_injections_are_rejected(failure):
    prediction, metadata, contract = _fixture()
    if failure == "missing":
        prediction = prediction.iloc[1:]
    elif failure == "extra":
        extra = prediction.iloc[:1].copy().rename(index={"a": "extra"})
        extra["sample_id"] = "extra"
        prediction = pd.concat([prediction, extra])
    elif failure == "duplicate":
        prediction = pd.concat([prediction, prediction.iloc[:1]])
    elif failure == "truth":
        prediction.loc["a", "target"] = 999
    elif failure == "pair":
        prediction.loc["a", "pair"] = "ETH"
    elif failure == "fold":
        prediction.loc["a", "fold_id"] = "999"
    else:
        prediction.index = prediction.index[::-1]
    with pytest.raises(DataContractError):
        evaluate_predictions(prediction, metadata, contract)


def test_constant_baseline_has_explicit_undefined_correlation():
    prediction, metadata, contract = _fixture()
    prediction["prediction"] = 0.0
    result = evaluate_predictions(prediction, metadata, contract)
    pooled = result["prediction_metrics"]["fixture"]["pooled"]
    assert pooled["pearson_ic"] is None
    assert pooled["spearman_ic"] is None
    assert pooled["correlation_undefined_reason"] == "constant_prediction"


def test_single_sample_correlation_is_undefined_and_not_reported_as_zero():
    prediction, metadata, contract = _fixture()
    prediction = prediction.iloc[:1]
    metadata = metadata.iloc[:1]
    contract["prediction_sample_ids"] = ["a"]
    result = evaluate_predictions(prediction, metadata, contract)
    pooled = result["prediction_metrics"]["fixture"]["pooled"]
    assert pooled["n"] == 1
    assert pooled["pearson_ic"] is None
    assert pooled["correlation_undefined_reason"] == "fewer_than_two_samples"


@pytest.mark.parametrize(
    "field",
    [
        "data_sha256",
        "label",
        "feature_schema_by_pair",
        "folds_sha256",
        "environment",
        "cost_assumptions",
    ],
)
def test_incomparable_experiments_cannot_be_silently_ranked(field):
    from quant_strategy.infrastructure.experiment_store import canonical_hash

    prediction, metadata, contract = _fixture()
    left = evaluate_predictions(prediction, metadata, contract)
    right = deepcopy(left)
    old = right["comparison_contract"][field]
    right["comparison_contract"][field] = (
        "c" * 64 if isinstance(old, str) else {**old, "changed": True}
    )
    right["comparison_contract_sha256"] = canonical_hash(right["comparison_contract"])
    with pytest.raises(DataContractError, match="Incomparable"):
        compare_development_predictions(left, right)
    assert compare_development_predictions(left, left)["model_ranking"] == "not_performed"


def test_raw_and_volnorm_errors_are_not_directly_comparable():
    from quant_strategy.infrastructure.experiment_store import canonical_hash

    prediction, metadata, contract = _fixture()
    left = evaluate_predictions(prediction, metadata, contract)
    right = deepcopy(left)
    right["comparison_contract"]["label"]["mode"] = "raw"
    right["comparison_contract_sha256"] = canonical_hash(right["comparison_contract"])
    with pytest.raises(DataContractError, match="Incomparable"):
        compare_development_predictions(left, right)


def test_missing_comparison_contract_and_formal_scope_are_rejected():
    prediction, metadata, contract = _fixture()
    with pytest.raises(DataContractError, match="Incomplete"):
        evaluate_predictions(prediction, metadata, {})
    contract["scope"] = "formal"
    with pytest.raises(DataContractError, match="development"):
        evaluate_predictions(prediction, metadata, contract)
