"""Production-task semantics stay separate from raw/Ridge legacy defaults."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import talib.abstract as ta

from quant_strategy.config import LabelConfig, load_config
from quant_strategy.errors import DataContractError
from quant_strategy.experiments.runner import run_experiment
from quant_strategy.labels import build_labels
from quant_strategy.research.contract import (
    load_research_contract,
    resolve_controlled_configuration,
    validate_research_equivalence,
)
from quant_strategy.research.native_panel import (
    identity_metadata,
    materialize_native_prefix,
    probe_metadata,
)
from quant_strategy.validation.admission import require_training_admission

PATHS = [
    "configs/base.yaml",
    "configs/research.yaml",
    "configs/experiments/btc_eth_bnb_controlled_v1.yaml",
]


def test_overlay_preserves_production_task_and_does_not_change_legacy_defaults():
    legacy = load_config(["configs/base.yaml"])
    assert legacy.label.mode == "raw" and legacy.model.name == "ridge"
    research, contract, native = resolve_controlled_configuration(PATHS)
    assert research.label == LabelConfig("volnorm", 3, 14)
    assert research.model.params == native["freqai"]["model_training_parameters"]
    assert research.validation.min_train_size == 2190
    assert set(research.data) == set(contract["pairs"])
    assert validate_research_equivalence(contract, native, research)["label_equivalent"]
    reordered = load_config([*PATHS, "configs/experiments/baseline_raw.yaml"])
    with pytest.raises(DataContractError, match="preserve production"):
        validate_research_equivalence(contract, native, reordered)


@pytest.mark.parametrize("fault", ["horizon", "label", "model", "periods", "seed", "pairs"])
def test_task_mismatch_cannot_silently_become_comparable(fault):
    research, contract, native = resolve_controlled_configuration(PATHS)
    if fault == "horizon":
        research = replace(research, label=replace(research.label, prediction_horizon=2))
    elif fault == "label":
        research = replace(research, label=replace(research.label, mode="raw"))
    elif fault == "model":
        research = replace(research, model=replace(research.model, params={"n_estimators": 3}))
    elif fault == "periods":
        research = replace(research, periods=(6, 14, 25))
    elif fault == "seed":
        research = replace(research, seed=43)
    else:
        research = replace(
            research, data={k: v for k, v in research.data.items() if "BNB" not in k}
        )
    with pytest.raises(DataContractError):
        validate_research_equivalence(contract, native, research)


def test_production_volnorm_label_equals_explicit_formula_and_actual_future_close_time():
    import pyarrow.dataset as ds

    from quant_strategy.execution.freqtrade_strategy import QuantStrategy

    research, _, native = resolve_controlled_configuration(PATHS)
    raw = (
        ds.dataset(research.data["BNB/USDT:USDT"], format="ipc")
        .to_table(filter=ds.field("date") < pd.Timestamp("2020-05-01", tz="UTC"))
        .to_pandas()
    )
    strategy = QuantStrategy(native)
    strategy.freqai_info = native["freqai"]
    actual = strategy.set_freqai_targets(raw.copy(), {})["&-s_return"]
    labeled = build_labels(raw, research.label, "4h")
    expected = (raw.close.shift(-3) / raw.close - 1) / (ta.ATR(raw, timeperiod=14) / raw.close)
    np.testing.assert_array_equal(actual.to_numpy(), expected.to_numpy())
    np.testing.assert_array_equal(labeled.target.to_numpy(), expected.to_numpy())
    pd.testing.assert_series_equal(
        labeled.label_end_time.dt.as_unit("ns"),
        (raw.date.shift(-3) + pd.Timedelta(hours=4)).dt.as_unit("ns"),
        check_names=False,
    )
    assert labeled.target.tail(3).isna().all()


def test_contract_checksum_and_formal_flags_are_enforced(tmp_path):
    original = Path("configs/contracts/btc_eth_bnb_v1.json")
    path = tmp_path / "copy.json"
    path.write_bytes(original.read_bytes())
    path.with_suffix(".json.sha256").write_bytes(original.with_suffix(".json.sha256").read_bytes())
    damaged = json.loads(path.read_text())
    damaged["formal_oos_allowed"] = True
    path.write_text(json.dumps(damaged))
    with pytest.raises(DataContractError, match="checksum"):
        load_research_contract(path)


def test_contract_bound_legacy_or_formal_entry_is_refused_before_outputs(tmp_path):
    research, _, _ = resolve_controlled_configuration(PATHS)
    with pytest.raises(DataContractError, match="controlled-research"):
        run_experiment(research, tmp_path / "legacy", evaluate_final_holdout=True)
    with pytest.raises(DataContractError, match="no formal OOS"):
        require_training_admission(tmp_path / "forged-six-pass.json", research)
    assert not (tmp_path / "legacy").exists()


def test_identity_metadata_and_prefix_have_frozen_global_time_and_no_shrinking():
    _, contract, _ = resolve_controlled_configuration(PATHS)
    metadata = identity_metadata(contract)
    prefix = probe_metadata(metadata, contract)
    assert metadata.available_at.nunique() == contract["sample_interval"]["global_timestamps"]
    assert prefix.available_at.nunique() == 4380
    assert metadata.sample_id.is_unique
    assert (metadata.groupby("available_at").size() == 3).all()
    assert contract["holdout"]["historical_independence"] == "BLOCKED"
    with pytest.raises(DataContractError, match="unshortened"):
        probe_metadata(metadata.iloc[:20], contract)
    damaged = copy.deepcopy(contract)
    damaged["sample_interval"]["global_timestamps"] -= 1
    with pytest.raises(DataContractError, match="interval/count"):
        identity_metadata(damaged)


def test_native_materialization_rejects_true_holdout_or_changed_prefix_before_reading(monkeypatch):
    _, contract, native = resolve_controlled_configuration(PATHS)
    metadata = identity_metadata(contract)

    # The reader itself must enforce the frozen prefix; a caller cannot bypass
    # the guard by supplying a different metadata table to the public helper.
    def forbidden(*args, **kwargs):
        raise AssertionError("A forbidden numeric read was attempted")

    monkeypatch.setattr("pyarrow.dataset.dataset", forbidden)
    with pytest.raises(DataContractError, match="frozen development prefix"):
        materialize_native_prefix(native, contract, metadata)
