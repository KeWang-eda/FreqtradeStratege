"""Identity checked prediction evaluation; development results never rank models."""

from copy import deepcopy

import numpy as np
import pandas as pd

from quant_strategy.errors import DataContractError
from quant_strategy.infrastructure.experiment_store import canonical_hash
from quant_strategy.market_data.contracts import frame_fingerprint
from quant_strategy.validation.metrics import prediction_metrics

METRIC_DEFINITION = {
    "version": "controlled-prediction-v1",
    "mae": "mean(abs(target-prediction))",
    "rmse": "sqrt(mean((target-prediction)**2))",
    "direction_accuracy": "mean(sign(target)==sign(prediction)); sign(0)=0",
    "pearson_ic": "Pearson correlation; undefined for n<2 or constant inputs",
    "spearman_ic": "Pearson correlation of average ranks; undefined as above",
    "invalid_values": "reject entire evaluation; no implicit filtering",
    "native_do_predict": "record flags; do not remove predictions from evaluation",
    "aggregation": "pooled, per-fold, per-pair, and per-fold-per-pair; no winner",
}

BASELINE_DEFINITION = {
    "version": "controlled-baselines-v1",
    "mean_train": "unweighted mean of the same retained inner-training targets",
    "zero": "constant zero in the frozen label's units",
    "selection": "predeclared diagnostic baselines; no automatic ranking",
}

COMPARISON_FIELDS = (
    "data_sha256",
    "label",
    "feature_schema_by_pair",
    "folds_sha256",
    "prediction_sample_ids",
    "metric_definition",
    "environment",
    "scope",
    "cost_assumptions",
)


