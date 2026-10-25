"""Pytest observer writing exact selected nodes and per-phase outcomes."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--suite-record", help="Write exact collection and outcomes as JSON")


@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session):
    session.config._suite_nodes = [
        {"node_id": item.nodeid, "markers": sorted({m.name for m in item.iter_markers()})}
        for item in session.items
    ]
    session.config._suite_reports = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    # Report hooks have no config argument; attach this item's config only for
    # its protocol. Sequential pytest execution is the reference runner mode.
    global _active_config
    _active_config = item.config
    yield


def pytest_runtest_logreport(report):
    if _active_config is not None:
        _active_config._suite_reports.append(
            {
                "node_id": report.nodeid,
                "phase": report.when,
                "outcome": report.outcome,
                "seconds": report.duration,
            }
        )


_active_config = None


def pytest_sessionfinish(session, exitstatus):
    destination = session.config.getoption("--suite-record")
    if destination:
        Path(destination).write_text(
            json.dumps(
                {
                    "invocation_args": list(session.config.invocation_params.args),
                    "cwd": str(session.config.invocation_params.dir),
                    "execution_id": os.environ.get("QUANT_TEST_EXECUTION_ID"),
                    "pid": os.getpid(),
                    "python": sys.executable,
                    "selected_nodes": getattr(session.config, "_suite_nodes", []),
                    "reports": getattr(session.config, "_suite_reports", []),
                    "exit_code": int(exitstatus),
                },
                indent=2,
            )
            + "\n"
        )
