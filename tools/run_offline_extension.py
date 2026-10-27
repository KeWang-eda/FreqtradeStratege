"""Run a gated, fresh three-pair native online/offline acceptance comparison.

References: native Freqtrade backtesting --cache/--export contracts;
https://www.freqtrade.io/en/stable/backtesting/
https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/Exchange-Information
Linux unshare(1)/strace(1) and run_offline_acceptance.py publication contracts.
Only the explicit capture and online metadata initialization may use networking.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from quant.infrastructure.experiment_store import environment_versions, file_hash
from tools.run_offline_acceptance import (
    ROOT,
    audited_run,
    check_isolation,
    json_text,
    publish,
    require_zero_network,
)
from tools.verify_freqtrade_regression import compare_runs

PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT"]
TIMERANGE = "20250101-20250122"
PREFIX = "phase4_extension"
CONFIGS = [
    "config.json",
    "configs/backtest-local.json",
    "configs/environment/freqtrade-mihomo.json",
]
METADATA_REQUEST = {
    "method": "GET",
    "host": "fapi.binance.com",
    "path": "/fapi/v1/exchangeInfo",
    "allowed": True,
}


def validate_gates(minimum_path: Path, coverage_path: Path) -> tuple[dict, dict]:
    """Require actual minimum PASS plus exact expanded raw-data approval."""
    minimum = json.loads(minimum_path.read_text())
    if (
        minimum.get("status") != "PASS"
        or minimum.get("pairs") != PAIRS[:2]
        or minimum.get("timerange") != "20250101-20250115"
        or minimum.get("regression", {}).get("passed") is not True
    ):
        raise RuntimeError("BLOCKED: minimum Phase 4 native acceptance must pass first")
    coverage = json.loads(coverage_path.read_text())
    if (
        coverage.get("requirements", {}).get("timerange") != TIMERANGE
        or coverage.get("trading_pairs") != PAIRS
    ):
        raise RuntimeError("BLOCKED: expanded coverage must approve the exact timerange")
    indexed = {item["pair"]: item for item in coverage["pairs"]}
    for pair in PAIRS:
        if pair not in indexed or indexed[pair].get("raw_data_ready") is not True:
            raise RuntimeError(f"BLOCKED: expanded raw-data coverage is not ready for {pair}")
        for item in indexed[pair]["files"]:
            if file_hash(ROOT / item["path"]) != item["sha256"]:
                raise RuntimeError("BLOCKED: data changed after expanded coverage approval")
    for item in coverage["configs"]:
        if file_hash(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError("BLOCKED: configuration changed after coverage approval")
    return minimum, coverage


def native_arguments(userdir: Path) -> list[str]:
    """Share identical native configuration/scope, differing only in fresh userdirs."""
    return [
        *(value for config in CONFIGS for value in ("-c", config)),
        "--userdir",
        str(userdir),
        "--datadir",
        str(ROOT / "data"),
        "--strategy-path",
        str(ROOT),
        "--freqaimodel-path",
        str(ROOT / "quant" / "models" / "freqai"),
        "--strategy",
        "MyStrategy",
        "--timerange",
        TIMERANGE,
        "--pairs",
        *PAIRS,
        "--cache",
        "none",
        "--export",
        "signals",
        "--backtest-directory",
        str(userdir / "results"),
    ]


def inspect_online_trace(trace_text: str) -> dict:
    """Allow tracked proxy TCP transport and local AF_UNIX socketpair wakeups.

    SSL writes use sendto(NULL) on the connected proxy descriptor. Asyncio's
    resolver thread may use sendto(NULL) on its AF_UNIX socketpair. Unknown
    descriptors, explicit send destinations and other connections fail closed.
    """
    descriptors: dict[int, str] = {}
    counts = {"proxy_connect_count": 0, "proxy_send_count": 0, "local_wakeup_send_count": 0}
    for line in trace_text.splitlines():
        pair = re.search(r"socketpair\(AF_UNIX,.*\[(\d+), (\d+)\]\)\s*= 0", line)
        if pair:
            for descriptor in pair.groups():
                descriptors[int(descriptor)] = "unix_socketpair"
        created = re.search(r"socket\((AF_INET6?),.*\)\s*= (\d+)", line)
        if created:
            descriptors[int(created.group(2))] = "unconnected_ip"
        operation = re.search(r"\b(connect|sendto|sendmsg|sendmmsg)\((\d+),", line)
        if not operation:
            continue
        kind, descriptor_text = operation.groups()
        descriptor = int(descriptor_text)
        if kind == "connect":
            if (
                descriptors.get(descriptor) != "unconnected_ip"
                or 'inet_addr("127.0.0.1")' not in line
                or "htons(7890)" not in line
            ):
                raise RuntimeError("Expanded online trace attempted an unapproved connection")
            descriptors[descriptor] = "proxy"
            counts["proxy_connect_count"] += 1
        elif kind == "sendto" and re.search(r", NULL, 0\)\s*=", line):
            scope = descriptors.get(descriptor)
            if scope == "proxy":
                counts["proxy_send_count"] += 1
            elif scope == "unix_socketpair":
                counts["local_wakeup_send_count"] += 1
            else:
                raise RuntimeError("Expanded online trace sent through an unknown descriptor")
        else:
            raise RuntimeError("Expanded online trace attempted an unapproved send destination")
    if counts["proxy_connect_count"] != 1 or counts["proxy_send_count"] == 0:
        raise RuntimeError("Expanded online trace lacks actual single-proxy TLS traffic")
    if "+++ exited with 0 +++" not in trace_text:
        raise RuntimeError("Expanded online strace lacks successful process completion")
    counts["other_connect_or_send_count"] = 0
    return counts


def validate_online_audit(audit: dict, userdir: Path, exit_code: int) -> None:
    """Require genuine complete native execution with the exact expanded arguments."""
    if (
        exit_code != 0
        or audit.get("policy") != "metadata-only"
        or audit.get("component") != "freqtrade"
        or audit.get("arguments") != ["backtesting", *native_arguments(userdir)]
        or audit.get("exit_code") != 0
        or audit.get("completed") is not True
        or audit.get("denied_operations") != 0
        or audit.get("http_requests") != [METADATA_REQUEST]
        or any(
            not event["allowed"]
            or event["event"] != "socket.connect"
            or event["host"] != "127.0.0.1"
            or event["port"] != 7890
            for event in audit["socket_events"]
        )
        or any(not event["allowed"] for event in audit["process_events"])
    ):
        raise RuntimeError("Expanded online baseline violated the metadata-only boundary")
    if not audit["socket_events"]:
        raise RuntimeError("Expanded online baseline lacks real proxy connection evidence")


def online_run(workspace: Path, userdir: Path) -> dict:
    """Permit only genuine exchangeInfo over the existing process-local proxy."""
    name = f"{PREFIX}_online"
    report, trace = workspace / f"{name}_network.json", workspace / f"{name}_network.strace"
    command = [
        "strace",
        "-f",
        "-e",
        "trace=network",
        "-o",
        str(trace),
        sys.executable,
        str(ROOT / "tools/audit_local_network.py"),
        "--policy",
        "metadata-only",
        "--report",
        str(report),
        "freqtrade",
        "backtesting",
        *native_arguments(userdir),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=240,
    )
    (workspace / f"{name}.log").write_text(result.stdout + result.stderr)
    audit = json.loads(report.read_text())
    validate_online_audit(audit, userdir, result.returncode)
    return {
        "exit_code": result.returncode,
        "audit": audit,
        "syscalls": inspect_online_trace(trace.read_text()),
        "command": command,
    }


def capture(workspace: Path) -> Path:
    """Explicitly acquire fresh real metadata; never download price candles."""
    snapshot = workspace / f"{PREFIX}_snapshot.json"
    command = [
        sys.executable,
        "-m",
        "quant.execution.offline_backtest",
        "capture",
        "--snapshot",
        str(snapshot),
        "--pairs",
        *PAIRS,
        "--proxy",
        "http://127.0.0.1:7890",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    (workspace / f"{PREFIX}_capture.log").write_text(result.stdout + result.stderr)
    (workspace / f"{PREFIX}_capture_command.json").write_text(json_text(command))
    if result.returncode != 0 or not snapshot.is_file():
        raise RuntimeError("BLOCKED: explicit genuine market acquisition failed")
    return snapshot


def lifecycle(userdir: Path, log: Path) -> dict:
    """Derive real train/model/feature/prediction counts, with no frozen counts."""
    metadata = sorted(userdir.rglob("*_metadata.json"))
    predictions = sorted(userdir.rglob("*_prediction.feather"))
    completed = re.findall(r"Done training ([A-Z0-9]+/USDT:USDT)", log.read_text())
    if (
        not metadata
        or len(completed) != len(metadata)
        or len(predictions) != len(metadata)
        or set(completed) != set(PAIRS)
    ):
        raise RuntimeError("Expanded fresh training/model/prediction lifecycle is incomplete")
    return {
        "completed_fit_count": len(completed),
        "metadata_count": len(metadata),
        "prediction_count": len(predictions),
        "fits_by_pair": {pair: completed.count(pair) for pair in PAIRS},
        "models": [
            {
                "file": str(path.relative_to(userdir)),
                "feature_count": len(json.loads(path.read_text())["training_features_list"]),
            }
            for path in metadata
        ],
    }


def execute(
    workspace: Path, output: Path, minimum: Path, coverage: Path, capture_attempt: int
) -> None:
    """Run fresh online reference then isolated offline comparison after both gates."""
    validate_gates(minimum, coverage)
    check_isolation()
    original_data = {
        item["path"]: item["sha256"]
        for pair in json.loads(coverage.read_text())["pairs"]
        if pair["pair"] in PAIRS
        for item in pair["files"]
    }
    protected = [ROOT / config for config in CONFIGS]
    protected.extend(ROOT.glob("*.py"))
    protected.extend((ROOT / "quant").rglob("*.py"))
    before = {str(path.relative_to(ROOT)): file_hash(path) for path in protected}
    (workspace / f"{PREFIX}_input_manifest.json").write_text(
        json_text(
            {"protected_sources": before, "history": original_data, "scope": "before_capture"}
        )
    )
    capture(workspace)
    artifacts = workspace / "runs"
    online, offline = artifacts / "online", artifacts / "offline"
    for userdir in (online, offline):
        userdir.mkdir(parents=True)
        if list(userdir.iterdir()):
            raise RuntimeError("Fresh extension userdir was not empty")
        (userdir / "results").mkdir()
    online_execution = online_run(workspace, online)
    finish_offline(
        workspace,
        output,
        minimum,
        coverage,
        online_execution,
        before,
        original_data,
        capture_attempt,
    )


def finish_offline(
    workspace: Path,
    output: Path,
    minimum: Path,
    coverage: Path,
    online_execution: dict,
    before: dict,
    original_data: dict,
    capture_attempt: int,
    source_guard_scope: str = "before_capture_through_offline_finish",
) -> None:
    """Finish a fresh attempt; retain the real online process evidence unchanged."""
    validate_gates(minimum, coverage)
    snapshot = workspace / f"{PREFIX}_snapshot.json"
    artifacts = workspace / "runs"
    online, offline = artifacts / "online", artifacts / "offline"
    validate_online_audit(online_execution["audit"], online, online_execution["exit_code"])
    recorded_audit = json.loads((workspace / f"{PREFIX}_online_network.json").read_text())
    if (
        recorded_audit != online_execution["audit"]
        or inspect_online_trace((workspace / f"{PREFIX}_online_network.strace").read_text())
        != online_execution["syscalls"]
    ):
        raise RuntimeError("Online evidence changed before offline continuation")
    if list(offline.rglob("*")) != [offline / "results"] or list((offline / "results").iterdir()):
        raise RuntimeError("Offline continuation requires an empty new userdir/results")
    lifecycle(online, workspace / f"{PREFIX}_online.log")
    offline_execution = audited_run(
        workspace,
        f"{PREFIX}_offline",
        "offline-backtest",
        ["backtesting", "--snapshot", str(snapshot), "--", *native_arguments(offline)],
    )
    require_zero_network(offline_execution)
    comparison = compare_runs(online, offline)
    (workspace / f"{PREFIX}_regression.json").write_text(json_text(comparison))
    if not comparison["passed"]:
        raise RuntimeError(f"Expanded native regression differs: {comparison['differences']}")
    training = {
        mode: lifecycle(userdir, workspace / f"{PREFIX}_{mode}.log")
        for mode, userdir in (("online", online), ("offline", offline))
    }
    changed = [
        name for name, sha in {**before, **original_data}.items() if file_hash(ROOT / name) != sha
    ]
    if changed:
        raise RuntimeError(f"Protected strategy/config/history changed during execution: {changed}")
    metadata = json.loads(snapshot.read_text())
    summary = {
        "status": "PASS",
        "executed_at": datetime.now(UTC).isoformat(),
        "versions": environment_versions(),
        "pairs": PAIRS,
        "timerange": TIMERANGE,
        "capture_attempt": capture_attempt,
        "minimum_gate": {"file": str(minimum.relative_to(ROOT)), "sha256": file_hash(minimum)},
        "coverage_gate": {"file": str(coverage.relative_to(ROOT)), "sha256": file_hash(coverage)},
        "snapshot": {
            "file": snapshot.name,
            "file_sha256": file_hash(snapshot),
            "payload_sha256": metadata["sha256"],
            "raw_sha256": metadata["raw_sha256"],
            "acquired_at": metadata["acquired_at"],
            "versions": metadata["versions"],
            "pairs": metadata["pairs"],
            "source": metadata["source"],
            "leverage_source": metadata["leverage_rules"]["source"],
            "leverage_sha256": metadata["leverage_rules"]["sha256"],
        },
        "execution": {"online": online_execution, "offline": offline_execution},
        "training": training,
        "fresh_userdirs_empty": True,
        "cache": "none",
        "protected_inputs_unchanged": True,
        "protected_source_check_scope": source_guard_scope,
        "protected_input_hashes": {**before, **original_data},
        "regression": comparison,
    }
    publish(workspace, output, PREFIX, summary, artifacts=artifacts)


def main(argv: list[str] | None = None) -> int:
    """Require completed minimum/data gates and refuse evidence replacement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--capture-attempt", type=int, choices=(1, 2), default=1, help="Explicit attempt index"
    )
    parser.add_argument(
        "--minimum-summary", type=Path, default=ROOT / "docs/acceptance/phase4_summary.json"
    )
    parser.add_argument(
        "--coverage", type=Path, default=ROOT / "docs/acceptance/phase3_extension_coverage.json"
    )
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    if any(
        not re.match(rf"{PREFIX}_attempt[0-9]+_", path.name)
        for path in args.output.glob(f"{PREFIX}_*")
    ):
        parser.error("Expanded evidence already exists; choose a fresh --output directory")
    workspace = Path(tempfile.mkdtemp(prefix="quant-phase4-extension-"))
    try:
        execute(
            workspace,
            args.output,
            args.minimum_summary.resolve(),
            args.coverage.resolve(),
            args.capture_attempt,
        )
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        summary = {
            "status": "BLOCKED" if str(error).startswith("BLOCKED:") else "FAIL",
            "executed_at": datetime.now(UTC).isoformat(),
            "versions": environment_versions(),
            "pairs": PAIRS,
            "timerange": TIMERANGE,
            "capture_attempt": args.capture_attempt,
            "error": str(error),
            "snapshot_captured": (workspace / f"{PREFIX}_snapshot.json").is_file(),
            "online_executed": (workspace / f"{PREFIX}_online_network.json").is_file(),
            "offline_executed": (workspace / f"{PREFIX}_offline_network.json").is_file(),
            "regression_executed": (workspace / f"{PREFIX}_regression.json").is_file(),
        }
        artifacts = workspace / "runs"
        publish(
            workspace,
            args.output,
            PREFIX,
            summary,
            artifacts=artifacts if artifacts.exists() else None,
        )
        print(json_text(summary))
        return 1
    print(json_text({"status": "PASS", "phase": PREFIX, "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
