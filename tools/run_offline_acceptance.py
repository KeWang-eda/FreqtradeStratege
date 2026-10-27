"""Reproduce real Phase 4/5 acceptance; publish path-redacted evidence only.

References: Linux unshare(1) network namespaces; strace(1) ``-f -e trace=network``;
Python sys.addaudithook/socket auditing; native Backtesting(config, exchange=...).
No networking policy, framework class or system configuration is changed here.
The raw regression comparison always precedes publication/redaction.
"""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from quant.infrastructure.experiment_store import environment_versions, file_hash
from tools.verify_freqtrade_regression import compare_runs

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baseline/acceptance"
PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
TIMERANGE = "20250101-20250115"
NAMESPACE = ["unshare", "--user", "--map-root-user", "--net"]


def json_text(value: object) -> str:
    """Use strict portable JSON for evidence; never serialize non-finite values."""
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def check_isolation() -> None:
    """Fail rather than substitute Python interception for unavailable OS isolation."""
    if any(not shutil.which(name) for name in ("unshare", "strace")):
        raise RuntimeError("BLOCKED: OS network acceptance requires unshare and strace")
    result = subprocess.run([*NAMESPACE, "true"], capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError("BLOCKED: kernel user/network namespace is unavailable")


def inspect_trace(text: str, expected_exit: int = 0) -> dict:
    """Reject every connect/send syscall, including unsuccessful and native C calls.

    Local socket creation and aiohttp's ::1 bind capability probe are recorded.
    They do not contact another process or send data. strace follows all children.
    """
    attempted = [
        line
        for line in text.splitlines()
        if re.search(r"\b(connect|sendto|sendmsg|sendmmsg)\(", line)
    ]
    # tarfile.gettarinfo calls pwd/grp for local archive ownership metadata.
    # glibc tries its local name-service cache first. An absent Unix socket
    # cannot transmit a DNS query or contact a server; retain it separately.
    local_nscd = [
        line
        for line in attempted
        if re.search(r'connect\(.*sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"', line)
        and "= -1 ENOENT" in line
    ]
    operations = [line for line in attempted if line not in local_nscd]
    if operations:
        raise RuntimeError(f"Unexpected connect/send syscalls: {operations}")
    if f"+++ exited with {expected_exit} +++" not in text:
        raise RuntimeError("strace is missing the expected process completion evidence")
    return {
        "connect_or_send_count": len(operations),
        "failed_local_nscd_probes": len(local_nscd),
        "socket_creation_count": len(re.findall(r"\bsocket\(", text)),
        "bind_count": len(re.findall(r"\bbind\(", text)),
        "scope": "strace -f captures network syscalls of traced process and children",
    }


def native_options(userdir: Path) -> list[str]:
    """Match the frozen online BTC/ETH window; explicitly use fresh local caches."""
    return [
        "-c",
        "config.json",
        "-c",
        "configs/backtest-local.json",
        "-c",
        "configs/environment/freqtrade-mihomo.json",
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


def audited_run(workspace: Path, name: str, component: str, arguments: list[str]) -> dict:
    """Execute under all three observation/isolation layers, retaining raw evidence."""
    report = workspace / f"{name}_network.json"
    trace = workspace / f"{name}_network.strace"
    command = [
        *NAMESPACE,
        "strace",
        "-f",
        "-e",
        "trace=network",
        "-o",
        str(trace),
        sys.executable,
        str(ROOT / "tools/audit_local_network.py"),
        "--policy",
        "deny-all",
        "--report",
        str(report),
        component,
        *arguments,
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
    if not report.is_file():
        raise RuntimeError(f"{name}: audit report was not produced (exit {result.returncode})")
    evidence = json.loads(report.read_text())
    if result.returncode != evidence.get("exit_code") or not evidence.get("completed"):
        raise RuntimeError(f"{name}: process/auditor outcome disagrees or execution incomplete")
    return {
        "exit_code": result.returncode,
        "audit": evidence,
        "syscalls": inspect_trace(trace.read_text(), result.returncode),
        "command": command,
    }


def require_zero_network(result: dict, *, research: bool = False) -> None:
    """Validate completed execution and every recorded event, not only exit status."""
    audit = result["audit"]
    if (
        result["exit_code"] != 0
        or audit["denied_operations"] != 0
        or audit["http_requests"]
        or audit["socket_events"]
        or any(not event["allowed"] for event in audit["process_events"])
    ):
        raise RuntimeError("A completed zero-network run was required")
    if research and (audit["freqtrade_imported"] or audit["ccxt_imported"]):
        raise RuntimeError("Research unexpectedly imported Freqtrade/CCXT")


def validate_coverage_scope(coverage: dict) -> None:
    """Reject a true gate for another window/pair scope before any execution."""
    scope = coverage.get("minimum_scope", {})
    if (
        coverage.get("minimum_scope_ready") is not True
        or scope.get("pairs") != PAIRS
        or scope.get("timerange") != TIMERANGE
        or coverage.get("requirements", {}).get("timerange") != TIMERANGE
        or scope.get("raw_data_ready") is not True
        or scope.get("metadata_scope_ready") is not True
    ):
        raise RuntimeError(
            "BLOCKED: Phase 3 must approve the exact BTC/ETH date/data/metadata scope"
        )


def replacements(workspace: Path, reference: Path | None = None) -> list[tuple[str, str]]:
    """Map only filesystem roots; never mask numeric trading/model differences."""
    mapping = {str(workspace): "/RUN", str(ROOT): "/REPO", sys.prefix: "/PYTHON_ENV"}
    if reference is not None:
        for path in reference.rglob("*_metadata.json"):
            metadata = json.loads(path.read_text())
            relative = path.relative_to(reference).parent
            data_path = Path(metadata["data_path"])
            original_root = data_path.parents[len(relative.parts) - 1]
            mapping[str(original_root)] = "/REFERENCE"
    mapping[str(Path.home())] = "/LOCAL_HOME"
    return sorted(mapping.items(), key=lambda pair: -len(pair[0]))


def redact_text(text: str, mapping: list[tuple[str, str]]) -> str:
    """Redact private roots, retaining every other byte and trading field."""
    for original, token in mapping:
        text = text.replace(original, token)
    if "/home/" in text:
        raise RuntimeError("Unmapped private path in published evidence")
    return text


def publish_bytes(path: Path, mapping: list[tuple[str, str]]) -> bytes:
    """Preserve binary data; redact textual config members of native result ZIPs."""
    if path.suffix == ".zip":
        buffer = io.BytesIO()
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(buffer, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename.endswith((".json", ".py")):
                    content = redact_text(content.decode(), mapping).encode()
                target.writestr(info, content)
        return buffer.getvalue()
    if path.suffix in {".json", ".log", ".strace", ".yaml", ".txt"}:
        return redact_text(path.read_text(), mapping).encode()
    return path.read_bytes()


def publish(
    workspace: Path,
    output: Path,
    phase: str,
    summary: dict,
    reference: Path | None = None,
    artifacts: Path | None = None,
) -> None:
    """Keep raw files local; archive verified evidence with an explicit hash ledger."""
    mapping = replacements(workspace, reference)
    ledger = []
    for path in sorted(workspace.glob(f"{phase}*")):
        if not path.is_file():
            continue
        data = publish_bytes(path, mapping)
        target = output / path.name
        target.write_bytes(data)
        ledger.append(
            {
                "file": target.name,
                "raw_sha256": file_hash(path),
                "published_sha256": hashlib.sha256(data).hexdigest(),
                "path_redacted": data != path.read_bytes(),
            }
        )
    if artifacts is not None:
        ledger.extend(publish_archive(artifacts, output / f"{phase}_artifacts.tar.gz", mapping))
    if reference is not None:
        ledger.extend(
            publish_archive(reference, output / f"{phase}_reference_artifacts.tar.gz", mapping)
        )
    summary["publication"] = {
        "raw_comparison_precedes_redaction": True,
        "redaction_scope": "Only local filesystem roots in UTF-8 logs/JSON/ZIP config; binary signals and predictions unchanged",
        "raw_files": "Retained only in local ephemeral workspace; never required for rerunning acceptance",
        "hash_ledger": ledger,
    }
    (output / f"{phase}_summary.json").write_text(redact_text(json_text(summary), mapping))


def publish_archive(source: Path, target: Path, mapping: list[tuple[str, str]]) -> list[dict]:
    """Apply identical root redaction to both sides for durable strict replay."""
    ledger = []
    with tarfile.open(target, "w:gz") as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.suffix not in {
                ".zip",
                ".json",
                ".feather",
                ".parquet",
                ".yaml",
            }:
                continue
            data = publish_bytes(path, mapping)
            relative = str(path.relative_to(source))
            info = tarfile.TarInfo(relative)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
            ledger.append(
                {
                    "file": target.name + ":" + relative,
                    "raw_sha256": file_hash(path),
                    "published_sha256": hashlib.sha256(data).hexdigest(),
                    "path_redacted": data != path.read_bytes(),
                }
            )
    ledger.append({"file": target.name, "published_sha256": file_hash(target)})
    return ledger


def phase4(workspace: Path, output: Path, gate: Path) -> None:
    """Native backtest with genuine data, fresh models, OS isolation and regression."""
    coverage = json.loads(gate.read_text())
    validate_coverage_scope(coverage)
    for item in coverage["configs"]:
        if file_hash(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError("BLOCKED: Phase 3 configuration changed since coverage audit")
    snapshot = BASELINE / "binance-usdt-market-snapshot.json"
    if file_hash(snapshot) != coverage["snapshot"]["file_sha256"]:
        raise RuntimeError("BLOCKED: Snapshot changed since Phase 3 coverage audit")
    for pair in coverage["pairs"]:
        if pair["pair"] in PAIRS:
            if pair["offline_backtest_ready"] is not True:
                raise RuntimeError("BLOCKED: Per-pair coverage contradicts the minimum gate")
            for item in pair["files"]:
                if file_hash(ROOT / item["path"]) != item["sha256"]:
                    raise RuntimeError(
                        "BLOCKED: Local history changed since Phase 3 coverage audit"
                    )
    reference = workspace / "reference"
    reference.mkdir()
    original = BASELINE / "native-online-reference.tar.gz"
    with tarfile.open(original) as archive:
        archive.extractall(reference, filter="data")
    userdir = workspace / "offline"
    userdir.mkdir()
    if list(userdir.iterdir()):
        raise RuntimeError("New offline userdir was unexpectedly nonempty")
    (userdir / "results").mkdir()
    args = [
        "backtesting",
        "--snapshot",
        str(snapshot),
        # Frozen acceptance snapshot; never the recommended production expiry policy.
        "--snapshot-max-age-days",
        "36500",
        "--",
        *native_options(userdir),
    ]
    execution = audited_run(workspace, "phase4_backtest", "offline-backtest", args)
    require_zero_network(execution)
    regression = compare_runs(reference, userdir)
    (workspace / "phase4_regression.json").write_text(json_text(regression))
    if not regression["passed"]:
        raise RuntimeError(f"Native regression failed: {regression['differences']}")
    log = (workspace / "phase4_backtest.log").read_text()
    metadata = list(userdir.rglob("*_metadata.json"))
    predictions = list(userdir.rglob("*_prediction.feather"))
    fit_count = len(re.findall(r"Done training (BTC|ETH)/USDT:USDT", log))
    feature_counts = [
        len(json.loads(path.read_text())["training_features_list"]) for path in metadata
    ]
    reference_count = len(list(reference.rglob("*_metadata.json")))
    if not metadata or fit_count != len(metadata) or len(predictions) != len(metadata):
        raise RuntimeError("Fresh fit/prediction/metadata lifecycle counts disagree")
    if len(metadata) != reference_count or "Offline snapshot" not in log:
        raise RuntimeError("Training lifecycle/reference scope or explicit offline log is missing")
    online_audit = json.loads((BASELINE / "network-after.json").read_text())
    if online_audit["exit_code"] != 0 or online_audit["http_requests"] != [
        {
            "method": "GET",
            "host": "fapi.binance.com",
            "path": "/fapi/v1/exchangeInfo",
            "allowed": True,
        }
    ]:
        raise RuntimeError("Frozen online reference provenance no longer matches its audit")
    summary = {
        "status": "PASS",
        "executed_at": datetime.now(UTC).isoformat(),
        "versions": environment_versions(),
        "pairs": PAIRS,
        "timerange": TIMERANGE,
        "phase3_gate": {"file": str(gate.relative_to(ROOT)), "sha256": file_hash(gate)},
        "execution": execution,
        "new_userdir_empty": True,
        "cache": "none",
        "training": {
            "completed_fit_count": fit_count,
            "metadata_count": len(metadata),
            "prediction_count": len(predictions),
            "feature_counts": feature_counts,
        },
        "reference": {
            "file": str(original.relative_to(ROOT)),
            "sha256": file_hash(original),
            "provenance": "Historical real online run; no fresh online run claimed",
        },
        "regression": regression,
    }
    publish(workspace, output, "phase4", summary, reference=reference, artifacts=userdir)


def phase5(workspace: Path, output: Path) -> None:
    """Real research and expected native startup failure under OS network isolation."""
    config = ["-c", "configs/base.yaml", "-c", "configs/environment/local.yaml"]
    executions = {}
    for command in ("validate", "dataset-build"):
        name = "phase5_" + command.replace("-", "_")
        executions[name] = audited_run(workspace, name, "research", [command, *config])
        require_zero_network(executions[name], research=True)
    experiments = workspace / "experiments"
    for estimator in ("ridge", "xgboost"):
        name = "phase5_" + estimator
        arguments = [
            "run",
            *config,
            "-c",
            f"configs/estimators/{estimator}.yaml",
            "--output",
            str(experiments),
            "--experiment-id",
            estimator,
        ]
        executions[name] = audited_run(workspace, name, "research", arguments)
        require_zero_network(executions[name], research=True)
        manifest = json.loads((experiments / estimator / "manifest.json").read_text())
        folds = json.loads((experiments / estimator / "folds.json").read_text())
        if manifest["status"] != "complete" or len(folds) != 3:
            raise RuntimeError("Research training/CV did not complete the configured folds")
    arguments = ["compare", str(experiments / "ridge"), str(experiments / "xgboost")]
    executions["phase5_compare"] = audited_run(workspace, "phase5_compare", "research", arguments)
    require_zero_network(executions["phase5_compare"], research=True)
    compared = json.loads((workspace / "phase5_compare.log").read_text())
    if len(compared) != 2 or any(len(result["folds"]) != 3 for result in compared):
        raise RuntimeError("Research comparison omitted experiments/folds")
    native_userdir = workspace / "native"
    (native_userdir / "results").mkdir(parents=True)
    native = audited_run(
        workspace, "phase5_native", "freqtrade", ["backtesting", *native_options(native_userdir)]
    )
    attempted = native["audit"]["http_requests"]
    if (
        native["exit_code"] == 0
        or not attempted
        or any(
            request
            != {
                "method": "GET",
                "host": "fapi.binance.com",
                "path": "/fapi/v1/exchangeInfo",
                "allowed": False,
            }
            for request in attempted
        )
    ):
        raise RuntimeError("Ordinary backtesting did not preserve native market initialization")
    if list(native_userdir.rglob("*.zip")) or native["audit"]["socket_events"]:
        raise RuntimeError("Denied native startup unexpectedly traded or reached sockets")
    executions["phase5_native"] = native
    samples = json.loads((workspace / "phase5_dataset_build.log").read_text())
    research_details = {}
    for estimator in ("ridge", "xgboost"):
        directory = experiments / estimator
        manifest = json.loads((directory / "manifest.json").read_text())
        import pandas as pd

        research_details[estimator] = {
            "status": manifest["status"],
            "input_files": manifest["input_files"],
            "dataset_sha256": manifest["dataset_sha256"],
            "input_data_sha256": manifest["input_data_sha256"],
            "folds_sha256": manifest["folds_sha256"],
            "prediction_rows": len(pd.read_parquet(directory / "predictions.parquet")),
            "fold_count": len(json.loads((directory / "folds.json").read_text())),
            "metrics": json.loads((directory / "metrics_prediction.json").read_text()),
        }
    summary = {
        "status": "PASS",
        "executed_at": datetime.now(UTC).isoformat(),
        "versions": environment_versions(),
        "executions": executions,
        "dataset": samples,
        "research": research_details,
        "native_network_attempts_expected_and_denied": len(attempted),
        "live_accounts_or_orders": "Not accessed; native client/credential paths verified only with boundary tests",
    }
    publish(workspace, output, "phase5", summary, artifacts=experiments)


def main(argv: list[str] | None = None) -> int:
    """Use the installed Freqtrade Python; refuse to overwrite durable evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("phase4", "phase5"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--coverage", type=Path, default=ROOT / "docs/acceptance/phase3_data_coverage.json"
    )
    args = parser.parse_args(argv)
    args.coverage = args.coverage.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / f"{args.phase}_summary.json").exists():
        parser.error("Evidence prefix already exists; choose a fresh --output directory")
    workspace = Path(tempfile.mkdtemp(prefix=f"quant-{args.phase}-acceptance-"))
    try:
        check_isolation()
        if args.phase == "phase4":
            phase4(workspace, args.output, args.coverage)
        else:
            phase5(workspace, args.output)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        summary = {
            "status": "BLOCKED" if str(exc).startswith("BLOCKED:") else "FAIL",
            "executed_at": datetime.now(UTC).isoformat(),
            "error": str(exc),
        }
        publish(workspace, args.output, args.phase, summary)
        print(json_text(summary))
        return 1
    print(json_text({"status": "PASS", "phase": args.phase, "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
