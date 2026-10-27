"""Development-only native XGBoost folds with a separate internal validation set.

The external test fold is never passed to native fit/preprocessor fit/early stop.
This adapter reuses the production model's pipelines and fit hook, leaving its
production contiguous-candle ``train`` lifecycle and defaults unchanged.
"""

import importlib.metadata
import inspect
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import numpy as np
import pandas as pd

from quant.errors import DataContractError
from quant.infrastructure.experiment_store import (
    canonical_hash,
    environment_versions,
    file_hash,
    git_state,
    write_json,
)
from quant.labels import set_regression_target
from quant.market_data.contracts import frame_fingerprint
from quant.market_data.time_index import timeframe_delta
from quant.research.evaluation import (
    BASELINE_DEFINITION,
    evaluate_predictions,
    validate_comparison_contract,
)
from quant.training.native_isolation import validate_native_config
from quant.validation.admission import current_source_hashes


def _runtime_environment_matches(expected: dict) -> bool:
    current = environment_versions()
    if any(expected.get(key) != value for key, value in current.items()):
        return False
    for key in expected.keys() - current.keys():
        try:
            if importlib.metadata.version(key) != expected[key]:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return True


def _verify_access_audit(path: Path, expected_events: list[dict], manifest: dict) -> dict:
    """Compare the actual access log with independently reconstructed selections."""

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DataContractError("Access audit contains duplicate JSON keys")
            result[key] = value
        return result

    def timestamp(value):
        try:
            result = datetime.fromisoformat(value)
        except (ValueError, TypeError) as error:
            raise DataContractError("Access audit has an invalid timestamp") from error
        if result.tzinfo is None or result.utcoffset() != timedelta(0):
            raise DataContractError("Access audit timestamps must be UTC-aware")
        return result

    try:
        observed_events = [
            json.loads(line, object_pairs_hook=unique_keys)
            for line in path.read_text().splitlines()
        ]
    except (OSError, ValueError) as error:
        raise DataContractError("Access audit is missing or damaged") from error
    if len(observed_events) != len(expected_events):
        raise DataContractError("Access audit has missing or duplicate operations")
    now = datetime.now(UTC)
    start, finish = timestamp(manifest.get("started_at")), timestamp(manifest.get("finished_at"))
    if not start <= finish <= now:
        raise DataContractError("Access audit execution interval is invalid or in the future")
    for observed, expected in zip(observed_events, expected_events, strict=True):
        if not isinstance(observed, dict) or "created_at" not in observed:
            raise DataContractError("Access audit event is malformed")
        recorded_at = timestamp(observed["created_at"])
        if not start <= recorded_at <= finish:
            raise DataContractError("Access audit timestamp lies outside the actual run interval")
        if {key: value for key, value in observed.items() if key != "created_at"} != {
            key: value for key, value in expected.items() if key != "created_at"
        }:
            raise DataContractError(
                "Access audit differs from reconstructed purposes, identities or permissions"
            )
    return {
        "status": "PASS",
        "event_count": len(observed_events),
        "reconstructed_event_count": len(expected_events),
        "unexpected_or_denied_operations": 0,
        "holdout_value_accesses": 0,
        "timestamp_policy": "UTC-aware; inside execution interval; not in the future",
    }


def _aligned(dd: dict, split: str, expected: pd.DataFrame, *, subset: bool = False) -> None:
    X, y, weights = (dd[f"{split}_{kind}"] for kind in ("features", "labels", "weights"))
    if (
        not isinstance(X, pd.DataFrame)
        or not isinstance(y, pd.DataFrame)
        or not X.index.is_unique
        or not X.index.equals(y.index)
        or not isinstance(weights, pd.Series)
        or not X.index.equals(weights.index)
    ):
        raise DataContractError("Fold X/y/weights identity alignment failed")
    wanted = expected.index[expected.index.isin(X.index)] if subset else expected.index
    if not X.index.equals(wanted) or X.empty:
        raise DataContractError("Fold preprocessing changed or lost unapproved sample identities")
    if (
        not np.isfinite(X.to_numpy(dtype=float)).all()
        or not np.isfinite(y.to_numpy(dtype=float)).all()
    ):
        raise DataContractError("Fold preprocessing produced nonfinite values")
    if not np.array_equal(weights.to_numpy(), expected.loc[X.index, "sample_weight"].to_numpy()):
        raise DataContractError("Fold weights differ from their independently indexed source")


