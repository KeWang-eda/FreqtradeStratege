"""Independent, fail-closed training admission from executable evidence.

This is an engineering gate, never a profitability or live-trading certificate.
References: sklearn common pitfalls/data leakage, actual FreqAI DataKitchen
source, and the explicit UTC source/sample contracts in this repository.
"""

import argparse
import json
import shutil
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
    file_hash,
    git_state,
    write_json,
)
from quant_strategy.market_data import load_ohlcv
from quant_strategy.market_data.contracts import audit_source
from quant_strategy.validation.admission import (
    IMPLEMENTED_FORMAL_GATES,
    bound_artifact,
    new_receipt_context,
    read_evidence_json,
    verify_test_execution,
)

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"

REQUIRED_DATA_NODEIDS = {
    "tests/unit/test_sample_governance.py::test_dataset_rejects_invented_or_duplicated_provenance",
    "tests/unit/test_sample_governance.py::test_gap_excludes_labels_crossing_missing_bar_and_restarts_warmup",
    "tests/integration/test_dataset_governance.py::test_file_change_during_read_fails_before_dataset",
    "tests/integration/test_dataset_governance.py::test_same_real_data_rebuilds_identical_schema_samples_and_exclusions",
}
REQUIRED_LEAKAGE_NODEIDS = {
    "tests/leakage/test_information_boundaries.py::test_test_distribution_cannot_change_fit_parameters",
    "tests/leakage/test_information_boundaries.py::test_early_stopping_uses_inner_validation_only",
    "tests/leakage/test_native_feature_causality.py::test_actual_btc_eth_bnb_files_full_native_features_are_causal",
    "tests/leakage/test_native_feature_causality.py::test_actual_pipeline_known_schema_future_faults_are_detected[future_shift]",
    "tests/leakage/test_native_feature_causality.py::test_actual_pipeline_known_schema_future_faults_are_detected[correlated_future]",
    "tests/leakage/test_native_feature_causality.py::test_future_global_dynamic_ranking_is_detected",
    "tests/unit/test_native_isolation.py::test_equality_greater_and_less_than_boundary",
    "tests/unit/test_native_isolation.py::test_weight_and_metadata_alignment",
    "tests/unit/test_native_isolation.py::test_post_purge_faults_are_not_repaired_into_a_pass[boundary]",
    "tests/unit/test_native_isolation.py::test_post_purge_faults_are_not_repaired_into_a_pass[weights]",
    "tests/unit/test_native_isolation.py::test_cache_cannot_reuse_predictions_after_source_file_change",
}


def test_evidence(receipt_path: Path) -> dict:
    """Check exit, bound JUnit bytes, actual counts and executed test identities."""
    return verify_test_execution(receipt_path)


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


def _native_feature_scope_status(status: str, *, source_errors: list, all_pairs: bool) -> str:
    """Apply source availability and universe scope to recomputed feature status."""
    if status == FAIL:
        return FAIL
    if source_errors:
        return BLOCKED
    if status == PASS and not all_pairs:
        return "PARTIAL"
    return status


