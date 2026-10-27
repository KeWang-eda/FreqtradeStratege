"""Receipt-boundary fixtures are not claims of successful model training."""

import os
import shutil
import subprocess
import sys
from copy import deepcopy

import pytest

from quant.infrastructure.experiment_store import file_hash, write_json
from quant.research import controlled
from quant.validation.admission import new_receipt_context


def valid_network():
    return {
        "policy": "deny-all",
        "completed": True,
        "exit_code": 0,
        "denied_operations": 0,
        "http_requests": [],
        "socket_events": [],
        "process_events": [
            {
                "event": "subprocess.Popen",
                "allowed": True,
                "executable": shutil.which("git"),
                "scope": "fixed local Git provenance query",
            }
        ],
    }


def envelope_fixture(tmp_path, trained=True):
    """Make hash-bound boundary placeholders, never a model/acceptance fixture."""
    evidence = tmp_path / "envelope"
    evidence.mkdir()
    names = set(controlled.BASE_ARTIFACTS)
    if trained:
        names |= set(controlled.TRAINING_ARTIFACTS)
    for name in names:
        path = evidence / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"boundary-only fixture, not a training artifact\n")
    write_json(evidence / "network.json", valid_network())
    run = {
        "status": "PASS",
        "scope": "development",
        "formal_oos_result": False,
        "formal_research_status": "BLOCKED",
        "holdout_metrics_generated": False,
        "train_development_requested": trained,
        "artifacts": {name: file_hash(evidence / name) for name in sorted(names)},
    }
    write_json(evidence / "run.json", run)
    return evidence, run


def test_network_boundary_accepts_deny_all_zero_network_and_only_local_git():
    controlled.validate_network_audit(valid_network())


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_policy",
        "incomplete",
        "nonzero_exit",
        "missing_exit",
        "fake_zero_counter_http",
        "fake_zero_counter_dns",
        "allowed_http",
        "allowed_socket",
        "denied_process",
        "unapproved_process_scope",
        "unapproved_executable",
        "unapproved_process_event",
        "wrong_allowed_type",
        "missing_events",
        "events_not_list",
        "noninteger_counter",
    ],
)
def test_network_boundary_rejects_operations_and_forged_summary_counters(fault):
    audit = deepcopy(valid_network())
    if fault == "wrong_policy":
        audit["policy"] = "metadata-only"
    elif fault == "incomplete":
        audit["completed"] = False
    elif fault == "nonzero_exit":
        audit["exit_code"] = 3
    elif fault == "missing_exit":
        del audit["exit_code"]
    elif fault in {"fake_zero_counter_http", "allowed_http"}:
        audit["http_requests"] = [{"host": "fapi.binance.com", "allowed": fault == "allowed_http"}]
    elif fault in {"fake_zero_counter_dns", "allowed_socket"}:
        audit["socket_events"] = [
            {
                "event": "socket.getaddrinfo",
                "host": "fapi.binance.com",
                "allowed": fault == "allowed_socket",
            }
        ]
    elif fault == "denied_process":
        audit["process_events"][0]["allowed"] = False
    elif fault == "unapproved_process_scope":
        audit["process_events"][0]["scope"] = "arbitrary child"
    elif fault == "unapproved_executable":
        audit["process_events"][0]["executable"] = "/unapproved/git"
    elif fault == "unapproved_process_event":
        audit["process_events"][0]["event"] = "os.system"
    elif fault == "wrong_allowed_type":
        audit["process_events"][0]["allowed"] = 1
    elif fault == "missing_events":
        del audit["socket_events"]
    elif fault == "events_not_list":
        audit["http_requests"] = {}
    else:
        audit["denied_operations"] = False
    with pytest.raises((ValueError, KeyError, TypeError)):
        controlled.validate_network_audit(audit)


@pytest.mark.parametrize("trained", [False, True])
def test_execution_envelope_accepts_complete_exact_boundary_inventory(tmp_path, trained):
    evidence, run = envelope_fixture(tmp_path, trained)
    controlled.validate_execution_envelope(evidence, run)


