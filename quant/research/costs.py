"""Frozen development cost assumptions, separate from production configuration.

Reviewed against the installed Freqtrade 2026.7 implementation. The adapter reads
its source files without constructing an exchange. A configured backtest fee is
an assumption, not proof of a historical account fee; slippage and historical
funding-event provenance remain unresolved and keep trading evaluation BLOCKED.
"""

import ast
import importlib.metadata
import importlib.util
import math
from pathlib import Path
from typing import Any

from quant.infrastructure.experiment_store import canonical_hash, file_hash

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = (
    {"name": "configured_fee_baseline", "fee_multiplier": 1.0, "slippage_bps": None},
    {"name": "fee_stress_2x", "fee_multiplier": 2.0, "slippage_bps": None},
)


def _source_evidence() -> dict:
    """Hash actual implementation files and the reviewed functions; never import clients."""
    try:
        version = importlib.metadata.version("freqtrade")
        spec = importlib.util.find_spec("freqtrade")
    except (ImportError, importlib.metadata.PackageNotFoundError):
        return {"status": "BLOCKED", "version": None, "sources": []}
    if spec is None or not spec.submodule_search_locations:
        return {"status": "BLOCKED", "version": version, "sources": []}
    root = Path(next(iter(spec.submodule_search_locations)))
    methods = {
        "optimize/backtesting.py": (
            "Backtesting.set_fee",
            "Backtesting._load_bt_data_detail",
            "Backtesting._get_order_filled",
            "Backtesting._enter_trade",
            "Backtesting._get_exit_for_signal",
            "Backtesting.check_order_cancel",
            "Backtesting.get_valid_entry_price_and_stake",
            "Backtesting._run_funding_fees",
        ),
        "exchange/exchange.py": (
            "Exchange.combine_funding_and_mark",
            "Exchange.calculate_funding_fees",
        ),
        "exchange/binance.py": ("Binance.funding_fee_cutoff",),
        "strategy/interface.py": (
            "IStrategy.custom_entry_price",
            "IStrategy.custom_exit_price",
            "IStrategy.custom_stake_amount",
        ),
    }
    sources = []
    for relative, required in methods.items():
        path = root / relative
        if not path.is_file():
            return {"status": "BLOCKED", "version": version, "sources": sources}
        before = file_hash(path)
        module = ast.parse(path.read_text())
        indexed = {
            f"{cls.name}.{method.name}": method
            for cls in module.body
            if isinstance(cls, ast.ClassDef)
            for method in cls.body
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if set(required) - indexed.keys():
            return {"status": "BLOCKED", "version": version, "sources": sources}
        sources.append(
            {
                "path": "freqtrade/" + relative,
                "sha256": before,
                "unchanged_during_read": before == file_hash(path),
                "functions": {
                    name: {
                        "line": indexed[name].lineno,
                        "ast_sha256": canonical_hash(
                            ast.dump(indexed[name], include_attributes=False)
                        ),
                    }
                    for name in required
                },
            }
        )
    return {
        "status": "PASS"
        if version == "2026.7" and all(item["unchanged_during_read"] for item in sources)
        else "BLOCKED",
        "version": version,
        "reviewed_version": "2026.7",
        "sources": sources,
    }


def _strategy_rules() -> dict:
    path = ROOT / "quant/execution/freqtrade_strategy.py"
    module = ast.parse(path.read_text())
    strategy = next(node for node in module.body if isinstance(node, ast.ClassDef))
    rules = {}
    for node in strategy.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "can_short",
                    "stoploss",
                    "minimal_roi",
                    "trailing_stop",
                    "startup_candle_count",
                }:
                    rules[target.id] = ast.literal_eval(node.value)
        if isinstance(node, ast.FunctionDef) and node.name == "leverage":
            returned = next(item for item in ast.walk(node) if isinstance(item, ast.Return))
            if (
                isinstance(returned.value, ast.Call)
                and isinstance(returned.value.func, ast.Name)
                and returned.value.func.id == "min"
                and isinstance(returned.value.args[0], ast.Constant)
            ):
                rules["leverage_cap"] = returned.value.args[0].value
            else:
                raise ValueError("Unreviewed strategy leverage expression")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": file_hash(path),
        "rules": rules,
        "leverage_still_subject_to_native_exchange_limit": True,
    }


