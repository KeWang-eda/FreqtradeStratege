"""A comparison must not silently join failed, corrupt or incompatible runs."""

import json
from dataclasses import replace

import pytest

from quant.config import ExperimentConfig, LabelConfig, ModelConfig
from quant.errors import DataContractError
from quant.experiments.runner import compare_experiments, run_experiment
from quant.infrastructure.experiment_store import file_hash


@pytest.fixture
def experiment(tmp_path, candles):
    return run_experiment(
        ExperimentConfig(), tmp_path, frames={"BTC": candles}, experiment_id="baseline"
    )


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "input_data_sha256",
        "dataset_sha256",
        "folds_sha256",
        "label",
        "feature_version",
        "experiment_scope",
        "cost_assumptions",
    ],
)
def test_changed_comparison_contract_is_rejected(experiment, field):
    manifest_path = experiment / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if field == "status":
        manifest[field] = "failed"
    elif field == "label":
        manifest[field] = {**manifest[field], "prediction_horizon": 999}
    elif field == "cost_assumptions":
        manifest[field] = {"fees": "unverified"}
    else:
        manifest[field] = "altered"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(DataContractError):
        compare_experiments([experiment])


def test_changed_prediction_artifact_cannot_be_compared(experiment):
    (experiment / "metrics_prediction.json").write_text("{}")
    with pytest.raises(DataContractError, match="checksum|fingerprint"):
        compare_experiments([experiment])


def test_different_labels_refuse_direct_comparison(tmp_path, candles, experiment):
    alternate = run_experiment(
        replace(ExperimentConfig(), label=LabelConfig(mode="volnorm")),
        tmp_path,
        frames={"BTC": candles},
        experiment_id="different-label",
    )
    with pytest.raises(DataContractError, match="comparable|contract"):
        compare_experiments([experiment, alternate])


def test_different_fold_indexes_refuse_direct_comparison(tmp_path, candles, experiment):
    config = ExperimentConfig()
    alternate = run_experiment(
        replace(config, validation=replace(config.validation, embargo_candles=5)),
        tmp_path,
        frames={"BTC": candles},
        experiment_id="different-folds",
    )
    with pytest.raises(DataContractError, match="comparable|contract"):
        compare_experiments([experiment, alternate])


def test_models_can_differ_when_data_labels_and_fold_contract_match(tmp_path, candles, experiment):
    alternate = run_experiment(
        replace(ExperimentConfig(), model=ModelConfig(name="ridge", params={"alpha": 2.0})),
        tmp_path,
        frames={"BTC": candles},
        experiment_id="different-model",
    )
    assert len(compare_experiments([experiment, alternate])) == 2


def test_manifest_cannot_remove_required_artifact_from_inventory(experiment):
    path = experiment / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["artifact_checksums"].pop("folds.json")
    path.write_text(json.dumps(manifest))
    with pytest.raises(DataContractError):
        compare_experiments([experiment])


def test_modified_fold_with_updated_artifact_hash_still_fails_contract(experiment):
    path = experiment / "folds.json"
    folds = json.loads(path.read_text())
    folds[0]["train_indices"] = folds[0]["train_indices"][1:]
    path.write_text(json.dumps(folds))
    manifest_path = experiment / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifact_checksums"][path.name] = file_hash(path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(DataContractError):
        compare_experiments([experiment])