def _indexed_weights(dd: dict, split: str) -> None:
    weights = dd[f"{split}_weights"]
    index = dd[f"{split}_features"].index
    if isinstance(weights, pd.Series) and not weights.index.equals(index):
        raise DataContractError("Native fold weights were reordered")
    dd[f"{split}_weights"] = pd.Series(np.asarray(weights), index=index, name="sample_weight")


def _train_pair(
    table: pd.DataFrame,
    metadata: pd.DataFrame,
    fold: dict,
    pair: str,
    config: dict,
    contract: dict,
    directory: Path,
    access,
) -> tuple[pd.DataFrame, dict]:
    from freqtrade.configuration.config_validation import validate_config_schema
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
    from freqtrade.resolvers.freqaimodel_resolver import FreqaiModelResolver

    features = contract["feature_schema_by_pair"][pair]
    if [column for column in table if column.startswith("%")] != features:
        raise DataContractError("Actual native feature schema differs from the frozen contract")
    train_ids = [
        identity for identity in fold["train_ids"] if metadata.at[identity, "pair"] == pair
    ]
    test_ids = [identity for identity in fold["test_ids"] if metadata.at[identity, "pair"] == pair]
    train = access.select(table, train_ids, "train")
    test = access.select(table, test_ids, "test")
    if train.empty or test.empty:
        raise DataContractError("Every declared research pair needs train and test samples")
    for frame in (train, test):
        if not {"date", "target"} <= set(frame):
            raise DataContractError("Fold input lacks dates or target")
        if not np.isfinite(frame[[*features, "target"]].to_numpy(dtype=float)).all():
            raise DataContractError("Fold input contains invalid features/labels; quarantine first")
        if not frame.date.is_monotonic_increasing or frame.date.duplicated().any():
            raise DataContractError("Fold pair input timestamps must be unique and increasing")
        expected_time = pd.DatetimeIndex(frame.date) + timeframe_delta(config["timeframe"])
        if not expected_time.equals(pd.DatetimeIndex(metadata.loc[frame.index, "available_at"])):
            raise DataContractError("Fold candle/availability timestamps disagree")
    test_start = metadata.loc[fold["test_ids"], "available_at"].min()
    if (metadata.loc[train.index, "label_end_time"] >= test_start).any():
        raise DataContractError("Outer training label touches the external test boundary")
    directory.mkdir(parents=True, exist_ok=False)
    runtime = deepcopy(config)
    runtime["user_data_dir"] = directory / "models" / "userdir"
    runtime["user_data_dir"].mkdir(parents=True)
    runtime["freqaimodel_path"] = str(
        Path(__file__).resolve().parents[2] / "quant" / "models" / "freqai"
    )
    runtime["freqaimodel"] = "XGBoostRegressorES"
    validate_config_schema(runtime)
    model = FreqaiModelResolver.load_freqaimodel(runtime)
    model.live = False
    dk = FreqaiDataKitchen(runtime, live=True, pair=pair)
    dk.data_path = directory / "models" / "native_fit"
    dk.data_path.mkdir()
    dk.training_features_list = features.copy()
    dk.label_list = ["&-s_return"]
    targets = train[["target"]].rename(columns={"target": "&-s_return"})
    dd = dk.make_train_test_datasets(train[features], targets)
    for split in ("train", "test"):
        _indexed_weights(dd, split)
    validation_ids = dd["test_features"].index.tolist()
    if not validation_ids:
        raise DataContractError("Native early stopping requires a nonempty inner validation set")
    validation_start = metadata.loc[validation_ids, "available_at"].min()
    initial_ids = dd["train_features"].index
    purge = metadata.loc[initial_ids, "label_end_time"] >= validation_start
    purged_ids = initial_ids[purge].tolist()
    retained = initial_ids[~purge]
    if not len(retained):
        raise DataContractError("Inner label purge leaves no training samples")
    for kind in ("features", "labels", "weights"):
        dd[f"train_{kind}"] = dd[f"train_{kind}"].loc[retained].copy()
    before = {}
    for split in ("train", "test"):
        before[split] = (
            dd[f"{split}_features"].join(dd[f"{split}_labels"]).join(dd[f"{split}_weights"])
        )
        before[split].to_parquet(directory / "models" / f"{split}_before.parquet")
        _aligned(dd, split, before[split])
    access.select(metadata, retained.tolist(), "fit")
    access.select(metadata, validation_ids, "validation")
    # All learned label/feature statistics are fitted after the strict inner purge.
    dk.fit_labels()
    dk.feature_pipeline = model.define_data_pipeline(threads=dk.thread_count)
    dk.label_pipeline = model.define_label_pipeline(threads=dk.thread_count)
    dd["train_features"], dd["train_labels"], dd["train_weights"] = (
        dk.feature_pipeline.fit_transform(
            dd["train_features"], dd["train_labels"], dd["train_weights"]
        )
    )
    dd["train_labels"], _, _ = dk.label_pipeline.fit_transform(dd["train_labels"])
    dd["test_features"], dd["test_labels"], dd["test_weights"] = dk.feature_pipeline.transform(
        dd["test_features"], dd["test_labels"], dd["test_weights"]
    )
    dd["test_labels"], _, _ = dk.label_pipeline.transform(dd["test_labels"])
    for split in ("train", "test"):
        _indexed_weights(dd, split)
        _aligned(dd, split, before[split], subset=split == "test")
        dd[f"{split}_features"].join(dd[f"{split}_labels"]).join(dd[f"{split}_weights"]).to_parquet(
            directory / "models" / f"{split}_fit.parquet"
        )
    for pipeline in (dk.feature_pipeline, dk.label_pipeline):
        if not pipeline.fit_indices.equals(retained):
            raise DataContractError("Fold pipeline fit observed a purged or validation sample")
    fitted = model.fit(dd, dk)
    transformed, ready, _ = dk.feature_pipeline.transform(test[features], outlier_check=True)
    if not transformed.index.equals(test.index):
        raise DataContractError("External prediction preprocessing removed or reordered samples")
    prediction = pd.DataFrame(
        np.asarray(fitted.predict(transformed)).reshape(-1, 1),
        index=test.index,
        columns=dk.label_list,
    )
    prediction, _, _ = dk.label_pipeline.inverse_transform(prediction)
    predictions = pd.DataFrame(
        {
            "sample_id": test.index,
            "pair": pair,
            "fold_id": fold["fold_id"],
            "target": test.target.to_numpy(),
            "prediction": prediction.iloc[:, 0].to_numpy(),
            "model": "XGBoostRegressorES",
            "do_predict": np.asarray(ready, dtype=int),
        }
    )
    mean_target = float(train.loc[retained, "target"].mean())
    outputs = [predictions]
    for baseline, value in (("mean_train", mean_target), ("zero", 0.0)):
        outputs.append(predictions.assign(model=baseline, prediction=value, do_predict=1))
    joblib.dump(fitted, directory / "models" / "model.joblib")
    joblib.dump(dk.feature_pipeline, directory / "models" / "feature_pipeline.joblib")
    joblib.dump(dk.label_pipeline, directory / "models" / "label_pipeline.joblib")
    train.to_parquet(directory / "models" / "outer_train_input.parquet")
    test.to_parquet(directory / "models" / "outer_test_input.parquet")
    used_ids = retained.tolist() + dd["test_features"].index.tolist()
    information_end = metadata.loc[used_ids, "label_end_time"].max()
    if information_end >= test_start:
        raise DataContractError("Early-stopping label information reaches the outer test fold")
    assignments = metadata.loc[train.index].copy()
    assignments["assignment"] = "inner_train"
    assignments["reason"] = "legal_inner_training_sample"
    assignments.loc[validation_ids, ["assignment", "reason"]] = [
        "inner_validation",
        "early_stopping_only_no_preprocessor_fit",
    ]
    assignments.loc[purged_ids, ["assignment", "reason"]] = [
        "purged",
        "label_end_time_greater_than_or_equal_to_validation_start",
    ]
    rejected = [
        identity for identity in validation_ids if identity not in dd["test_features"].index
    ]
    assignments.loc[rejected, ["assignment", "reason"]] = [
        "validation_preprocessing_rejected",
        "native_DI_filter",
    ]
    assignments.to_parquet(directory / "sample_assignments.parquet")
    summary = {
        "scope": "development",
        "formal_oos_result": False,
        "status": "PASS",
        "fold_id": fold["fold_id"],
        "pair": pair,
        "feature_schema": features,
        "raw_outer_train_ids": train.index.tolist(),
        "outer_test_ids": test.index.tolist(),
        "preprocessor_fit_ids": retained.tolist(),
        "inner_purged_ids": purged_ids,
        "inner_validation_ids": validation_ids,
        "inner_validation_used_ids": dd["test_features"].index.tolist(),
        "inner_validation_rejected_ids": rejected,
        "inner_validation_start": validation_start.isoformat(),
        "training_information_end": information_end.isoformat(),
        "outer_test_start": test_start.isoformat(),
        "baseline_mean_train": mean_target,
        "label_statistics": {"mean": dk.data["labels_mean"], "std": dk.data["labels_std"]},
        "xgboost_parameters": deepcopy(config["freqai"]["model_training_parameters"]),
        "effective_xgboost_random_state": fitted.get_xgb_params().get("random_state"),
        "effective_booster_seed": json.loads(fitted.get_booster().save_config())["learner"][
            "generic_param"
        ]["seed"],
        "xgboost_boosted_rounds": fitted.get_booster().num_boosted_rounds(),
        "best_iteration": getattr(fitted, "best_iteration", None),
        "input_sha256": {
            "train": frame_fingerprint(train.assign(sample_id=train.index).reset_index(drop=True)),
            "test": frame_fingerprint(test.assign(sample_id=test.index).reset_index(drop=True)),
        },
    }
    write_json(directory / "training.json", summary)
    return pd.concat(outputs, ignore_index=True), summary


