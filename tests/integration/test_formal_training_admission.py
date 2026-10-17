"""Formal entry rejects admission before calling any model training function."""

import json

import pytest

from quant_strategy.cli import main
from quant_strategy.config import ExperimentConfig
from quant_strategy.errors import DataContractError
from quant_strategy.validation.admission import require_training_admission


@pytest.mark.parametrize("status", ["FAIL", "PARTIAL", "BLOCKED"])
def test_formal_entry_does_not_train_with_failed_engineering_gate(tmp_path, monkeypatch, status):
    report = tmp_path / "readiness.json"
    report.write_text(
        json.dumps(
            {"schema_version": 1, "status": status, "formal_out_of_sample_research_allowed": False}
        )
    )

    def prohibited(*args, **kwargs):
        pytest.fail("Training must not start after denied admission")

    monkeypatch.setattr("quant_strategy.cli.run_experiment", prohibited)
    assert (
        main(
            [
                "formal-run",
                "-c",
                "configs/base.yaml",
                "-c",
                "configs/environment/local.yaml",
                "--readiness",
                str(report),
                "--output",
                str(tmp_path / "training"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "training").exists()


def test_pass_word_without_six_gates_is_not_admission(tmp_path):
    report = tmp_path / "fake.json"
    report.write_text(
        json.dumps(
            {"schema_version": 1, "status": "PASS", "formal_out_of_sample_research_allowed": True}
        )
    )
    with pytest.raises(DataContractError, match="six"):
        require_training_admission(report, ExperimentConfig())


def test_six_claimed_passes_without_executed_tests_are_not_admission(tmp_path):
    report = tmp_path / "fake.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "PASS",
                "formal_out_of_sample_research_allowed": True,
                "phases": {str(i): {"status": "PASS"} for i in range(1, 7)},
            }
        )
    )
    with pytest.raises(DataContractError, match="execution"):
        require_training_admission(report, ExperimentConfig())
