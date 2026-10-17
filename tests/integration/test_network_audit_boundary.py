"""Audit-process probes must deny and record operations even if a task catches errors."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "operation",
    ["http", "dns", "connect", "sendto", "sendmsg", "getnameinfo", "child", "system", "git_remote"],
)
def test_caught_denial_cannot_report_success(tmp_path, operation):
    report = tmp_path / "audit.json"
    script = r"""
import socket, subprocess, sys, types, os
from tools.audit_local_network import main, NetworkDenied
def run(arguments):
    try:
        operation = sys.argv[2]
        if operation == "http":
            import requests
            requests.get("https://example.invalid/")
        elif operation == "dns":
            socket.getaddrinfo("example.invalid",443)
        elif operation == "getnameinfo":
            socket.getnameinfo(("203.0.113.1", 443), 0)
        elif operation == "child":
            subprocess.run([sys.executable,"-c","pass"], check=True)
        elif operation == "git_remote":
            subprocess.run(["git","fetch"], check=True)
        elif operation == "system":
            os.system("true")
        else:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                if operation == "connect": sock.connect(("203.0.113.1",53))
                elif operation == "sendto": sock.sendto(b"probe",("203.0.113.1",53))
                elif operation == "sendmsg": sock.sendmsg([b"probe"],[],0,("203.0.113.1",53))
    except NetworkDenied:
        pass
    return 0
module=types.ModuleType("quant_strategy.cli")
module.main=run
sys.modules["quant_strategy.cli"]=module
raise SystemExit(main(["--policy","deny-all","--report",sys.argv[1],"research"]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(report), operation],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 3, result.stdout + result.stderr
    evidence = json.loads(report.read_text())
    assert evidence["completed"] and evidence["exit_code"] == 3
    assert evidence["denied_operations"] == 1


def test_audit_setup_failure_is_recorded_as_failure(tmp_path):
    report = tmp_path / "audit.json"
    script = """
import sys
from tools import audit_local_network as module
def fail(*args): raise RuntimeError("injected setup failure")
module.install_policy=fail
raise SystemExit(module.main(["--policy","deny-all","--report",sys.argv[1],"research"]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(report)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    evidence = json.loads(report.read_text())
    assert not evidence["completed"] and evidence["error"]["type"] == "RuntimeError"