def verify_native_feature_evidence(directory: Path) -> dict:
    """Recompute real expanded schemas and causal tests, not a saved PASS flag."""
    from freqtrade.configuration.load_config import load_from_files

    from quant_strategy.validation.native_features import audit_native_features

    saved = read_evidence_json(directory / "native_features.json")
    if saved.get("run_id") != directory.parent.name:
        raise ValueError("Native feature evidence run_id differs from its execution directory")
    if saved.get("input_integrity", {}).get("unchanged") is not True:
        raise ValueError("Native feature audit inputs/code were not unchanged throughout execution")
    root = Path(__file__).resolve().parents[1]
    candidates = [root / "config.json", *(root / "configs").rglob("*.json")]
    configs = []
    for index, item in enumerate(saved["config_files"]):
        matches = [
            path
            for path in candidates
            if path.name == item["filename"] and file_hash(path) == item["sha256"]
        ]
        if len(matches) != 1:
            raise ValueError("Native feature configuration cannot be uniquely reproduced")
        relative = str(matches[0].relative_to(root))
        if saved.get("config_paths") and saved["config_paths"][index] != relative:
            raise ValueError("Native feature configuration path/order mismatch")
        configs.append(relative)
    if not configs:
        raise ValueError("Missing native feature configuration fingerprints")
    config = load_from_files(configs)
    window = saved["requested_common_window"]
    frames = {}
    for item in saved["input_files"]:
        path = Path(config["datadir"]) / "futures" / item["filename"]
        if file_hash(path) != item["sha256"]:
            raise ValueError("Native feature source changed")
        frame = pd.read_feather(path)
        if file_hash(path) != item["sha256"]:
            raise ValueError("Native feature source changed during independent read")
        frames[item["pair"], item["timeframe"]] = frame.loc[
            frame.date.between(pd.Timestamp(window["start"]), pd.Timestamp(window["end"]))
        ].reset_index(drop=True)
    bars = window["base_bars"]
    actual = audit_native_features(
        config,
        frames,
        pairs=saved["audited_pairs"],
        cut_points=saved.get("cut_points", [bars // 2, bars - 20]),
    )
    for field in (
        "pairs",
        "differences",
        "configuration_sha256",
        "audited_pairs",
        "configured_pair_count",
        "all_configured_pairs_audited",
        "versions",
        "label_contract",
        "tolerance",
    ):
        if actual.get(field) != saved.get(field):
            raise ValueError(f"Native feature audit cannot reproduce: {field}")
    for item in saved.get("populated_artifacts", []):
        bound_artifact(directory, {"path": item["filename"], "sha256": item["sha256"]})
    actual["status"] = _native_feature_scope_status(
        actual["status"],
        source_errors=saved.get("source_errors", []),
        all_pairs=actual.get("all_configured_pairs_audited", False),
    )
    if saved.get("source_errors"):
        actual["source_errors"] = saved["source_errors"]
    if actual["status"] == "PARTIAL":
        actual["reason"] = "Only a subset of the actual production universe was audited"
    actual["run_id"] = saved["run_id"]
    return actual


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
    if (
        status == PASS
        and set(phases) == {str(i) for i in range(1, 7)}
        and set(phases) - IMPLEMENTED_FORMAL_GATES
    ):
        status = BLOCKED
    return {
        "status": status,
        "formal_out_of_sample_research_allowed": status == PASS
        and set(phases) == {str(i) for i in range(1, 7)}
        and set(phases) <= IMPLEMENTED_FORMAL_GATES,
        "implemented_formal_gate_validators": sorted(IMPLEMENTED_FORMAL_GATES),
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
                if REQUIRED_DATA_NODEIDS - set(tests["executed_test_nodeids"]):
                    raise FileNotFoundError(
                        "Required data fault-injection/integration tests were not executed"
                    )
                phases[key] = verify_data_evidence(evidence / "source_sample_audit")
            elif phase == 2:
                from quant_strategy.validation.feature_contracts import (
                    audit_causality,
                    build_feature_contracts,
                )

                if REQUIRED_LEAKAGE_NODEIDS - set(tests["executed_test_nodeids"]):
                    raise FileNotFoundError(
                        "Required leakage injection/preprocessing/native boundary tests were not executed"
                    )

                config = load_config(["configs/base.yaml", "configs/environment/local.yaml"])
                audits = {}
                for pair, path in config.data.items():
                    raw = load_ohlcv(path).iloc[-600:].reset_index(drop=True)
                    audits[pair] = audit_causality(raw, config)
                columns = json.loads(
                    (evidence / "source_sample_audit/phase1_data.json").read_text()
                )["features"]
                contracts = build_feature_contracts(config, columns)
                write_json(output / "feature_contracts.json", contracts)
                write_json(output / "feature_causality.json", audits)
                native_directory = evidence / "native_training"
                if not (native_directory / "training_run.json").is_file():
                    raise FileNotFoundError("Real corrected native training evidence is missing")
                from tools.verify_native_training_acceptance import (
                    verify_native_training_acceptance,
                )

                native = verify_native_training_acceptance(native_directory)
                if native.get("run_id") != tests["run_id"]:
                    raise ValueError("Native training and test evidence belong to different runs")
                native_features = verify_native_feature_evidence(evidence / "native_features")
                if native_features["run_id"] != tests["run_id"]:
                    raise ValueError("Native feature and test evidence belong to different runs")
                native_config = json.loads(Path("config.json").read_text())
                trained_pairs = [value["pair"] for value in native.get("pairs", [])]
                configured_pairs = native_config["exchange"]["pair_whitelist"]
                write_json(output / "native_training_independent.json", native)
                write_json(output / "native_features_independent.json", native_features)
                components = [*audits.values(), contracts, native, native_features]
                states = [r["status"] for r in components]
                if trained_pairs != configured_pairs and all(value == PASS for value in states):
                    states.append("PARTIAL")
                phases[key] = {
                    "status": FAIL
                    if FAIL in states
                    else BLOCKED
                    if BLOCKED in states
                    else "PARTIAL"
                    if "PARTIAL" in states
                    else PASS,
                    "research_causality": audits,
                    "native_training": native,
                    "native_training_scope": {
                        "trained_pairs": trained_pairs,
                        "configured_pair_count": len(configured_pairs),
                        "all_configured_pairs_trained": trained_pairs == configured_pairs,
                    },
                    "required_data_blockers": native.get("funding", {}),
                    "native_features": native_features,
                    "reason": "Corrected production artifacts and causal features are independently recomputed; scope/data blockers remain explicit",
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
        **new_receipt_context(tests.get("run_id", output.name)),
        executed_at=started,
        git=git_state(),
        tests=tests,
        required_test_nodeids=sorted(REQUIRED_DATA_NODEIDS | REQUIRED_LEAKAGE_NODEIDS),
        thresholds={
            "invalid_eligible_samples": 0,
            "label_boundary_violations": 0,
            "unexplained_preprocessing_fit_overreach": 0,
            "feature_future_difference": "exact equality including matching missing masks",
            "missing_rate": "No global zero rule; detect, record, quarantine",
            "profitability": "No business threshold declared; no effectiveness admission",
        },
    )
    if tests.get("run_id"):
        receipt = read_evidence_json(test_run)
        junit = bound_artifact(
            test_run.parent,
            {
                "path": receipt["junit"],
                "sha256": receipt["junit_sha256"],
            },
        )
        shutil.copyfile(junit, output / "test_results.xml")
        receipt["junit"] = "test_results.xml"
        write_json(output / "test_run.json", receipt)
        report["test_receipt"] = {
            "path": "test_run.json",
            "sha256": file_hash(output / "test_run.json"),
        }
    data_path = evidence / "source_sample_audit/phase1_data.json"
    if data_path.is_file():
        data_report = read_evidence_json(data_path)
        for field in ("config_sha256", "config_inputs", "input_files", "dataset_sha256"):
            report[field] = data_report.get(field)
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
    try:
        report = evaluate(args.evidence, args.test_run, args.output, args.phase)
    except (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError) as error:
        print(json.dumps({"status": FAIL, "error": type(error).__name__, "reason": str(error)}))
        return 2
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
