"""Runner receipts preserve actual selection, failures and observable real fits."""

import json
import os
import subprocess
import sys
from xml.etree import ElementTree

import pytest


@pytest.fixture(scope="module")
def profiled_execution(tmp_path_factory):
    output = tmp_path_factory.mktemp("suite-observer") / "execution"
    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_tests.py",
            "ci",
            "--output",
            str(output),
            "--profile",
            "--",
            "tests/contract/test_backends_and_splits.py::test_model_fit_predict_save_load[xgboost]",
        ],
        env={**os.environ, "PYTEST_ADDOPTS": "-k impossible_hidden_filter"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return output


def test_exact_selection_and_actual_fit_receipt_ignore_hidden_addopts(profiled_execution):
    output = profiled_execution
    receipt = json.loads((output / "test_run.json").read_text())
    nodes = json.loads((output / "nodes.json").read_text())
    assert receipt["exit_code"] == 0
    assert receipt["pytest_addopts_cleared"] is True
    assert receipt["inherited_pytest_addopts"] == "-k impossible_hidden_filter"
    assert receipt["counts"] == {"tests": 1, "passed": 1, "failures": 0, "errors": 0, "skipped": 0}
    assert receipt["selected_nodeids"] == [record["node_id"] for record in nodes["selected_nodes"]]
    assert len(list(ElementTree.parse(output / "junit.xml").getroot().iter("testcase"))) == 1
    assert receipt["profile_counts"]["xgboost_fits"] == 1
    assert receipt["collect_only"] is False


def test_runner_refuses_to_overwrite_existing_execution(profiled_execution):
    output = profiled_execution
    before = (output / "test_run.json").read_bytes()
    completed = subprocess.run(
        [sys.executable, "tools/run_tests.py", "ci", "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert (output / "test_run.json").read_bytes() == before


def test_runner_preserves_nonzero_pytest_exit_and_empty_selection(tmp_path):
    output = tmp_path / "failure"
    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_tests.py",
            "ci",
            "--output",
            str(output),
            "--",
            "--deliberately-invalid-option",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 4
    receipt = json.loads((output / "test_run.json").read_text())
    assert receipt["exit_code"] == 4
    assert receipt["counts"]["passed"] == 0
    assert receipt["selected_nodeids"] == []
    assert (output / "pytest.log").is_file()


@pytest.mark.parametrize("fault", ["empty_rehashed", "duplicate", "missing_phase", "false_success"])
def test_rehashed_selection_corruption_is_rejected(profiled_execution, tmp_path, fault):
    from quant_strategy.infrastructure.experiment_store import file_hash
    from tools.verify_test_consolidation import validate_selection

    output = profiled_execution
    receipt = json.loads((output / "test_run.json").read_text())
    selection = json.loads((output / "nodes.json").read_text())
    expected = set(receipt["selected_nodeids"])
    validate_selection(output / "test_run.json", expected, "ci")
    if fault == "empty_rehashed":
        selection["selected_nodes"] = []
    elif fault == "duplicate":
        selection["reports"].append(selection["reports"][0].copy())
    elif fault == "missing_phase":
        selection["reports"].pop()
    else:
        selection["reports"][0]["outcome"] = "failed"
    path = tmp_path / "nodes.json"
    path.write_text(json.dumps(selection))
    receipt["selected_nodes_file"] = path.name
    receipt["selected_nodes_file_sha256"] = file_hash(path)
    record = tmp_path / "test_run.json"
    record.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        validate_selection(record, expected, "ci")
