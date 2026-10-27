"""Isolated preparation and real native development folds for a frozen task.

Only the early, predeclared historical prefix is materialized for training.
The full-history plan contains identity/time metadata, not holdout targets.
Formal stage registration is deliberately not changed by these diagnostics.
"""

import gzip
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from quant.errors import DataContractError
from quant.infrastructure.experiment_store import (
    canonical_hash,
    environment_versions,
    file_hash,
    write_json,
)
from quant.market_data.contracts import frame_fingerprint
from quant.research.contract import (
    ROOT,
    contract_identity,
    resolve_controlled_configuration,
)
from quant.research.costs import build_cost_contract, validate_cost_scenario
from quant.research.evaluation import BASELINE_DEFINITION, METRIC_DEFINITION
from quant.research.governance import audit_three_pair_sources
from quant.research.native_panel import (
    identity_metadata,
    materialize_native_prefix,
    probe_metadata,
)
from quant.research.splits import build_split_plan, verify_split_plan
from quant.validation.admission import (
    current_source_hashes,
    new_receipt_context,
    read_evidence_json,
    verify_complete_test_execution,
    verify_receipt_context,
)

BASE_ARTIFACTS = frozenset(
    {
        "semantic_contract.json",
        "source_audit.json",
        "cost_contract.json",
        "full_identity_metadata.parquet",
        "development_prefix_metadata.parquet",
        "full_identity_plan.json.gz",
        "development_prefix_plan.json.gz",
        "full_split_verification.json",
        "prefix_split_verification.json",
        "holdout_access.json",
        "native_prefix_audit.json",
        "execution_contract.json",
        "network.json",
    }
)
TRAINING_ARTIFACTS = frozenset(
    {
        "predictions.parquet",
        "expected_predictions.parquet",
        "prediction_metrics.json",
        "data_access.jsonl",
        "development_training_manifest.json",
    }
)


def validate_network_audit(network: dict) -> None:
    """Recount events; a manually reset counter cannot conceal a request."""
    if (
        network.get("policy") != "deny-all"
        or network.get("completed") is not True
        or type(network.get("exit_code")) is not int
        or network["exit_code"] != 0
        or network.get("http_requests") != []
        or network.get("socket_events") != []
        or not isinstance(network.get("process_events"), list)
    ):
        raise DataContractError(
            "Controlled network audit is missing, incomplete or has network events"
        )
    for item in network["process_events"]:
        if (
            not isinstance(item, dict)
            or item.get("allowed") is not True
            or item.get("event") != "subprocess.Popen"
            or Path(str(item.get("executable"))).resolve()
            != Path(shutil.which("git") or "/missing-git").resolve()
            or item.get("scope") != "fixed local Git provenance query"
        ):
            raise DataContractError("Controlled audit contains an unaudited child operation")
    denied = sum(
        item.get("allowed") is not True
        for kind in ("http_requests", "socket_events", "process_events")
        for item in network[kind]
    )
    if (
        denied
        or type(network.get("denied_operations")) is not int
        or network["denied_operations"] != denied
    ):
        raise DataContractError("Controlled network audit denied-operation counter disagrees")


def validate_execution_envelope(evidence: Path, run: dict) -> None:
    """Check exact public inventory and locked flags before loading real models."""
    if (
        run.get("status") != "PASS"
        or run.get("scope") != "development"
        or run.get("formal_oos_result") is not False
        or run.get("formal_research_status") != "BLOCKED"
        or run.get("holdout_metrics_generated") is not False
        or type(run.get("train_development_requested")) is not bool
    ):
        raise DataContractError(
            "Controlled execution flags do not preserve development and holdout locks"
        )
    required = BASE_ARTIFACTS | (
        TRAINING_ARTIFACTS if run["train_development_requested"] else frozenset()
    )
    actual = {
        str(path.relative_to(evidence))
        for path in evidence.rglob("*")
        if path.is_file()
        and "models" not in path.relative_to(evidence).parts
        and path != evidence / "run.json"
    }
    if set(run.get("artifacts", {})) != required or actual != required:
        raise DataContractError(
            "Controlled public artifact inventory is incomplete or has unexpected files"
        )
    for name, digest in run["artifacts"].items():
        path = (evidence / name).resolve()
        if not path.is_relative_to(evidence.resolve()) or file_hash(path) != digest:
            raise DataContractError("Controlled evidence artifact changed or escaped the run")
    validate_network_audit(read_evidence_json(evidence / "network.json"))


