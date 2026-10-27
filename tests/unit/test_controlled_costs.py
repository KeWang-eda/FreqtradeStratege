"""Check development cost assumptions against actual installed native source/logic."""

import json
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from quant.infrastructure.experiment_store import canonical_hash
from quant.research.costs import build_cost_contract, validate_cost_scenario


@pytest.fixture
def production():
    return json.loads(Path("config.json").read_text())


def test_native_fee_is_per_side_and_config_is_unchanged(production):
    before = deepcopy(production)
    contract = build_cost_contract(production)
    assert contract["fee"]["entry_fraction"] == production["fee"] == 0.0005
    assert contract["fee"]["exit_fraction"] == production["fee"]
    assert contract["fee"]["applies_each_side"] is True
    assert contract["framework"]["status"] == "PASS"
    assert all(
        source["sha256"] and source["functions"] for source in contract["framework"]["sources"]
    )
    assert production == before
    assert contract["position_configuration"]["max_open_trades"] == production["max_open_trades"]
    assert contract["strategy"]["rules"]["leverage_cap"] == 2


def test_frozen_fee_stress_does_not_invent_funding_or_zero_slippage(production):
    contract = build_cost_contract(production)
    for scenario, multiplier in zip(contract["scenarios"], (1, 2), strict=True):
        result = validate_cost_scenario(contract, scenario)
        assert result["definition_status"] == "PASS"
        assert result["entry_fee_fraction"] == production["fee"] * multiplier
        assert result["exit_fee_fraction"] == production["fee"] * multiplier
        assert result["status"] == "BLOCKED"
        assert result["slippage_basis_points"] is None
        assert result["funding_payment_schedule_verified"] is False
        assert result["formal_research_allowed"] is False


@pytest.mark.parametrize("fee", [-1, float("nan"), float("inf"), True, "0.0005", 1])
def test_invalid_fee_fraction_is_rejected(production, fee):
    production["fee"] = fee
    with pytest.raises(ValueError, match="finite fraction"):
        build_cost_contract(production)


def test_missing_fee_is_not_replaced_by_guessed_exchange_rate(production):
    production.pop("fee")
    contract = build_cost_contract(production)
    result = validate_cost_scenario(contract, contract["scenarios"][0])
    assert result["status"] == "BLOCKED" and result["entry_fee_fraction"] is None


@pytest.mark.parametrize("fallback", [0, 0.001, -0.001])
def test_synthetic_funding_fallback_is_not_accepted(production, fallback):
    production["futures_funding_rate"] = fallback
    with pytest.raises(ValueError, match="synthetic funding"):
        build_cost_contract(production)


def test_unfrozen_cost_scenario_or_added_fields_are_rejected(production):
    contract = build_cost_contract(production)
    for changed in (
        {**contract["scenarios"][0], "fee_multiplier": 1.1},
        {**contract["scenarios"][0], "slippage_bps": 0},
        {**contract["scenarios"][0], "funding_rate": 0},
        {**contract["scenarios"][0], "fee_multiplier": True},
    ):
        with pytest.raises(ValueError, match="frozen"):
            validate_cost_scenario(contract, changed)


def test_contract_corruption_is_not_a_valid_scenario(production):
    contract = build_cost_contract(production)
    contract["fee"]["entry_fraction"] = 0
    with pytest.raises(ValueError, match="integrity"):
        validate_cost_scenario(contract, contract["scenarios"][0])


@pytest.mark.parametrize("fault", ["funding_claim", "slippage_claim", "pass_string", "source_hash"])
def test_rehashed_cost_claim_cannot_authorize_unknown_costs(production, fault):
    contract = build_cost_contract(production)
    if fault == "funding_claim":
        contract["funding"]["historical_schedule_verified"] = True
    elif fault == "slippage_claim":
        contract["slippage"]["basis_points"] = 0
    elif fault == "pass_string":
        contract["trade_evaluation_status"] = "PASS"
    else:
        contract["framework"]["sources"][0]["sha256"] = "0" * 64
    contract["sha256"] = canonical_hash(
        {key: value for key, value in contract.items() if key != "sha256"}
    )
    with pytest.raises(ValueError):
        validate_cost_scenario(contract, contract["scenarios"][0])


def test_native_funding_formula_and_timestamp_endpoints_are_hand_verifiable():
    # Execute the installed native implementation directly; no exchange is constructed.
    from freqtrade.exchange.exchange import Exchange

    frame = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=3, freq="8h", tz="UTC"),
            "open_fund": [0.001, -0.002, 0.004],
            "open_mark": [100.0, 110.0, 120.0],
        }
    )
    expected = (0.001 * 100 - 0.002 * 110 + 0.004 * 120) * 2
    args = dict(df=frame, amount=2, open_date=frame.date.iloc[0], close_date=frame.date.iloc[2])
    assert Exchange.calculate_funding_fees(None, is_short=True, **args) == pytest.approx(expected)
    assert Exchange.calculate_funding_fees(None, is_short=False, **args) == pytest.approx(-expected)


def test_native_missing_mark_join_drops_event_so_governance_must_check_it():
    from freqtrade.exchange.exchange import Exchange

    dates = pd.date_range("2025-01-01", periods=3, freq="8h", tz="UTC")
    funding = pd.DataFrame({"date": dates, "open": [0.001, 0.002, 0.003]})
    mark = pd.DataFrame({"date": dates[[0, 2]], "open": [100.0, 100.0]})
    combined = Exchange.combine_funding_and_mark(funding, mark)
    assert len(combined) == 2
    assert dates[1] not in set(combined.date)