def run_development_folds(
    tables: dict[str, pd.DataFrame],
    metadata: pd.DataFrame,
    plan: dict,
    contract: dict,
    native_config: dict,
    output: Path,
) -> dict:
    """Run predeclared development folds; refuse formal scope and overwrite."""
    from quant.research.splits import DevelopmentAccess, verify_split_plan

    if contract.get("scope") != "development":
        raise DataContractError("Controlled native folds permit development scope only")
    validate_native_config(native_config)
    if native_config.get("freqaimodel") != "XGBoostRegressorES":
        raise DataContractError("Controlled folds support the current native XGBoost model only")
    if any(native_config.get("exchange", {}).get(key) for key in ("key", "secret", "password")):
        raise DataContractError("Controlled local development requires a credential-free config")
    label = contract.get("label", {})
    if (
        label.get("mode") != native_config.get("my_experiment", {}).get("label", "raw")
        or label.get("horizon_candles")
        != native_config["freqai"]["feature_parameters"]["label_period_candles"]
        or label.get("timeframe") != native_config["timeframe"]
        or label.get("volatility_period")
        != inspect.signature(set_regression_target).parameters["volatility_period"].default
    ):
        raise DataContractError("Research label contract differs from production configuration")
    if native_config["freqai"]["data_split_parameters"].get("test_size", 0.1) == 0:
        raise DataContractError(
            "Controlled native folds require internal early-stopping validation"
        )
    verify_split_plan(metadata, plan["validation"], plan)
    expected_label_end = metadata.available_at + (
        native_config["freqai"]["feature_parameters"]["label_period_candles"]
        * timeframe_delta(native_config["timeframe"])
    )
    if not metadata.label_end_time.eq(expected_label_end).all():
        raise DataContractError("Sample label times differ from the continuous native horizon")
    if set(tables) != set(contract.get("feature_schema_by_pair", {})):
        raise DataContractError("Research pair set differs from the frozen feature contract")
    expected_ids = [identity for fold in plan["folds"] for identity in fold["test_ids"]]
    comparison = contract.get("comparison_contract", {})
    validate_comparison_contract(comparison, expected_ids)
    if (
        comparison["label"] != label
        or comparison["feature_schema_by_pair"] != contract["feature_schema_by_pair"]
        or not _runtime_environment_matches(comparison["environment"])
        or comparison["folds_sha256"] != canonical_hash(plan)
        or contract.get("native_config_sha256", canonical_hash(native_config))
        != canonical_hash(native_config)
        or contract.get("baseline_definition", BASELINE_DEFINITION) != BASELINE_DEFINITION
    ):
        raise DataContractError("Execution and prediction comparison contracts disagree")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "scope": "development",
        "formal_oos_result": False,
        "holdout_evaluated": False,
        "status": "RUNNING",
        "started_at": datetime.now(UTC).isoformat(),
        "git": git_state(),
        "environment": environment_versions(),
        "source_files_sha256": current_source_hashes(),
        "contract_sha256": canonical_hash(contract),
        "research_contract_sha256": contract.get("contract_sha256") or canonical_hash(contract),
        "plan_sha256": canonical_hash(plan),
        "native_config_sha256": canonical_hash(native_config),
        "model_selection": "not_performed",
        "folds": [],
    }
    write_json(output / "contract.json", contract)
    write_json(output / "split_plan.json", plan)
    write_json(output / "native_config.json", native_config)
    write_json(output / "manifest.json", manifest)
    access = DevelopmentAccess(metadata, plan, output / "data_access.jsonl")
    predictions, expected = [], []
    try:
        for fold in plan["folds"]:
            for number, (pair, table) in enumerate(tables.items()):
                directory = output / f"fold-{fold['fold_id']}" / f"pair-{number}"
                result, summary = _train_pair(
                    table, metadata, fold, pair, native_config, contract, directory, access
                )
                predictions.append(result)
                manifest["folds"].append(summary)
            rows = access.select(metadata, fold["test_ids"], "metrics").copy()
            rows["target"] = [
                tables[row.pair].at[identity, "target"] for identity, row in rows.iterrows()
            ]
            rows["fold_id"] = fold["fold_id"]
            expected.append(rows)
        prediction_table = pd.concat(predictions, ignore_index=True)
        expected_table = pd.concat(expected)
        evaluation = evaluate_predictions(prediction_table, expected_table, comparison)
        prediction_table.to_parquet(output / "predictions.parquet", index=False)
        expected_table.to_parquet(output / "expected_predictions.parquet")
        write_json(output / "prediction_metrics.json", evaluation)
        manifest["status"] = "PASS"
        manifest["prediction_rows"] = len(prediction_table)
        manifest["baseline_definition"] = BASELINE_DEFINITION
    except Exception as error:
        manifest["status"] = "FAIL"
        manifest["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        manifest["finished_at"] = datetime.now(UTC).isoformat()
        manifest["artifacts"] = {
            path.relative_to(output).as_posix(): file_hash(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and path != output / "manifest.json"
        }
        write_json(output / "manifest.json", manifest)
    return manifest


def verify_development_folds(
    output: Path,
    tables: dict[str, pd.DataFrame],
    metadata: pd.DataFrame,
    plan: dict,
    contract: dict,
    native_config: dict,
) -> dict:
    """Rebuild identities/pipelines/predictions from inputs, not status declarations.

    A fresh native model object supplies the current production preprocessing
    definitions; no model is trained, no metric uses reserved holdout values.
    Byte hashes protect integrity, while independent reconstruction catches a
    changed assignment, dropped sample or falsified report even after rehashing.
    """
    from freqtrade.configuration.config_validation import validate_config_schema
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
    from freqtrade.resolvers.freqaimodel_resolver import FreqaiModelResolver
    from pandas.testing import assert_frame_equal

    from quant.research.splits import DevelopmentAccess, verify_split_plan

    output = Path(output)
    verify_split_plan(metadata, plan["validation"], plan)
    expected_label_end = metadata.available_at + (
        native_config["freqai"]["feature_parameters"]["label_period_candles"]
        * timeframe_delta(native_config["timeframe"])
    )
    if not metadata.label_end_time.eq(expected_label_end).all():
        raise DataContractError("Independent sample horizon differs from native label semantics")
    manifest = json.loads((output / "manifest.json").read_text())
    mismatches = []
    if manifest.get("scope") != "development":
        mismatches.append("scope")
    if manifest.get("formal_oos_result") is not False:
        mismatches.append("formal_oos_result")
    if manifest.get("holdout_evaluated") is not False:
        mismatches.append("holdout_evaluated")
    if manifest.get("status") != "PASS":
        mismatches.append("status")
    if manifest.get("contract_sha256") != canonical_hash(contract):
        mismatches.append("contract_sha256")
    if manifest.get("plan_sha256") != canonical_hash(plan):
        mismatches.append("plan_sha256")
    if manifest.get("native_config_sha256") != canonical_hash(native_config):
        mismatches.append("native_config_sha256")
    if manifest.get("environment") != environment_versions():
        mismatches.append("environment")
    if manifest.get("source_files_sha256") != current_source_hashes():
        mismatches.append("source_files_sha256")
    if mismatches:
        raise DataContractError(
            "Development run contract/scope/environment evidence disagrees: " + ",".join(mismatches)
        )
    actual_files = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file() and path != output / "manifest.json"
    }
    if actual_files != set(manifest.get("artifacts", {})):
        raise DataContractError("Development artifact inventory is incomplete or has extras")
    for relative, digest in manifest["artifacts"].items():
        if file_hash(output / relative) != digest:
            raise DataContractError("Development artifact hash mismatch")
    for filename, expected_value in (
        ("contract.json", contract),
        ("split_plan.json", plan),
        ("native_config.json", native_config),
    ):
        actual = json.loads((output / filename).read_text())
        if canonical_hash(actual) != canonical_hash(expected_value):
            raise DataContractError("Persisted development input contract differs")
    access = DevelopmentAccess(metadata, plan)
    rebuilt, expected_rows, checks = [], [], []
    with TemporaryDirectory(prefix="native-fold-verification-") as temporary:
        runtime = deepcopy(native_config)
        runtime["user_data_dir"] = Path(temporary)
        runtime["freqaimodel_path"] = str(
            Path(__file__).resolve().parents[2] / "quant" / "models" / "freqai"
        )
        runtime["freqaimodel"] = "XGBoostRegressorES"
        validate_config_schema(runtime)
        definition = FreqaiModelResolver.load_freqaimodel(runtime)
        for fold in plan["folds"]:
            for number, (pair, table) in enumerate(tables.items()):
                directory = output / f"fold-{fold['fold_id']}" / f"pair-{number}"
                summary = json.loads((directory / "training.json").read_text())
                matching = [
                    item
                    for item in manifest["folds"]
                    if item.get("fold_id") == fold["fold_id"] and item.get("pair") == pair
                ]
                if matching != [summary]:
                    raise DataContractError("Fold summary is missing, duplicated or inconsistent")
                features = contract["feature_schema_by_pair"][pair]
                if summary.get("feature_schema") != features:
                    raise DataContractError("Fold feature schema differs from production contract")
                ids = {
                    kind: [
                        identity
                        for identity in fold[f"{kind}_ids"]
                        if metadata.at[identity, "pair"] == pair
                    ]
                    for kind in ("train", "test")
                }
                train = access.select(table, ids["train"], "train")
                test = access.select(table, ids["test"], "test")
                try:
                    assert_frame_equal(
                        pd.read_parquet(directory / "models" / "outer_train_input.parquet"), train
                    )
                    assert_frame_equal(
                        pd.read_parquet(directory / "models" / "outer_test_input.parquet"), test
                    )
                except AssertionError as error:
                    raise DataContractError(
                        "Saved fold input differs from the actual dataset"
                    ) from error
                dk = FreqaiDataKitchen(runtime, live=True, pair=pair)
                dd = dk.make_train_test_datasets(
                    train[features], train[["target"]].rename(columns={"target": "&-s_return"})
                )
                for split in ("train", "test"):
                    _indexed_weights(dd, split)
                initial_train = dd["train_features"].index
                valid_ids = dd["test_features"].index.tolist()
                boundary = metadata.loc[valid_ids, "available_at"].min()
                overlap = metadata.loc[initial_train, "label_end_time"] >= boundary
                retained, purged = initial_train[~overlap], initial_train[overlap]
                # Reconstruct the actual runner's access sequence using the
                # independently derived split, rather than trusting its log.
                access.select(metadata, retained.tolist(), "fit")
                access.select(metadata, valid_ids, "validation")
                expected_summary = {
                    "raw_outer_train_ids": train.index.tolist(),
                    "outer_test_ids": test.index.tolist(),
                    "preprocessor_fit_ids": retained.tolist(),
                    "inner_purged_ids": purged.tolist(),
                    "inner_validation_ids": valid_ids,
                    "inner_validation_start": boundary.isoformat(),
                    "xgboost_parameters": native_config["freqai"]["model_training_parameters"],
                    "outer_test_start": metadata.loc[fold["test_ids"], "available_at"]
                    .min()
                    .isoformat(),
                    "input_sha256": {
                        "train": frame_fingerprint(
                            train.assign(sample_id=train.index).reset_index(drop=True)
                        ),
                        "test": frame_fingerprint(
                            test.assign(sample_id=test.index).reset_index(drop=True)
                        ),
                    },
                }
                if any(summary.get(key) != value for key, value in expected_summary.items()):
                    raise DataContractError(
                        "Fold fit/validation/purge IDs differ from independent native split"
                    )
                for kind in ("features", "labels", "weights"):
                    dd[f"train_{kind}"] = dd[f"train_{kind}"].loc[retained].copy()
                for split in ("train", "test"):
                    expected_before = (
                        dd[f"{split}_features"]
                        .join(dd[f"{split}_labels"])
                        .join(dd[f"{split}_weights"])
                    )
                    try:
                        assert_frame_equal(
                            pd.read_parquet(directory / "models" / f"{split}_before.parquet"),
                            expected_before,
                        )
                    except AssertionError as error:
                        raise DataContractError(
                            "Saved preprocessor input has wrong features/labels/weights"
                        ) from error
                feature_pipeline = definition.define_data_pipeline(threads=dk.thread_count)
                label_pipeline = definition.define_label_pipeline(threads=dk.thread_count)
                dd["train_features"], dd["train_labels"], dd["train_weights"] = (
                    feature_pipeline.fit_transform(
                        dd["train_features"], dd["train_labels"], dd["train_weights"]
                    )
                )
                dd["train_labels"], _, _ = label_pipeline.fit_transform(dd["train_labels"])
                dd["test_features"], dd["test_labels"], dd["test_weights"] = (
                    feature_pipeline.transform(
                        dd["test_features"], dd["test_labels"], dd["test_weights"]
                    )
                )
                dd["test_labels"], _, _ = label_pipeline.transform(dd["test_labels"])
                for split in ("train", "test"):
                    _indexed_weights(dd, split)
                    expected_fit = (
                        dd[f"{split}_features"]
                        .join(dd[f"{split}_labels"])
                        .join(dd[f"{split}_weights"])
                    )
                    try:
                        assert_frame_equal(
                            pd.read_parquet(directory / "models" / f"{split}_fit.parquet"),
                            expected_fit,
                            check_exact=True,
                        )
                    except AssertionError as error:
                        raise DataContractError(
                            "Saved model fit inputs differ from independently refitted pipelines"
                        ) from error
                # Inspect actual serialized preprocessors as well as recomputing their outputs.
                saved_feature = joblib.load(directory / "models" / "feature_pipeline.joblib")
                saved_label = joblib.load(directory / "models" / "label_pipeline.joblib")
                for saved, refitted in (
                    (saved_feature, feature_pipeline),
                    (saved_label, label_pipeline),
                ):
                    if not saved.fit_indices.equals(retained) or [
                        name for name, _ in saved.steps
                    ] != [name for name, _ in refitted.steps]:
                        raise DataContractError(
                            "Serialized preprocessor fitted on wrong sample identities"
                        )
                    for (name, old), (_, new) in zip(saved.steps, refitted.steps, strict=True):
                        left, right = getattr(old, "_skl", old), getattr(new, "_skl", new)
                        for attribute in (
                            "data_min_",
                            "data_max_",
                            "scale_",
                            "mean_",
                            "var_",
                            "n_samples_seen_",
                        ):
                            if hasattr(right, attribute) and not np.array_equal(
                                np.asarray(getattr(left, attribute, None)),
                                np.asarray(getattr(right, attribute)),
                            ):
                                raise DataContractError(
                                    f"Serialized {name} statistics differ from train-only refit"
                                )
                used = dd["test_features"].index.tolist()
                information_end = metadata.loc[retained.tolist() + used, "label_end_time"].max()
                outer_start = metadata.loc[fold["test_ids"], "available_at"].min()
                if (
                    summary.get("inner_validation_used_ids") != used
                    or summary.get("training_information_end") != information_end.isoformat()
                    or information_end >= outer_start
                    or (metadata.loc[retained, "label_end_time"] >= boundary).any()
                ):
                    raise DataContractError(
                        "Early stopping or training information crosses a protected boundary"
                    )
                transformed, ready, _ = feature_pipeline.transform(
                    test[features], outlier_check=True
                )
                fitted = joblib.load(directory / "models" / "model.joblib")
                # get_xgb_params deliberately omits sklearn-wrapper parameters
                # such as n_estimators; get_params retains the complete fitted
                # estimator configuration instead of misreporting them missing.
                effective = fitted.get_params(deep=False)
                for key, value in native_config["freqai"]["model_training_parameters"].items():
                    if key != "early_stopping_rounds" and effective.get(key) != value:
                        raise DataContractError(
                            "Actual saved model hyperparameters differ from native config"
                        )
                if (
                    summary.get("effective_xgboost_random_state") != effective.get("random_state")
                    or summary.get("effective_booster_seed")
                    != json.loads(fitted.get_booster().save_config())["learner"]["generic_param"][
                        "seed"
                    ]
                ):
                    raise DataContractError("Actual saved model seed differs from recorded seed")
                prediction = pd.DataFrame(
                    np.asarray(fitted.predict(transformed)).reshape(-1, 1), columns=["&-s_return"]
                )
                prediction, _, _ = label_pipeline.inverse_transform(prediction)
                result = pd.DataFrame(
                    {
                        "sample_id": test.index,
                        "pair": pair,
                        "fold_id": fold["fold_id"],
                        "target": test.target.to_numpy(),
                        "prediction": prediction.iloc[:, 0].to_numpy(),
                        "model": "XGBoostRegressorES",
                        "do_predict": np.asarray(ready, dtype=int),
                    }
                )
                mean = float(train.loc[retained, "target"].mean())
                if summary.get("baseline_mean_train") != mean:
                    raise DataContractError(
                        "Baseline mean was not fitted on the retained inner train labels"
                    )
                statistics = summary.get("label_statistics", {})
                if statistics != {
                    "mean": {"&-s_return": mean},
                    "std": {"&-s_return": float(train.loc[retained, "target"].to_numpy().std())},
                }:
                    raise DataContractError(
                        "Label statistics were not fitted on retained training labels"
                    )
                rebuilt.extend(
                    [
                        result,
                        result.assign(model="mean_train", prediction=mean, do_predict=1),
                        result.assign(model="zero", prediction=0.0, do_predict=1),
                    ]
                )
                checks.append(
                    {
                        "fold_id": fold["fold_id"],
                        "pair": pair,
                        "fit_samples": len(retained),
                        "purged_samples": len(purged),
                        "validation_samples": len(used),
                        "replayed_predictions": len(test),
                        "violations": 0,
                    }
                )
            expected = access.select(metadata, fold["test_ids"], "metrics").copy()
            expected["target"] = [
                tables[row.pair].at[identity, "target"] for identity, row in expected.iterrows()
            ]
            expected["fold_id"] = fold["fold_id"]
            expected_rows.append(expected)
    predictions = pd.concat(rebuilt, ignore_index=True)
    original_predictions = pd.read_parquet(output / "predictions.parquet")
    try:
        assert_frame_equal(original_predictions, predictions, check_exact=True)
    except AssertionError as error:
        raise DataContractError("Predictions differ from actual model/pipeline replay") from error
    result = evaluate_predictions(
        predictions, pd.concat(expected_rows), contract["comparison_contract"]
    )
    try:
        assert_frame_equal(
            pd.read_parquet(output / "expected_predictions.parquet"),
            pd.concat(expected_rows),
            check_exact=True,
        )
    except AssertionError as error:
        raise DataContractError("Expected prediction identities or truths were changed") from error
    published = json.loads((output / "prediction_metrics.json").read_text())
    if result != published:
        raise DataContractError("Prediction metrics differ from independently recomputed inputs")
    access_audit = _verify_access_audit(output / "data_access.jsonl", access.events, manifest)
    return {
        "status": "PASS",
        "scope": "development",
        "formal_admission": "BLOCKED",
        "holdout_evaluated": False,
        "checks": checks,
        "violations": 0,
        "prediction_replay_tolerance": 0.0,
        "access_audit": access_audit,
    }