def write_plan(path: Path, plan: dict) -> None:
    """Compress large identity plans deterministically; do not discard samples."""
    payload = json.dumps(plan, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    path.write_bytes(gzip.compress(payload, mtime=0))


def read_plan(path: Path) -> dict:
    """Read a locally generated compressed plan for independent reconstruction."""
    return json.loads(gzip.decompress(path.read_bytes()))


def execution_contract(contract: dict, native: dict, tables: dict, plan: dict) -> dict:
    """Bind the frozen semantic contract to exact samples before fitting models."""
    data = {
        pair: frame_fingerprint(table.assign(sample_id=table.index).reset_index(drop=True))
        for pair, table in tables.items()
    }
    return {
        **contract,
        "semantic_contract_sha256": contract_identity(contract),
        "native_config_sha256": canonical_hash(native),
        "baseline_definition": BASELINE_DEFINITION,
        "baseline_id_aliases": {"mean_inner_train": "mean_train"},
        "randomness": {
            "experiment_and_split_seed": contract["model"]["seed"],
            "estimator_random_state_parameter": native["freqai"]["model_training_parameters"].get(
                "random_state"
            ),
            "estimator_seed_policy": "inherit actual native XGBoost default; never override production parameters with the experiment seed",
        },
        "comparison_contract": {
            "data_sha256": canonical_hash(data),
            "label": contract["label"],
            "feature_schema_by_pair": contract["feature_schema_by_pair"],
            "folds_sha256": canonical_hash(plan),
            "prediction_sample_ids": [
                identity for fold in plan["folds"] for identity in fold["test_ids"]
            ],
            "metric_definition": METRIC_DEFINITION,
            "environment": environment_versions(),
            "scope": "development",
            "cost_assumptions": contract["cost_policy"],
        },
    }


def prepare_controlled_research(
    config_paths: list[str],
    output: Path,
    *,
    train_development: bool = False,
    execution_state: dict | None = None,
) -> dict:
    """Create one immutable development execution; failures retain their evidence."""
    _, contract, native = resolve_controlled_configuration(config_paths)
    output.mkdir(parents=True, exist_ok=False)
    if execution_state is not None:
        execution_state["output_owned"] = True
    run = {
        **new_receipt_context(output.parent.name),
        "status": "RUNNING",
        "scope": "development",
        "command": sys.argv,
        "contract_sha256": contract_identity(contract),
        "contract_file": {
            "path": "configs/contracts/btc_eth_bnb_v1.json",
            "sha256": file_hash(ROOT / "configs/contracts/btc_eth_bnb_v1.json"),
        },
        "config_paths": config_paths,
        "train_development_requested": train_development,
        "formal_oos_result": False,
        "formal_research_status": "BLOCKED",
        "holdout_metrics_generated": False,
    }
    try:
        write_json(output / "semantic_contract.json", contract)
        source_audit = audit_three_pair_sources(native, contract["pairs"])
        write_json(output / "source_audit.json", source_audit)
        if source_audit["status"] == "FAIL" or any(
            item["source_prediction_preparation_status"] != "PASS"
            for item in source_audit["per_pair"]
        ):
            raise DataContractError(
                "Controlled source data are not valid for prediction preparation"
            )
        costs = build_cost_contract(native)
        write_json(output / "cost_contract.json", costs)
        for scenario in costs["scenarios"]:
            validate_cost_scenario(costs, scenario)
        metadata = identity_metadata(contract)
        prefix = probe_metadata(metadata, contract)
        metadata.to_parquet(output / "full_identity_metadata.parquet")
        prefix.to_parquet(output / "development_prefix_metadata.parquet")
        plan = build_split_plan(metadata, contract["validation"])
        prefix_plan = build_split_plan(prefix, contract["validation"])
        write_plan(output / "full_identity_plan.json.gz", plan)
        write_plan(output / "development_prefix_plan.json.gz", prefix_plan)
        write_json(
            output / "full_split_verification.json",
            verify_split_plan(metadata, contract["validation"], plan),
        )
        write_json(
            output / "prefix_split_verification.json",
            verify_split_plan(prefix, contract["validation"], prefix_plan),
        )
        write_json(
            output / "holdout_access.json",
            {
                "scope": "development",
                "operations": [
                    {
                        "purpose": "source_inventory",
                        "access": "full source bytes/quality; no fitting, prediction or scoring",
                        "allowed": True,
                    },
                    {
                        "purpose": "global_holdout_registration",
                        "access": "date column and derived identity/time metadata only",
                        "allowed": True,
                    },
                    {
                        "purpose": "historical_exposure_review",
                        "access": "existing research history and prior training evidence, no new tail metrics",
                        "allowed": True,
                    },
                ],
                "true_holdout_start": plan["holdout"]["start"],
                "true_holdout_numeric_values_materialized_for_models": False,
                "true_holdout_metrics_generated": False,
                "historical_independence": "BLOCKED",
            },
        )
        tables, panel_audit = materialize_native_prefix(native, contract, prefix)
        write_json(output / "native_prefix_audit.json", panel_audit)
        model_root = output / "models"
        model_root.mkdir()
        for number, (pair, table) in enumerate(tables.items()):
            table.to_parquet(model_root / f"native-prefix-{number}.parquet")
        resolved = execution_contract(contract, native, tables, prefix_plan)
        write_json(output / "execution_contract.json", resolved)
        run["execution_contract_sha256"] = canonical_hash(resolved)
        if train_development:
            from quant.research.fold_training import run_development_folds

            trained = run_development_folds(
                tables, prefix, prefix_plan, resolved, native, model_root / "development_run"
            )
            # Public projections retain the actual values and identities. Model
            # files/native exported configs remain in the ignored models tree.
            for filename in (
                "predictions.parquet",
                "expected_predictions.parquet",
                "prediction_metrics.json",
                "data_access.jsonl",
            ):
                shutil.copyfile(model_root / "development_run" / filename, output / filename)
            write_json(output / "development_training_manifest.json", trained)
            run["training_folds"] = len(trained["folds"])
            run["prediction_rows"] = trained["prediction_rows"]
        if run["source_files_sha256"] != current_source_hashes():
            raise DataContractError("Source/tests changed during controlled execution")
        resolve_controlled_configuration(config_paths)
        run["status"] = "PASS"
    except Exception as error:
        run.update(status="FAIL", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        run["finished_at"] = datetime.now(UTC).isoformat()
        run["artifacts"] = {
            str(path.relative_to(output)): file_hash(path)
            for path in sorted(output.rglob("*"))
            if path.is_file()
            and "models" not in path.relative_to(output).parts
            and path.name != "run.json"
        }
        write_json(output / "run.json", run)
    return run


def verify_controlled_research(
    evidence: Path, output: Path, test_receipt: Path | None = None
) -> dict:
    """Recreate dates, native values and fit/prediction lineage in a fresh receipt."""
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "scope": "development",
        "engineering_status": "FAIL",
        "status": "BLOCKED",
        "formal_research_allowed": False,
    }
    try:
        run = read_evidence_json(evidence / "run.json")
        # The preparation CLI stores evidence below <run_id>/execution. Bind
        # both the receipt and its parent directory to prevent cross-run mixing.
        expected_run_id = evidence.parent.name
        if run.get("run_id") != expected_run_id:
            raise DataContractError("Evidence parent directory and run_id differ")
        verify_receipt_context(run, run_id=expected_run_id)
        validate_execution_envelope(evidence, run)
        if test_receipt is None:
            raise FileNotFoundError(
                "Actual complete test execution receipt is required for final acceptance"
            )
        tests = verify_complete_test_execution(test_receipt, run_id=run["run_id"])
        _, contract, native = resolve_controlled_configuration(run["config_paths"])
        if (
            run["contract_sha256"] != contract_identity(contract)
            or read_evidence_json(evidence / "semantic_contract.json") != contract
        ):
            raise DataContractError("Execution is not bound to the frozen semantic contract")
        actual_sources = audit_three_pair_sources(native, contract["pairs"])
        saved_sources = read_evidence_json(evidence / "source_audit.json")
        for field in (
            "status",
            "scope",
            "formal_research_allowed",
            "pairs",
            "timeframe",
            "horizon",
            "sources",
            "per_pair",
            "source_set_sha256",
            "all_existing_files_unchanged",
            "historical_universe",
            "native_startup_requirement",
            "blockers",
            "policy",
        ):
            if actual_sources[field] != saved_sources[field]:
                raise DataContractError(
                    "Source quality/provenance cannot be independently reproduced"
                )
        for item in actual_sources["sources"]:
            key = item["pair"] + "|" + item["kind"]
            frozen = contract["input_files"].get(key)
            if (
                frozen is None
                or item.get("path") != frozen["path"]
                or item.get("file_sha256") != frozen["sha256"]
            ):
                raise DataContractError("Source bytes differ from frozen contract inputs")
        actual_costs = build_cost_contract(native)
        if actual_costs != read_evidence_json(evidence / "cost_contract.json"):
            raise DataContractError("Cost evidence/configuration changed")
        metadata = identity_metadata(contract)
        prefix = probe_metadata(metadata, contract)
        pd.testing.assert_frame_equal(
            metadata, pd.read_parquet(evidence / "full_identity_metadata.parquet"), check_exact=True
        )
        pd.testing.assert_frame_equal(
            prefix,
            pd.read_parquet(evidence / "development_prefix_metadata.parquet"),
            check_exact=True,
        )
        plan = read_plan(evidence / "full_identity_plan.json.gz")
        prefix_plan = read_plan(evidence / "development_prefix_plan.json.gz")
        full_check = verify_split_plan(metadata, contract["validation"], plan)
        prefix_check = verify_split_plan(prefix, contract["validation"], prefix_plan)
        if full_check != read_evidence_json(
            evidence / "full_split_verification.json"
        ) or prefix_check != read_evidence_json(evidence / "prefix_split_verification.json"):
            raise DataContractError(
                "Published split validation is not the actual independent result"
            )
        access_record = read_evidence_json(evidence / "holdout_access.json")
        if (
            access_record.get("true_holdout_metrics_generated") is not False
            or access_record.get("true_holdout_start") != plan["holdout"]["start"]
        ):
            raise DataContractError("True final holdout policy was not preserved")
        tables, native_check = materialize_native_prefix(native, contract, prefix)
        if native_check != read_evidence_json(evidence / "native_prefix_audit.json"):
            raise DataContractError("Actual native feature/target prefix changed")
        resolved = execution_contract(contract, native, tables, prefix_plan)
        if read_evidence_json(evidence / "execution_contract.json") != resolved or run[
            "execution_contract_sha256"
        ] != canonical_hash(resolved):
            raise DataContractError("Execution comparison contract changed")
        for number, table in enumerate(tables.values()):
            pd.testing.assert_frame_equal(
                table,
                pd.read_parquet(evidence / "models" / f"native-prefix-{number}.parquet"),
                check_exact=True,
            )
        if not run.get("train_development_requested"):
            raise FileNotFoundError("Real native development fold training was not executed")
        from quant.research.fold_training import verify_development_folds

        training = verify_development_folds(
            evidence / "models/development_run", tables, prefix, prefix_plan, resolved, native
        )
        actual_manifest = read_evidence_json(evidence / "models/development_run/manifest.json")
        if (
            read_evidence_json(evidence / "development_training_manifest.json") != actual_manifest
            or run.get("training_folds") != len(prefix_plan["folds"]) * len(contract["pairs"])
            or run.get("prediction_rows") != len(pd.read_parquet(evidence / "predictions.parquet"))
        ):
            raise DataContractError(
                "Published training manifest or run counts differ from actual artifacts"
            )
        for filename in (
            "predictions.parquet",
            "expected_predictions.parquet",
            "prediction_metrics.json",
            "data_access.jsonl",
        ):
            if file_hash(evidence / filename) != file_hash(
                evidence / "models/development_run" / filename
            ):
                raise DataContractError("Published development projection differs from actual run")
        result.update(
            engineering_status="PASS",
            status="BLOCKED",
            tests=tests,
            full_split=full_check,
            prefix_split=prefix_check,
            native_training=training,
            source_status=actual_sources["status"],
            cost_status=actual_costs["trade_evaluation_status"],
            historical_holdout_independence="BLOCKED",
            violations=0,
            blockers=actual_sources["blockers"]
            + [
                "Final holdout was historically exposed",
                "Formal P3-P6 execution/lineage and effect standards are not admitted",
            ],
        )
    except FileNotFoundError as error:
        result.update(engineering_status="BLOCKED", reason=str(error))
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        result.update(
            engineering_status="FAIL",
            status="FAIL",
            error={"type": type(error).__name__, "message": str(error)},
        )
    result.update(verified_at=datetime.now(UTC).isoformat())
    write_json(output / "acceptance.json", result)
    return result
