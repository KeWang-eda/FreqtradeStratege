"""Actual native pipelines/XGBoost using only an early non-final historical prefix."""

import json
import shutil
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from quant_strategy.config import ValidationConfig
from quant_strategy.errors import DataContractError
from quant_strategy.infrastructure.experiment_store import (
    canonical_hash,
    environment_versions,
    file_hash,
)
from quant_strategy.research.evaluation import METRIC_DEFINITION
from quant_strategy.research.fold_training import run_development_folds, verify_development_folds
from quant_strategy.research.splits import build_split_plan


@pytest.fixture(scope="module")
def early_native_inputs(native_prefix_cache):
    prepared = native_prefix_cache.snapshot()
    config, pairs = prepared["config"], prepared["pairs"]
    tables, rows, schemas = {}, [], {}
    for pair in pairs:
        expanded = prepared["expanded"][pair]
        features = [column for column in expanded if column.startswith("%")]
        usable = expanded.loc[expanded[[*features, "&-s_return"]].notna().all(axis=1)].copy()
        ids = [canonical_hash({"pair": pair, "date": date.isoformat()}) for date in usable.date]
        table = usable[["date", *features, "&-s_return"]].rename(columns={"&-s_return": "target"})
        table.index = pd.Index(ids, name="sample_id")
        tables[pair] = table
        schemas[pair] = features
        rows.append(
            pd.DataFrame(
                {
                    "sample_id": ids,
                    "pair": pair,
                    "candle_timestamp": usable.date.to_numpy(),
                    "available_at": (usable.date + pd.Timedelta(hours=4)).to_numpy(),
                    "label_start_time": (usable.date + pd.Timedelta(hours=4)).to_numpy(),
                    "label_end_time": (usable.date + pd.Timedelta(hours=16)).to_numpy(),
                    "data_version": canonical_hash(
                        {"fixture": "early-real-600-candles", "pair": pair}
                    ),
                }
            )
        )
    metadata = pd.concat(rows, ignore_index=True).sort_values(["available_at", "pair"])
    metadata = metadata.set_index("sample_id", drop=False)
    validation = asdict(ValidationConfig(method="fixed_holdout", n_splits=1))
    plan = build_split_plan(metadata, validation)
    contract = {
        "scope": "development",
        "label": {
            "mode": "volnorm",
            "horizon_candles": 3,
            "timeframe": "4h",
            "volatility_period": 14,
        },
        "feature_schema_by_pair": schemas,
        "development_fixture": "first 600 shared real candles, not a production 365-day window or formal OOS",
        "prepared_prefix_identity_sha256": prepared["provenance"]["identity_sha256"],
    }
    contract["comparison_contract"] = {
        "data_sha256": canonical_hash(
            {pair: table.date.astype(str).tolist() for pair, table in tables.items()}
        ),
        "label": contract["label"],
        "feature_schema_by_pair": schemas,
        "folds_sha256": canonical_hash(plan),
        "prediction_sample_ids": [
            identity for fold in plan["folds"] for identity in fold["test_ids"]
        ],
        "metric_definition": METRIC_DEFINITION,
        "environment": environment_versions(),
        "scope": "development",
        "cost_assumptions": {"prediction": "no_costs_applied", "trading": "not_evaluated"},
    }
    return tables, metadata, plan, contract, config


@pytest.fixture(scope="module")
def completed_native_run(tmp_path_factory, early_native_inputs):
    tables, metadata, plan, contract, config = early_native_inputs
    output = tmp_path_factory.mktemp("completed-native-folds") / "development"
    manifest = run_development_folds(tables, metadata, plan, contract, config, output)
    return output, manifest