@pytest.mark.parametrize(
    "fault",
    [
        "omit_required_manifest_entry",
        "remove_required_file_and_entry",
        "unlisted_extra",
        "listed_extra",
        "artifact_corruption",
        "artifact_escape",
        "formal_scope",
        "formal_result",
        "unlocked_formal_status",
        "holdout_metrics",
        "incomplete_run",
        "tampered_network_rehashed",
    ],
)
def test_execution_envelope_rejects_rehashed_inventory_and_policy_corruption(tmp_path, fault):
    evidence, run = envelope_fixture(tmp_path)
    required = sorted(set(controlled.BASE_ARTIFACTS) - {"network.json"})[0]
    if fault == "omit_required_manifest_entry":
        del run["artifacts"][required]
    elif fault == "remove_required_file_and_entry":
        del run["artifacts"][required]
        (evidence / required).unlink()
    elif fault in {"unlisted_extra", "listed_extra"}:
        extra = evidence / "holdout_metrics.json"
        extra.write_text('{"scope": "formal"}\n')
        if fault == "listed_extra":
            run["artifacts"][extra.name] = file_hash(extra)
    elif fault == "artifact_corruption":
        (evidence / required).write_bytes(b"changed after recording\n")
    elif fault == "artifact_escape":
        external = tmp_path / "outside.json"
        external.write_text("{}\n")
        run["artifacts"]["../outside.json"] = file_hash(external)
    elif fault == "formal_scope":
        run["scope"] = "formal"
    elif fault == "formal_result":
        run["formal_oos_result"] = True
    elif fault == "unlocked_formal_status":
        run["formal_research_status"] = "PASS"
    elif fault == "holdout_metrics":
        run["holdout_metrics_generated"] = True
    elif fault == "incomplete_run":
        run["status"] = "RUNNING"
    else:
        audit = valid_network()
        audit["http_requests"].append({"host": "fapi.binance.com", "allowed": False})
        # A fresh byte hash cannot make inconsistent underlying events valid.
        write_json(evidence / "network.json", audit)
        run["artifacts"]["network.json"] = file_hash(evidence / "network.json")
    with pytest.raises((ValueError, KeyError, TypeError)):
        controlled.validate_execution_envelope(evidence, run)


def test_real_cli_refuses_existing_output_without_mutating_old_receipts(tmp_path):
    output = tmp_path / "preserved"
    output.mkdir()
    run = output / "run.json"
    network = output / "network.json"
    run.write_text('{"artifacts": {}, "preserve": "old run"}\n')
    network.write_text('{"preserve": "old network audit"}\n')
    before = {path.name: path.read_bytes() for path in (run, network)}
    command = [
        sys.executable,
        "tools/prepare_controlled_research.py",
        "-c",
        "configs/base.yaml",
        "-c",
        "configs/research.yaml",
        "-c",
        "configs/experiments/btc_eth_bnb_controlled_v1.yaml",
        "--output",
        str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode != 0
    assert {path.name: path.read_bytes() for path in (run, network)} == before
    assert set(path.name for path in output.iterdir()) == set(before)


def test_single_real_old_test_receipt_cannot_establish_complete_project_execution(tmp_path):
    """Run one genuine test; its true exit0/JUnit still lacks mandatory coverage."""
    directory = tmp_path / "actual-single-test"
    directory.mkdir()
    junit = directory / "junit.xml"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/unit/test_config_labels_features.py::test_metrics_empty_constant_and_known_values",
        f"--junitxml={junit}",
    ]
    context = new_receipt_context(directory.name)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = "."
    completed = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    receipt_path = directory / "test_run.json"
    write_json(
        receipt_path,
        {
            **context,
            "command": command,
            "exit_code": completed.returncode,
            "junit": junit.name,
            "junit_sha256": file_hash(junit),
        },
    )
    with pytest.raises(ValueError, match="[Cc]omplete|required|Required|coverage|collect"):
        controlled.verify_complete_test_execution(receipt_path, run_id=directory.name)
