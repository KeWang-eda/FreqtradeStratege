"""Independent, fail-closed training admission from executable evidence.

This is an engineering gate, never a profitability or live-trading certificate.
References: sklearn common pitfalls/data leakage, actual FreqAI DataKitchen
source, and the explicit UTC source/sample contracts in this repository.
"""

import argparse
import importlib.metadata
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

import pandas as pd

from quant_strategy.config import load_config
from quant_strategy.dataset import build_dataset
from quant_strategy.experiments.runner import _dataset_hash
from quant_strategy.infrastructure.experiment_store import (
    canonical_hash,
    environment_versions,
    file_hash,
    git_state,
    write_json,
)
from quant_strategy.market_data import load_ohlcv
from quant_strategy.market_data.contracts import audit_source
from quant_strategy.validation.native_boundaries import audit_native_boundaries

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"


def test_evidence(receipt_path: Path) -> dict:
    """Check exit, bound JUnit bytes, actual counts and executed test identities."""
    receipt = json.loads(receipt_path.read_text())
    junit = receipt_path.parent / receipt["junit"]
    if file_hash(junit) != receipt["junit_sha256"]:
        raise ValueError("Test JUnit fingerprint mismatch")
    root = ElementTree.parse(junit).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {
        key: sum(int(s.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    cases = list(root.iter("testcase"))
    if receipt["exit_code"] != 0 or counts["failures"] or counts["errors"]:
        raise ValueError("Required automated tests failed")
    if not counts["tests"] or counts["tests"] != len(cases):
        raise ValueError("JUnit case count is empty or inconsistent")
    executed = [c.get("name").split("[", 1)[0] for c in cases if c.find("skipped") is None]
    return {
        **counts,
        "executed_test_names": executed,
        "command": receipt["command"],
        "exit_code": receipt["exit_code"],
        "junit_sha256": receipt["junit_sha256"],
    }


def verify_data_evidence(directory: Path) -> dict:
    """Rebuild samples, verify all raw files and compare actual row identities."""
    report = json.loads((directory / "phase1_data.json").read_text())
    if report.get("phase") != 1 or report.get("status") != PASS:
        raise ValueError("Data quality evidence did not pass")
    for name, expected in report["artifacts"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or file_hash(path) != expected:
            raise ValueError(f"Data artifact fingerprint mismatch: {name}")
    sources = json.loads((directory / "source_audit.json").read_text())
    if len(sources) != sum(report["sources_by_status"].values()):
        raise ValueError("Source inventory count mismatch")
    for item in sources:
        if item.get("file_sha256") and file_hash(item["path"]) != item["file_sha256"]:
            raise ValueError("Raw data changed after audit")
        if item.get("file_sha256"):
            actual = audit_source(
                pd.read_feather(item["path"]), kind=item["kind"], timeframe=item["timeframe"]
            )
            if any(
                actual.get(field) != item.get(field)
                for field in (
                    "status",
                    "fingerprint",
                    "missing_rows",
                    "missing_intervals",
                    "issues",
                    "contract",
                )
            ):
                raise ValueError("Source contract results do not reproduce from raw data")
        if item["status"] != PASS and item.get("formal_use") != "quarantined":
            raise ValueError("Unverified source was not quarantined")
    # The original layered files must be unchanged, not merely recreated from a report.
    configs = report.get("config_inputs", [])
    if not configs:
        raise ValueError("Missing actual configuration fingerprints")
    for item in configs:
        if file_hash(item["path"]) != item["sha256"]:
            raise ValueError("Research configuration changed after audit")
    config = load_config([item["path"] for item in configs])
    if canonical_hash(asdict(config)) != report["config_sha256"]:
        raise ValueError("Resolved research configuration fingerprint mismatch")
    frames = {}
    for pair, item in report["input_files"].items():
        if file_hash(item["path"]) != item["sha256"]:
            raise ValueError("Research input changed after audit")
        frames[pair] = load_ohlcv(item["path"])
    dataset = build_dataset(frames, config)
    if _dataset_hash(dataset) != report["dataset_sha256"] or len(dataset.X) != report["samples"]:
        raise ValueError("Dataset content/schema or sample count is not reproducible")
    pd.testing.assert_frame_equal(
        dataset.metadata, pd.read_parquet(directory / "sample_metadata.parquet")
    )
    pd.testing.assert_frame_equal(
        dataset.exclusions, pd.read_parquet(directory / "sample_exclusions.parquet")
    )
    return {
        "status": PASS,
        "samples": len(dataset.X),
        "features": len(dataset.X.columns),
        "raw_files_verified": len(sources),
        "sources_by_status": report["sources_by_status"],
        "dataset_sha256": report["dataset_sha256"],
        "sample_boundary_violations": 0,
        "scope": report["availability_scope"],
        "quarantined_sources": sum(s["status"] != PASS for s in sources),
    }


def aggregate(phases: dict[str, dict]) -> dict:
    """A P0 failure always dominates missing dependent evidence; never grants admission."""
    states = [value["status"] for value in phases.values()]
    status = (
        FAIL
        if FAIL in states
        else BLOCKED
        if BLOCKED in states
        else "PARTIAL"
        if "PARTIAL" in states
        else PASS
    )
    if not phases:
        status = BLOCKED
    return {
        "status": status,
        "formal_out_of_sample_research_allowed": status == PASS
        and set(phases) == {str(i) for i in range(1, 7)},
        "model_effectiveness": BLOCKED,
        "live_trading_admission": BLOCKED,
        "scope_rule": "Partial engine/pair/window coverage cannot authorize full-project admission",
        "phases": phases,
    }


def evaluate(evidence: Path, test_run: Path, output: Path, requested: str = "all") -> dict:
    """Execute independent checks; later phases cannot bypass a failed earlier gate."""
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC).isoformat()
    phases = {}
    try:
        tests = test_evidence(test_run)
    except FileNotFoundError as error:
        tests = {"status": BLOCKED, "reason": str(error)}
    except (OSError, ValueError, KeyError, ElementTree.ParseError) as error:
        tests = {"status": FAIL, "reason": str(error)}
    for phase in range(1, 7):
        key = str(phase)
        if requested != "all" and phase > int(requested):
            break
        if phase > 1 and phases[str(phase - 1)]["status"] != PASS:
            phases[key] = {
                "status": BLOCKED,
                "reason": "Previous mandatory gate did not pass",
                "not_executed": True,
                "depends_on": str(phase - 1),
            }
            continue
        try:
            if tests.get("status") in {FAIL, BLOCKED}:
                phases[key] = {
                    "status": tests["status"],
                    "reason": "Automated test evidence failed",
                    "tests": tests,
                }
            elif phase == 1:
                if tests["skipped"]:
                    raise FileNotFoundError(
                        "Suite has skipped tests; complete gate coverage is not established"
                    )
                required = {
                    "test_dataset_rejects_invented_or_duplicated_provenance",
                    "test_gap_excludes_labels_crossing_missing_bar_and_restarts_warmup",
                    "test_file_change_during_read_fails_before_dataset",
                    "test_same_real_data_rebuilds_identical_schema_samples_and_exclusions",
                }
                if required - set(tests["executed_test_names"]):
                    raise FileNotFoundError(
                        "Required data fault-injection/integration tests were not executed"
                    )
                phases[key] = verify_data_evidence(evidence / "source_sample_audit")
            elif phase == 2:
                from quant_strategy.validation.feature_contracts import (
                    audit_causality,
                    build_feature_contracts,
                )

                required = {
                    "test_injected_known_schema_leak_is_detected_by_values_not_registry",
                    "test_test_distribution_cannot_change_fit_parameters",
                    "test_early_stopping_uses_inner_validation_only",
                    "test_actual_native_split_exposes_overlapping_training_labels",
                }
                if required - set(tests["executed_test_names"]):
                    raise FileNotFoundError(
                        "Required leakage injection/preprocessing/native boundary tests were not executed"
                    )

                config = load_config(["configs/base.yaml", "configs/environment/local.yaml"])
                native_config = json.loads(Path("config.json").read_text())
                audits, native = {}, {}
                for pair, path in config.data.items():
                    raw = load_ohlcv(path).iloc[-600:].reset_index(drop=True)
                    audits[pair] = audit_causality(raw, config)
                    native[pair] = audit_native_boundaries(native_config, raw)
                columns = json.loads(
                    (evidence / "source_sample_audit/phase1_data.json").read_text()
                )["features"]
                contracts = build_feature_contracts(config, columns)
                write_json(output / "feature_contracts.json", contracts)
                write_json(output / "feature_causality.json", audits)
                write_json(output / "native_boundaries.json", native)
                failed = any(
                    r["status"] == FAIL for r in [*audits.values(), *native.values(), contracts]
                )
                blocked = any(
                    r["status"] == BLOCKED for r in [*audits.values(), *native.values(), contracts]
                )
                phases[key] = {
                    "status": FAIL if failed else BLOCKED if blocked else PASS,
                    "research_causality": audits,
                    "native_boundaries": native,
                    "reason": "Native training labels overlap early-stopping validation; production trainer preserved by user decision"
                    if failed
                    else "No detected violations",
                }
            else:
                phases[key] = {
                    "status": BLOCKED,
                    "not_executed": True,
                    "reason": "Required stage implementation/real execution receipt is not available; no inherited historical pass",
                }
        except FileNotFoundError as error:
            phases[key] = {"status": BLOCKED, "reason": str(error)}
        except (OSError, ValueError, KeyError, AssertionError, TypeError) as error:
            phases[key] = {"status": FAIL, "reason": str(error)}
    if requested in {"all", "6"}:
        preceding = aggregate({k: v for k, v in phases.items() if k != "6"})
        phases["6"] = {
            "status": preceding["status"],
            "independent_aggregation_executed": True,
            "reason": "P0 failure denies admission"
            if preceding["status"] == FAIL
            else "All mandatory evidence must be complete",
        }
    report = aggregate(phases)
    report.update(
        schema_version=1,
        executed_at=started,
        git=git_state(),
        environment=environment_versions(),
        ccxt_version=importlib.metadata.version("ccxt"),
        tests=tests,
        thresholds={
            "invalid_eligible_samples": 0,
            "label_boundary_violations": 0,
            "unexplained_preprocessing_fit_overreach": 0,
            "feature_future_difference": "exact equality including matching missing masks",
            "missing_rate": "No global zero rule; detect, record, quarantine",
            "profitability": "No business threshold declared; no effectiveness admission",
        },
    )
    report["output_sha256"] = {p.name: file_hash(p) for p in output.iterdir() if p.is_file()}
    write_json(output / "readiness.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--test-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["all", "1", "2", "3", "4", "5", "6"], default="all")
    args = parser.parse_args(argv)
    report = evaluate(args.evidence, args.test_run, args.output, args.phase)
    print(
        json.dumps(
            {
                "status": report["status"],
                "phases": {k: v["status"] for k, v in report["phases"].items()},
                "formal_out_of_sample_research_allowed": report[
                    "formal_out_of_sample_research_allowed"
                ],
            }
        )
    )
    return 0 if report["status"] == PASS else 1 if report["status"] == FAIL else 2


if __name__ == "__main__":
    raise SystemExit(main())