def test_real_three_pair_fold_uses_native_training_and_never_final_holdout(
    early_native_inputs, completed_native_run
):
    tables, metadata, plan, contract, config = early_native_inputs
    original = json.loads(Path("config.json").read_text())
    output, manifest = completed_native_run
    assert manifest["status"] == "PASS"
    assert config == original
    assert manifest["formal_oos_result"] is False
    assert manifest["holdout_evaluated"] is False
    assert len(manifest["folds"]) == 3
    predictions = pd.read_parquet(output / "predictions.parquet")
    metrics = json.loads((output / "prediction_metrics.json").read_text())
    assert set(predictions.model) == {"XGBoostRegressorES", "mean_train", "zero"}
    assert metrics["model_ranking"] == "not_performed"
    for number, summary in enumerate(manifest["folds"]):
        directory = output / "fold-0" / f"pair-{number}"
        fit_ids = summary["preprocessor_fit_ids"]
        validation_ids = summary["inner_validation_ids"]
        assert len(summary["inner_purged_ids"]) == 3
        assert set(fit_ids).isdisjoint(validation_ids)
        assert set(fit_ids).isdisjoint(summary["outer_test_ids"])
        assert (
            metadata.loc[fit_ids, "label_end_time"]
            < pd.Timestamp(summary["inner_validation_start"])
        ).all()
        assert pd.Timestamp(summary["training_information_end"]) < pd.Timestamp(
            summary["outer_test_start"]
        )
        assert summary["xgboost_parameters"] == config["freqai"]["model_training_parameters"]
        pipeline = joblib.load(directory / "models" / "feature_pipeline.joblib")
        assert pipeline.fit_indices.tolist() == fit_ids
        train = tables[summary["pair"]].loc[fit_ids]
        mask = pipeline["const"].mask
        scaler = pipeline["scaler"]._skl
        np.testing.assert_array_equal(
            scaler.data_min_, train[summary["feature_schema"]].to_numpy()[:, mask].min(axis=0)
        )
        assert summary["baseline_mean_train"] == float(train.target.mean())
    for relative, digest in manifest["artifacts"].items():
        assert file_hash(output / relative) == digest
    independent = verify_development_folds(output, tables, metadata, plan, contract, config)
    assert independent["status"] == "PASS"
    assert len(independent["checks"]) == 3
    with pytest.raises(FileExistsError):
        run_development_folds(tables, metadata, plan, contract, config, output)


@pytest.mark.parametrize(
    "failure",
    [
        "fit_ids",
        "purge_ids",
        "validation_boundary",
        "weights",
        "predictions",
        "scaler",
        "information_end",
    ],
)
def test_independent_fold_verification_rejects_faults_even_after_rehashing(
    tmp_path, early_native_inputs, completed_native_run, failure
):
    original, _ = completed_native_run
    output = tmp_path / "mutated"
    shutil.copytree(original, output)
    directory = output / "fold-0" / "pair-0"
    summary_path = directory / "training.json"
    summary = json.loads(summary_path.read_text())
    if failure == "fit_ids":
        summary["preprocessor_fit_ids"] = summary["preprocessor_fit_ids"][1:]
    elif failure == "purge_ids":
        summary["inner_purged_ids"] = summary["inner_purged_ids"][1:]
    elif failure == "validation_boundary":
        summary["inner_validation_start"] = (
            pd.Timestamp(summary["inner_validation_start"]) + pd.Timedelta(hours=4)
        ).isoformat()
    elif failure == "information_end":
        summary["training_information_end"] = summary["inner_validation_start"]
    elif failure == "weights":
        path = directory / "models" / "train_fit.parquet"
        frame = pd.read_parquet(path)
        frame.iloc[0, frame.columns.get_loc("sample_weight")] *= 2
        frame.to_parquet(path)
    elif failure == "predictions":
        path = output / "predictions.parquet"
        frame = pd.read_parquet(path)
        frame.loc[0, "prediction"] += 0.125
        frame.to_parquet(path, index=False)
    else:
        path = directory / "models" / "feature_pipeline.joblib"
        pipeline = joblib.load(path)
        pipeline["scaler"]._skl.data_min_[0] -= 10
        joblib.dump(pipeline, path)
    summary_path.write_text(json.dumps(summary))
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["folds"][0] = summary
    manifest["artifacts"] = {
        path.relative_to(output).as_posix(): file_hash(path)
        for path in output.rglob("*")
        if path.is_file() and path != manifest_path
    }
    manifest_path.write_text(json.dumps(manifest))
    tables, metadata, plan, contract, config = early_native_inputs
    with pytest.raises(DataContractError):
        verify_development_folds(output, tables, metadata, plan, contract, config)


@pytest.mark.parametrize(
    "failure", ["missing", "duplicate", "holdout", "denied", "scope", "plan", "future", "order"]
)
def test_independent_verifier_rejects_access_audit_tampering_after_rehashing(
    tmp_path, early_native_inputs, completed_native_run, failure
):
    original, _ = completed_native_run
    output = tmp_path / "access-audit-mutated"
    shutil.copytree(original, output)
    path = output / "data_access.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    if failure == "missing":
        del events[1]
    elif failure == "duplicate":
        events.insert(2, events[1].copy())
    elif failure == "holdout":
        events[1]["sample_ids"] = [early_native_inputs[2]["holdout"]["sample_ids"][0]]
    elif failure == "denied":
        events[1]["status"] = "denied"
    elif failure == "scope":
        events[1]["scope"] = "formal"
    elif failure == "plan":
        events[1]["plan_sha256"] = "9" * 64
    elif failure == "future":
        events[1]["created_at"] = "2999-01-01T00:00:00+00:00"
    else:
        events[1], events[2] = events[2], events[1]
    # Reassigning event IDs makes a plausible contiguous log; the verifier
    # must still reconstruct purposes and identities instead of trusting IDs.
    for number, event in enumerate(events):
        event["event_id"] = number
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"][path.relative_to(output).as_posix()] = file_hash(path)
    manifest_path.write_text(json.dumps(manifest))
    tables, metadata, plan, contract, config = early_native_inputs
    with pytest.raises(DataContractError, match="[Aa]ccess"):
        verify_development_folds(output, tables, metadata, plan, contract, config)


