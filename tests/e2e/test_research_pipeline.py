"""Small complete research experiments run without exchange/network access."""

import json
from dataclasses import replace

import pandas as pd
import pytest
import yaml

from quant.api import build_dataset, load_model, run_experiment
from quant.cli import main
from quant.config import ExperimentConfig, LabelConfig, ModelConfig
from quant.errors import DataContractError
from quant.experiments.runner import compare_experiments
from quant.infrastructure.artifact_audit import check_artifacts


@pytest.mark.parametrize("mode", ["raw", "volnorm"])
@pytest.mark.parametrize("model", ["ridge", "xgboost"])
def test_complete_research_artifacts_and_final_holdout(tmp_path, candles, mode, model):
    params = (
        {} if model == "ridge" else {"n_estimators": 15, "early_stopping_rounds": 3, "max_depth": 2}
    )
    config = ExperimentConfig(
        label=LabelConfig(mode=mode), model=ModelConfig(name=model, params=params)
    )
    frames = {"BTC": candles, "ETH": candles.assign(volume=candles.volume * 2)}
    output = run_experiment(
        config,
        tmp_path,
        frames=frames,
        experiment_id=f"{mode}-{model}",
        evaluate_final_holdout=True,
    )
    required = {
        "manifest.json",
        "config.resolved.yaml",
        "feature_schema.json",
        "folds.json",
        "metrics_prediction.json",
        "metrics_backtest.json",
        "leakage_report.json",
        "predictions.parquet",
        "dataset_metadata.parquet",
        "development_metadata.parquet",
    }
    assert required.issubset({path.name for path in output.iterdir()})
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "complete" and manifest["final_holdout_evaluated"]
    table = pd.read_parquet(output / "predictions.parquet")
    assert set(table.phase) == {"development", "final_holdout"}
    assert set(table.pair) == {"BTC", "ETH"}
    final_start = pd.Timestamp(manifest["final_holdout"]["start"])
    development = table.loc[table.phase == "development"]
    assert (development.candle_timestamp + pd.Timedelta(hours=4) < final_start).all()
    assert (development.training_data_end < final_start).all()
    assert json.loads((output / "leakage_report.json").read_text())["passed"]
    model_dir = next((output / "model").glob("final/*"))
    preprocessor, loaded, artifact = load_model(model_dir, config)
    matrix = build_dataset(frames, config).X.iloc[-2:]
    assert len(loaded.predict(preprocessor.transform(matrix))) == 2
    assert artifact["model_version"].startswith(manifest["experiment_id"])
    assert check_artifacts(output)["verified_models"] == 8
    with pytest.raises(DataContractError):
        load_model(
            model_dir,
            replace(config, label=LabelConfig(mode="volnorm" if mode == "raw" else "raw")),
        )
    (model_dir / "model.bin").write_bytes(b"corrupt")
    with pytest.raises(DataContractError, match="checksum"):
        load_model(model_dir, config)
    with pytest.raises(FileExistsError):
        run_experiment(config, tmp_path, frames=frames, experiment_id=f"{mode}-{model}")


def test_cli_and_default_unseen_final_holdout(tmp_path, candles, capsys):
    source = tmp_path / "candles.feather"
    candles.to_feather(source)
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"research": {"name": "cli", "data": {"BTC": str(source)}}}))
    assert main(["validate", "-c", str(config)]) == 0
    assert (
        main(["run", "-c", str(config), "--output", str(tmp_path), "--experiment-id", "cli-run"])
        == 0
    )
    output = tmp_path / "cli-run"
    manifest = json.loads((output / "manifest.json").read_text())
    assert not manifest["final_holdout_evaluated"]
    table = pd.read_parquet(output / "predictions.parquet")
    assert set(table.phase) == {"development"}
    assert main(["compare", str(output)]) == 0
    assert main(["artifact-check", str(output)]) == 0
    assert main(["leakage-check", str(output)]) == 0
    assert main(["dataset-build", "-c", str(config)]) == 0
    assert compare_experiments([output])[0]["experiment_id"] == "cli-run"
    assert "cli-run" in capsys.readouterr().out


def test_failed_experiment_is_recorded(tmp_path, candles):
    with pytest.raises(DataContractError):
        run_experiment(
            ExperimentConfig(), tmp_path, frames={"BTC": candles.iloc[:4]}, experiment_id="failed"
        )
    manifest = json.loads((tmp_path / "failed" / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["error"]["type"] == "DataContractError"