def build_cost_contract(config: dict) -> dict[str, Any]:
    """Snapshot current native assumptions and predeclare fee stress scenarios.

    Higher fee multipliers are hypothetical sensitivity cases, not exchange fee
    claims. Unknown slippage is null, never zero. No production setting is written.
    """
    if (
        config.get("trading_mode") != "futures"
        or config.get("exchange", {}).get("name") != "binance"
        or config.get("margin_mode") != "isolated"
    ):
        raise ValueError("Cost contract supports the reviewed Binance isolated-futures scope")
    fee = config.get("fee")
    if fee is not None and (
        isinstance(fee, bool)
        or not isinstance(fee, (int, float))
        or not math.isfinite(fee)
        or not 0 <= fee < 1
    ):
        raise ValueError("Configured fee must be a finite fraction in [0,1)")
    if config.get("futures_funding_rate") is not None:
        raise ValueError("A synthetic funding fallback cannot enter the controlled cost contract")
    contract: dict[str, Any] = {
        "schema_version": 1,
        "scope": "development_cost_preparation",
        "trade_evaluation_status": "BLOCKED",
        "formal_research_allowed": False,
        "native_config_sha256": canonical_hash(config),
        "framework": _source_evidence(),
        "strategy": _strategy_rules(),
        "fee": {
            "entry_fraction": fee,
            "exit_fraction": fee,
            "source": "production config fee"
            if fee is not None
            else "native exchange fee lookup required",
            "evidence_grade": "configured_backtest_assumption_not_historical_account_fee",
            "applies_each_side": True,
            "native_function": "Backtesting.set_fee / _enter_trade (fee_open and fee_close)",
        },
        "fill": {
            "entry_order_type": config.get("order_types", {}).get("entry"),
            "exit_order_type": config.get("order_types", {}).get("exit"),
            "default_entry_rate": "current simulated candle open before custom price and precision handling",
            "ordinary_exit_rate": "current candle open; ROI, stops and liquidation have separate native paths",
            "limit_fill_rule": "candle.low <= requested_rate <= candle.high",
            "queue_position_partial_fills_and_market_impact": "not established by OHLC range simulation",
            "live_order_book_settings": {
                "entry_pricing": config.get("entry_pricing"),
                "exit_pricing": config.get("exit_pricing"),
                "note": "Live pricing configuration does not recreate a historical order book in backtesting",
            },
            "unfilledtimeout": config.get("unfilledtimeout"),
            "timeout_and_rejection_handling": "Native timeout, cancel/replace, stake/precision and strategy confirmation paths retained",
        },
        "slippage": {
            "status": "BLOCKED",
            "basis_points": None,
            "evidence_grade": "no_verified_execution_or_order_book_calibration",
            "zero_slippage_claimed": False,
        },
        "funding": {
            "status": "BLOCKED",
            "historical_schedule_verified": False,
            "native_join": "funding and mark inner join on exact event timestamp when fallback is None",
            "native_interval": "open_date <= event_timestamp <= close_date, timestamp-unit aligned",
            "native_formula": "sum(open_fund * open_mark * amount); short positive, long negative",
            "storage_timeframe_is_schedule": False,
            "missing_rate_fallback": None,
            "native_empty_or_nan_aggregate_behavior": "Native calculation may return zero; controlled evaluation requires verified nonmissing events and finite inputs beforehand",
            "required_evidence": "Pair-specific authoritative historical payment events, rate coverage and matching mark data",
        },
        "position_configuration": {
            key: config.get(key)
            for key in (
                "trading_mode",
                "margin_mode",
                "max_open_trades",
                "stake_currency",
                "stake_amount",
                "dry_run_wallet",
                "tradable_balance_ratio",
                "stoploss",
                "trailing_stop",
            )
        },
        "scenarios": [dict(scenario) for scenario in SCENARIOS],
        "scenario_policy": {
            "source": "Prespecified engineering sensitivity assumptions, not claimed market observations",
            "multipliers_apply_to_both_entry_and_exit": True,
            "production_config_modified": False,
            "requires_contract_and_scenario_sha_in_each_backtest_artifact": True,
            "prediction_metrics_are_not_trade_returns": True,
        },
        "blockers": [
            "Historical account/execution-cost provenance is not established by configured fee",
            "Slippage calibration/approved assumption is missing",
            "Authoritative historical funding payment-event evidence is missing",
        ],
    }
    contract["sha256"] = canonical_hash(contract)
    return contract


def validate_cost_scenario(contract: dict, scenario: dict) -> dict[str, Any]:
    """Validate immutable sensitivity definition; never authorize unknown trading costs.

    A checksum detects inconsistency, not authenticity. The parent acceptance
    verifier must additionally bind the contract to actual configuration/source
    fingerprints and run identity. Valid shape remains BLOCKED for trading here.
    """
    if not isinstance(contract, dict) or contract.get("sha256") != canonical_hash(
        {key: value for key, value in contract.items() if key != "sha256"}
    ):
        raise ValueError("Cost contract integrity mismatch")
    if (
        contract.get("schema_version") != 1
        or contract.get("scope") != "development_cost_preparation"
        or contract.get("trade_evaluation_status") != "BLOCKED"
        or contract.get("formal_research_allowed") is not False
        or canonical_hash(contract.get("scenarios")) != canonical_hash(list(SCENARIOS))
    ):
        raise ValueError("Unsupported or altered cost contract")
    if (
        not isinstance(scenario, dict)
        or isinstance(scenario.get("fee_multiplier"), bool)
        or not isinstance(scenario.get("fee_multiplier"), (int, float))
        or scenario not in SCENARIOS
    ):
        raise ValueError("Cost scenario is not one of the frozen prespecified assumptions")
    if contract["framework"] != _source_evidence() or contract["strategy"] != _strategy_rules():
        raise ValueError("Framework or strategy implementation changed after cost freeze")
    fee = contract["fee"]["entry_fraction"]
    if fee is not None and (
        isinstance(fee, bool)
        or not isinstance(fee, (int, float))
        or not math.isfinite(fee)
        or not 0 <= fee < 1
    ):
        raise ValueError("Cost fee is not a finite configured fraction")
    if fee != contract["fee"]["exit_fraction"]:
        raise ValueError("Native fee contract must apply the same configured rate on each side")
    if (
        contract["slippage"].get("basis_points") is not None
        or contract["funding"].get("historical_schedule_verified") is not False
    ):
        raise ValueError("Unverified slippage or funding claims cannot unlock cost evaluation")
    rate = None if fee is None else fee * scenario["fee_multiplier"]
    if rate is not None and rate >= 1:
        raise ValueError("Fee stress must remain a fraction below one on each side")
    return {
        "schema_version": 1,
        "scope": "development_cost_preparation",
        "status": "BLOCKED",
        "definition_status": "PASS",
        "contract_sha256": contract["sha256"],
        "scenario_sha256": canonical_hash(scenario),
        "scenario": dict(scenario),
        "entry_fee_fraction": rate,
        "exit_fee_fraction": rate,
        "slippage_basis_points": None,
        "funding_payment_schedule_verified": False,
        "blockers": list(contract["blockers"]),
        "formal_research_allowed": False,
    }