@pytest.mark.parametrize(
    "failure",
    [
        "formal",
        "label",
        "volatility_period",
        "model",
        "environment",
        "plan",
        "missing_sample",
        "schema",
    ],
)
def test_fold_execution_refuses_contract_and_identity_faults(
    tmp_path, early_native_inputs, failure
):
    tables, metadata, plan, contract, config = deepcopy(early_native_inputs)
    if failure == "formal":
        contract["scope"] = "formal"
    elif failure == "label":
        contract["label"]["mode"] = "raw"
    elif failure == "volatility_period":
        contract["label"]["volatility_period"] = 99
    elif failure == "model":
        config["freqaimodel"] = "MomentumRidgeRegressor"
    elif failure == "environment":
        contract["comparison_contract"]["environment"] = {"python": "not_current"}
    elif failure == "plan":
        plan["folds"][0]["train_ids"].append(plan["folds"][0]["test_ids"][0])
    elif failure == "missing_sample":
        first = next(iter(tables))
        tables[first] = tables[first].drop(plan["folds"][0]["train_ids"][0], errors="ignore")
        # Ensure the removed ID belongs to this table, without assuming pair sort.
        tables[first] = tables[first].iloc[1:]
    else:
        first = next(iter(tables))
        tables[first] = tables[first].drop(columns=contract["feature_schema_by_pair"][first][0])
    with pytest.raises(DataContractError):
        run_development_folds(tables, metadata, plan, contract, config, tmp_path / "invalid")


def test_failed_native_model_training_retains_a_failed_run(
    tmp_path, early_native_inputs, monkeypatch
):
    from freqtrade.resolvers.freqaimodel_resolver import FreqaiModelResolver

    # Fault injection only replaces the failing model boundary. The positive
    # test above executes actual native training with production parameters.
    def fail(*args, **kwargs):
        raise RuntimeError("intentional isolated training failure")

    original_load = FreqaiModelResolver.load_freqaimodel

    def load_failing(config):
        model = original_load(config)
        model.fit = fail
        return model

    monkeypatch.setattr(FreqaiModelResolver, "load_freqaimodel", staticmethod(load_failing))
    tables, metadata, plan, contract, config = early_native_inputs
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="intentional"):
        run_development_folds(tables, metadata, plan, contract, config, output)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "FAIL"
    assert manifest["error"]["type"] == "RuntimeError"
    assert (output / "fold-0" / "pair-0" / "models" / "train_fit.parquet").is_file()


def test_nonfinal_fixture_holdout_changes_cannot_change_development_models_or_predictions(
    tmp_path, early_native_inputs, completed_native_run
):
    from pandas.testing import assert_frame_equal

    # This is an explicitly non-final early-2020 fixture reservation, not the
    # project's real final holdout. No metric is computed on this reservation.
    tables, metadata, plan, contract, config = deepcopy(early_native_inputs)
    reserved = set(plan["holdout"]["sample_ids"])
    for table in tables.values():
        identities = table.index[table.index.isin(reserved)]
        table.loc[identities, "target"] = 1e100
        for feature in table.columns[table.columns.str.startswith("%")]:
            table.loc[identities, feature] = -1e100
    original, _ = completed_native_run
    repeated = tmp_path / "repeated-with-mutated-fixture-reservation"
    run_development_folds(tables, metadata, plan, contract, config, repeated)
    assert_frame_equal(
        pd.read_parquet(original / "predictions.parquet"),
        pd.read_parquet(repeated / "predictions.parquet"),
        check_exact=True,
    )
    first = json.loads((original / "prediction_metrics.json").read_text())
    second = json.loads((repeated / "prediction_metrics.json").read_text())
    assert first == second
    assert (
        verify_development_folds(repeated, tables, metadata, plan, contract, config)["violations"]
        == 0
    )