def _indexed(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    """Require explicit, nonempty unique identities without resetting any index."""
    result = frame.copy()
    if "sample_id" in result:
        if result["sample_id"].isna().any() or not result["sample_id"].is_unique:
            raise DataContractError(f"{name} has missing or duplicate sample IDs")
        # A RangeIndex is an ordinary export format. Named identity indices must agree.
        if result.index.name == "sample_id" and not result.index.equals(
            pd.Index(result.sample_id, name="sample_id")
        ):
            raise DataContractError(f"{name} sample ID column/index alignment failed")
        result = result.set_index("sample_id", drop=False)
    elif result.index.name == "sample_id":
        result["sample_id"] = result.index
    else:
        raise DataContractError(f"{name} needs a sample_id column or named index")
    if (
        result.empty
        or not result.index.is_unique
        or any(not isinstance(value, str) or not value for value in result.index)
    ):
        raise DataContractError(f"{name} requires nonempty unique string sample IDs")
    return result


def validate_comparison_contract(contract: dict, expected_ids: list[str]) -> None:
    """Fail before metrics when task identity is absent or cannot be compared."""
    if not isinstance(contract, dict) or any(key not in contract for key in COMPARISON_FIELDS):
        raise DataContractError("Incomplete prediction comparison contract")
    if contract["scope"] != "development":
        raise DataContractError("Prediction preparation only permits development scope")
    if contract["metric_definition"] != METRIC_DEFINITION:
        raise DataContractError("Prediction metric definition differs from the frozen contract")
    if contract["prediction_sample_ids"] != expected_ids:
        raise DataContractError("Prediction sample IDs differ from the frozen contract")
    if (
        not isinstance(contract["label"], dict)
        or contract["label"].get("mode") not in {"raw", "volnorm"}
        or not contract["feature_schema_by_pair"]
        or not contract["environment"]
    ):
        raise DataContractError("Missing label, feature schema or software environment contract")
    for key in ("data_sha256", "folds_sha256"):
        value = contract[key]
        if not isinstance(value, str) or len(value) != 64:
            raise DataContractError(f"Invalid comparison fingerprint: {key}")


def _metrics(frame: pd.DataFrame) -> dict:
    metrics = prediction_metrics(frame.target, frame.prediction)
    reason = None
    if len(frame) < 2:
        reason = "fewer_than_two_samples"
    elif frame.target.nunique() < 2:
        reason = "constant_target"
    elif frame.prediction.nunique() < 2:
        reason = "constant_prediction"
    metrics["correlation_undefined_reason"] = reason
    metrics["native_do_predict_zero"] = (
        int(frame.do_predict.eq(0).sum()) if "do_predict" in frame else None
    )
    return metrics


def evaluate_predictions(
    predictions: pd.DataFrame, expected_metadata: pd.DataFrame, comparison_contract: dict
) -> dict:
    """Score complete per-model predictions against independent expected truths.

    ``expected_metadata`` includes target/fold_id in addition to sample identity,
    pair and observation/label times. It must be assembled from the frozen input
    table and split plan, rather than copied from a model's prediction export.
    """
    expected = _indexed(expected_metadata, "Expected metadata")
    required = {"pair", "fold_id", "target", "available_at", "label_end_time"}
    if not required <= set(expected):
        raise DataContractError("Expected metadata lacks truth, fold or time information")
    validate_comparison_contract(comparison_contract, expected.index.tolist())
    if set(expected.pair) - set(comparison_contract["feature_schema_by_pair"]):
        raise DataContractError("Expected pair has no frozen feature schema")
    for column in ("available_at", "label_end_time"):
        if (
            not isinstance(expected[column].dtype, pd.DatetimeTZDtype)
            or expected[column].isna().any()
        ):
            raise DataContractError("Prediction metadata needs timezone-aware finite timestamps")
    if (expected.label_end_time < expected.available_at).any():
        raise DataContractError("Prediction label ends before feature availability")
    if not np.isfinite(expected.target.to_numpy(dtype=float)).all():
        raise DataContractError("Expected targets must be finite")
    if predictions.empty or not {"model", "pair", "fold_id", "target", "prediction"} <= set(
        predictions
    ):
        raise DataContractError("Predictions lack model, pair, fold, truth or predicted values")
    if predictions.model.isna().any() or predictions.pair.isna().any():
        raise DataContractError("Predictions have missing model or pair identities")
    models = {}
    for name, raw in predictions.groupby("model", sort=True):
        if not isinstance(name, str) or not name:
            raise DataContractError("Prediction model names must be nonempty strings")
        frame = _indexed(raw, f"Predictions for {name}")
        if set(frame.index) != set(expected.index):
            raise DataContractError("Prediction sample coverage is incomplete or contains extras")
        frame = frame.loc[expected.index]
        for column in ("pair", "fold_id", "target"):
            if not np.array_equal(frame[column].to_numpy(), expected[column].to_numpy()):
                raise DataContractError(f"Prediction {column} disagrees with independent inputs")
        if not np.isfinite(frame[["target", "prediction"]].to_numpy(dtype=float)).all():
            raise DataContractError("Nonfinite prediction; no sample can be silently dropped")
        if "do_predict" in frame and not frame.do_predict.isin([0, 1]).all():
            raise DataContractError("Invalid native do_predict flags")
        groups = []
        for keys in (("fold_id",), ("pair",), ("fold_id", "pair")):
            for identity, subset in frame.groupby(list(keys), sort=True):
                identity = identity if isinstance(identity, tuple) else (identity,)
                groups.append({"group": dict(zip(keys, identity, strict=True)), **_metrics(subset)})
        models[name] = {"pooled": _metrics(frame), "groups": groups}
    return {
        "schema_version": 1,
        "scope": "development",
        "formal_oos_result": False,
        "status": "PASS",
        "comparison_contract": deepcopy(comparison_contract),
        "comparison_contract_sha256": canonical_hash(comparison_contract),
        "expected_metadata_sha256": frame_fingerprint(expected.reset_index(drop=True)),
        "prediction_metrics": models,
        "excluded_samples": [],
        "model_ranking": "not_performed",
        "trading_evaluation": "not_performed; prediction quality is not trading value",
    }


def compare_development_predictions(left: dict, right: dict) -> dict:
    """Check comparability and expose paired diagnostics, never choose a winner."""
    for result in (left, right):
        if result.get("status") != "PASS" or result.get("formal_oos_result") is not False:
            raise DataContractError("Only verified development prediction reports are comparable")
        contract = result.get("comparison_contract", {})
        validate_comparison_contract(contract, contract.get("prediction_sample_ids", []))
        if result.get("comparison_contract_sha256") != canonical_hash(contract):
            raise DataContractError("Comparison contract fingerprint is invalid")
    if left["comparison_contract"] != right["comparison_contract"]:
        raise DataContractError("Incomparable data, label, features, folds, costs or environment")
    if left.get("expected_metadata_sha256") != right.get("expected_metadata_sha256"):
        raise DataContractError("Prediction truths or sample metadata differ")
    return {
        "scope": "development",
        "comparable": True,
        "model_ranking": "not_performed",
        "left": left["prediction_metrics"],
        "right": right["prediction_metrics"],
    }
