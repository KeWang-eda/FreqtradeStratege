"""Synthetic parser/gate probes; these never represent real backtest evidence."""

import json

import pytest

from quant_strategy.infrastructure.experiment_store import file_hash
from tools import run_offline_extension as module

PROXY = """100 socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_TCP) = 6
100 connect(6, {sa_family=AF_INET, sin_port=htons(7890), sin_addr=inet_addr("127.0.0.1")}, 16) = -1 EINPROGRESS
100 sendto(6, "TLS", 3, 0, NULL, 0) = 3
100 +++ exited with 0 +++
"""
WAKEUP = """100 socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, [4, 5]) = 0
101 sendto(5, "wake", 4, 0, NULL, 0) = 4
"""


@pytest.mark.parametrize("local_wakeup", [False, True])
def test_actual_proxy_transport_and_known_local_ipc_are_classified(local_wakeup):
    report = module.inspect_online_trace((WAKEUP if local_wakeup else "") + PROXY)
    assert report == {
        "proxy_connect_count": 1,
        "proxy_send_count": 1,
        "local_wakeup_send_count": int(local_wakeup),
        "other_connect_or_send_count": 0,
    }


@pytest.mark.parametrize(
    "change",
    [
        "remote_host",
        "wrong_port",
        "unknown_fd",
        "explicit_destination",
        "unconnected_fd",
        "sendmsg",
        "missing_exit",
        "second_connection",
        "unix_fd_reused_for_ip",
    ],
)
def test_trace_rejects_unclassified_or_external_operations(change):
    trace = PROXY
    if change == "remote_host":
        trace = trace.replace("127.0.0.1", "203.0.113.1")
    elif change == "wrong_port":
        trace = trace.replace("7890", "443")
    elif change == "unknown_fd":
        trace = trace.replace("sendto(6,", "sendto(9,")
    elif change == "explicit_destination":
        trace = trace.replace("NULL, 0)", "{sa_family=AF_INET, sin_port=htons(53)}, 16)")
    elif change == "unconnected_fd":
        trace = "\n".join(line for line in trace.splitlines() if "connect(" not in line)
    elif change == "sendmsg":
        trace = trace.replace("sendto(6,", "sendmsg(6,")
    elif change == "missing_exit":
        trace = trace.replace("+++ exited with 0 +++", "+++ killed by SIGKILL +++")
    elif change == "second_connection":
        trace += PROXY
    else:
        trace = WAKEUP + "100 socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP) = 5\n"
        trace += '100 sendto(5, "packet", 6, 0, NULL, 0) = 6\n' + PROXY
    with pytest.raises(RuntimeError):
        module.inspect_online_trace(trace)


@pytest.fixture
def gates(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    minimum = {
        "status": "PASS",
        "pairs": module.PAIRS[:2],
        "timerange": "20250101-20250115",
        "regression": {"passed": True},
    }
    coverage = {
        "requirements": {"timerange": module.TIMERANGE},
        "trading_pairs": module.PAIRS,
        "pairs": [],
        "configs": [],
    }
    for index, pair in enumerate(module.PAIRS):
        path = tmp_path / f"probe{index}.bin"
        path.write_bytes(b"unit-test-only input hash probe")
        coverage["pairs"].append(
            {
                "pair": pair,
                "raw_data_ready": True,
                "files": [{"path": path.name, "sha256": file_hash(path)}],
            }
        )
    return tmp_path, minimum, coverage


def save_gates(gates):
    directory, minimum, coverage = gates
    paths = directory / "minimum.json", directory / "coverage.json"
    for path, value in zip(paths, (minimum, coverage)):
        path.write_text(json.dumps(value))
    return paths


def test_gate_accepts_matching_explicit_scope_and_hashes(gates):
    minimum, coverage = module.validate_gates(*save_gates(gates))
    assert minimum["status"] == "PASS"
    assert all(pair["raw_data_ready"] for pair in coverage["pairs"])


@pytest.mark.parametrize(
    "failure",
    ["minimum_failed", "minimum_scope", "range", "scope", "missing_pair", "raw", "data_changed"],
)
def test_gate_rejects_missing_prerequisites_before_network(gates, failure):
    directory, minimum, coverage = gates
    if failure == "minimum_failed":
        minimum["regression"]["passed"] = False
    elif failure == "minimum_scope":
        minimum["pairs"] = [module.PAIRS[0]]
    elif failure == "range":
        coverage["requirements"]["timerange"] = "20250101-20250115"
    elif failure == "scope":
        coverage["trading_pairs"] = module.PAIRS[:2]
    elif failure == "missing_pair":
        coverage["pairs"].pop()
    elif failure == "raw":
        coverage["pairs"][2]["raw_data_ready"] = False
    else:
        (directory / coverage["pairs"][2]["files"][0]["path"]).write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="BLOCKED"):
        module.validate_gates(*save_gates(gates))


@pytest.mark.parametrize("failure", [None, "scope", "component", "http", "socket", "exit"])
def test_online_audit_requires_exact_native_execution_scope(tmp_path, failure):
    audit = {
        "policy": "metadata-only",
        "component": "freqtrade",
        "arguments": ["backtesting", *module.native_arguments(tmp_path)],
        "exit_code": 0,
        "completed": True,
        "denied_operations": 0,
        "http_requests": [module.METADATA_REQUEST],
        "socket_events": [
            {"allowed": True, "event": "socket.connect", "host": "127.0.0.1", "port": 7890}
        ],
        "process_events": [],
    }
    if failure == "scope":
        audit["arguments"][-1] = "other-results"
    elif failure == "component":
        audit["component"] = "offline-backtest"
    elif failure == "http":
        audit["http_requests"] = []
    elif failure == "socket":
        audit["socket_events"][0]["host"] = "203.0.113.1"
    elif failure == "exit":
        audit["exit_code"] = 3
    if failure:
        with pytest.raises(RuntimeError):
            module.validate_online_audit(audit, tmp_path, 0)
    else:
        module.validate_online_audit(audit, tmp_path, 0)
