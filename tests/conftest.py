"""Shared fixtures and deterministic pytest execution-layer classification.

The test suite has several deliberately different execution costs.  The
collection hook below assigns *every* collected item to ``ci`` and then adds
more specific responsibility and execution markers.  Consequently ``-m ci``
cannot silently omit a test, while ``-m fast`` can avoid complete native model
training workflows during development.

Markers are assigned from reviewed test bodies and fixture dependencies,
using exact test IDs when a module mixes synthetic and historical inputs.
They do not depend on the developer's environment or an implicit
``PYTEST_ADDOPTS`` value.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest_plugins = ("tests.support.native_prefix",)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Every node in these modules consumes a module fixture that prepares a real
# native fold or a completed native training run.  Mixed-responsibility files
# are classified by exact unparametrized node ID below instead.
_SLOW_FILES = {
    "tests/integration/test_controlled_fold_training.py",
    "tests/integration/test_independent_native_acceptance.py",
}

_SLOW_TESTS = {
    "tests/e2e/test_research_pipeline.py::test_complete_research_artifacts_and_final_holdout",
    "tests/e2e/test_research_pipeline.py::test_cli_and_default_unseen_final_holdout",
    "tests/integration/test_controlled_holdout.py::test_real_three_pair_native_prefix_plan_and_preprocessing_isolation",
    "tests/integration/test_local_data_network.py::test_research_cli_dataset_training_cv_and_comparison_without_network",
    "tests/integration/test_native_purged_training.py::test_actual_preprocessing_and_early_stopping_exclude_all_purged_rows",
    "tests/integration/test_native_purged_training.py::test_validation_extremes_never_fit_training_scaler",
    "tests/integration/test_native_purged_training.py::test_actual_real_btc_training_and_prediction",
    "tests/integration/test_native_purged_training.py::test_actual_reused_datakitchen_keeps_distinct_window_fit_identities",
    "tests/integration/test_native_purged_training.py::test_fresh_userdirs_have_identical_logical_audit_reference",
    "tests/integration/test_native_purged_training.py::test_repeated_input_cannot_overwrite_audit_or_refit",
    "tests/integration/test_offline_freqtrade.py::test_native_backtest_in_disconnected_namespace_matches_online_reference",
    "tests/integration/test_offline_freqtrade.py::test_corrected_native_backtest_is_reproducible_in_fresh_disconnected_userdirs",
    "tests/integration/test_strategy_adapter.py::test_installed_freqai_train_predict_lifecycle",
    "tests/leakage/test_native_feature_causality.py::test_actual_native_expansion_schema_and_all_feature_contracts",
    "tests/leakage/test_native_feature_causality.py::test_actual_btc_eth_bnb_files_full_native_features_are_causal",
    "tests/leakage/test_native_feature_causality.py::test_native_informative_timeframe_merges_only_closed_candles",
    "tests/leakage/test_native_feature_causality.py::test_real_native_audit_cli_binds_run_identity_and_immutable_inputs",
}

# Only genuine historical-file consumers acquire real_data.  For example,
# the historical-coverage and Funding unit modules write synthetic fixtures
# into tmp_path and therefore do not belong to the real-data execution layer.
_REAL_DATA_FILES = {
    "tests/integration/test_controlled_fold_training.py",
    "tests/integration/test_independent_native_acceptance.py",
    "tests/integration/test_real_split_foundations.py",
}

_REAL_DATA_TESTS = {
    "tests/unit/test_controlled_contract.py::test_overlay_preserves_production_task_and_does_not_change_legacy_defaults",
    "tests/unit/test_controlled_contract.py::test_task_mismatch_cannot_silently_become_comparable",
    "tests/unit/test_controlled_contract.py::test_production_volnorm_label_equals_explicit_formula_and_actual_future_close_time",
    "tests/unit/test_controlled_contract.py::test_contract_bound_legacy_or_formal_entry_is_refused_before_outputs",
    "tests/unit/test_controlled_contract.py::test_identity_metadata_and_prefix_have_frozen_global_time_and_no_shrinking",
    "tests/unit/test_controlled_contract.py::test_native_materialization_rejects_true_holdout_or_changed_prefix_before_reading",
    "tests/integration/test_controlled_holdout.py::test_real_three_pair_native_prefix_plan_and_preprocessing_isolation",
    "tests/integration/test_dataset_governance.py::test_same_real_data_rebuilds_identical_schema_samples_and_exclusions",
    "tests/integration/test_native_purged_training.py::test_actual_real_btc_training_and_prediction",
    "tests/integration/test_native_purged_training.py::test_actual_reused_datakitchen_keeps_distinct_window_fit_identities",
    "tests/integration/test_native_training_boundaries.py::test_real_btc_native_boundary_gate_cannot_pass_by_exit_code_only",
    "tests/integration/test_offline_freqtrade.py::test_native_backtest_in_disconnected_namespace_matches_online_reference",
    "tests/integration/test_offline_freqtrade.py::test_corrected_native_backtest_is_reproducible_in_fresh_disconnected_userdirs",
    "tests/leakage/test_native_feature_causality.py::test_actual_btc_eth_bnb_files_full_native_features_are_causal",
    "tests/leakage/test_native_feature_causality.py::test_real_native_audit_cli_binds_run_identity_and_immutable_inputs",
}

_FORMAL_PREFLIGHT_FILES = {
    "tests/integration/test_formal_training_admission.py",
    "tests/unit/test_admission_integrity.py",
    "tests/unit/test_controlled_contract.py",
    "tests/unit/test_controlled_costs.py",
    "tests/unit/test_controlled_governance.py",
    "tests/unit/test_training_readiness_gate.py",
}

_PRODUCTION_REGRESSION_FILES = {
    "tests/regression/test_strategy_contract.py",
    "tests/integration/test_freqtrade_regression_report.py",
    "tests/integration/test_mode_isolation_acceptance.py",
    "tests/integration/test_native_purged_training.py",
    "tests/integration/test_native_training_boundaries.py",
    "tests/integration/test_offline_freqtrade.py",
    "tests/integration/test_offline_lifecycle.py",
    "tests/integration/test_strategy_adapter.py",
    "tests/integration/test_truncation_audit.py",
    "tests/unit/test_native_isolation.py",
}

_E2E_TESTS = {
    "tests/e2e/test_research_pipeline.py::test_complete_research_artifacts_and_final_holdout",
    "tests/e2e/test_research_pipeline.py::test_cli_and_default_unseen_final_holdout",
    "tests/integration/test_controlled_fold_training.py::test_real_three_pair_fold_uses_native_training_and_never_final_holdout",
    "tests/integration/test_controlled_fold_training.py::test_nonfinal_fixture_holdout_changes_cannot_change_development_models_or_predictions",
    "tests/integration/test_independent_native_acceptance.py::test_real_native_training_has_independently_recomputed_safe_boundaries",
    "tests/integration/test_local_data_network.py::test_research_cli_dataset_training_cv_and_comparison_without_network",
    "tests/integration/test_native_purged_training.py::test_actual_real_btc_training_and_prediction",
    "tests/integration/test_offline_freqtrade.py::test_native_backtest_in_disconnected_namespace_matches_online_reference",
    "tests/integration/test_offline_freqtrade.py::test_corrected_native_backtest_is_reproducible_in_fresh_disconnected_userdirs",
    "tests/integration/test_strategy_adapter.py::test_installed_freqai_train_predict_lifecycle",
    "tests/leakage/test_native_feature_causality.py::test_real_native_audit_cli_binds_run_identity_and_immutable_inputs",
}

_LEAKAGE_SECURITY_FILES = {
    "tests/unit/test_suite_execution.py",
    "tests/integration/test_controlled_fold_training.py",
    "tests/integration/test_controlled_holdout.py",
    "tests/integration/test_formal_training_admission.py",
    "tests/integration/test_independent_native_acceptance.py",
    "tests/integration/test_mode_isolation_acceptance.py",
    "tests/integration/test_native_purged_training.py",
    "tests/integration/test_native_training_boundaries.py",
    "tests/integration/test_network_audit_boundary.py",
    "tests/integration/test_offline_freqtrade.py",
    "tests/integration/test_offline_lifecycle.py",
    "tests/integration/test_real_split_foundations.py",
    "tests/unit/test_admission_integrity.py",
    "tests/unit/test_controlled_receipts.py",
    "tests/unit/test_controlled_splits.py",
    "tests/unit/test_native_isolation.py",
    "tests/unit/test_offline_extension.py",
    "tests/unit/test_snapshot_contract.py",
    "tests/unit/test_training_readiness_gate.py",
}

_LEAKAGE_SECURITY_TESTS = {
    "tests/contract/test_backends_and_splits.py::test_split_contract_global_pair_boundaries",
    "tests/e2e/test_research_pipeline.py::test_complete_research_artifacts_and_final_holdout",
    "tests/e2e/test_research_pipeline.py::test_cli_and_default_unseen_final_holdout",
    "tests/integration/test_dataset_governance.py::test_file_change_during_read_fails_before_dataset",
    "tests/integration/test_local_data_network.py::test_research_cli_dataset_training_cv_and_comparison_without_network",
    "tests/integration/test_local_data_network.py::test_local_formats_do_not_make_network_calls",
    "tests/integration/test_local_data_network.py::test_framework_download_gate_is_preserved",
    "tests/unit/test_controlled_contract.py::test_contract_checksum_and_formal_flags_are_enforced",
    "tests/unit/test_controlled_contract.py::test_contract_bound_legacy_or_formal_entry_is_refused_before_outputs",
    "tests/unit/test_controlled_contract.py::test_identity_metadata_and_prefix_have_frozen_global_time_and_no_shrinking",
    "tests/unit/test_controlled_contract.py::test_native_materialization_rejects_true_holdout_or_changed_prefix_before_reading",
}


def _relative_test_path(item: pytest.Item) -> str:
    """Return a stable repository-relative path for a collected test item."""

    return Path(str(item.fspath)).resolve().relative_to(_REPOSITORY_ROOT).as_posix()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Assign execution and responsibility markers to every test item.

    Marker assignment is intentionally centralized so parametrized nodes use
    the same policy as their parent test.  ``ci`` is universal by design;
    marker expressions selecting other layers therefore cannot accidentally
    redefine the complete suite.
    """

    del config  # The policy is repository-local and does not depend on config flags.
    for item in items:
        relative = _relative_test_path(item)
        path = Path(relative)
        base_node = item.nodeid.split("[", 1)[0]
        slow = relative in _SLOW_FILES or base_node in _SLOW_TESTS

        item.add_marker(pytest.mark.ci)

        if path.parts and path.parts[0] == "tests":
            if len(path.parts) > 1 and path.parts[1] in {"unit", "contract"}:
                item.add_marker(pytest.mark.unit_contract)
            if len(path.parts) > 1 and path.parts[1] == "integration":
                item.add_marker(pytest.mark.integration)
            if len(path.parts) > 1 and path.parts[1] == "regression":
                item.add_marker(pytest.mark.production_regression)

        if (
            (len(path.parts) > 1 and path.parts[1] == "leakage")
            or relative in _LEAKAGE_SECURITY_FILES
            or base_node in _LEAKAGE_SECURITY_TESTS
        ):
            item.add_marker(pytest.mark.leakage_security)
        if relative in _PRODUCTION_REGRESSION_FILES:
            item.add_marker(pytest.mark.production_regression)
        if base_node in _E2E_TESTS:
            item.add_marker(pytest.mark.e2e)
        if relative in _REAL_DATA_FILES or base_node in _REAL_DATA_TESTS:
            item.add_marker(pytest.mark.real_data)
        if relative in _FORMAL_PREFLIGHT_FILES:
            item.add_marker(pytest.mark.formal_preflight)
        if slow:
            item.add_marker(pytest.mark.slow)

        # Key synthetic leakage/fail-closed checks remain fast even in modules
        # containing expensive positive native training and audit workflows.
        if not slow:
            item.add_marker(pytest.mark.fast)


def make_ohlcv(count: int = 240) -> pd.DataFrame:
    """Build valid 4h candles with nonconstant features and no external I/O."""
    index = np.arange(count, dtype=float)
    close = 100 + index * 0.04 + 2 * np.sin(index * 0.3)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=count, freq="4h", tz="UTC"),
            "open": close * 1.001,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 500 + index + 50 * np.cos(index * 0.2),
        }
    )


@pytest.fixture
def candles() -> pd.DataFrame:
    return make_ohlcv()
