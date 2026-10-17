"""Boundary observations use test spies only; no accounts or orders are accessed."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import ccxt
import ccxt.pro
import pytest
from freqtrade.enums import RunMode
from freqtrade.exchange import Exchange
from freqtrade.exchange.binance import Binance
from freqtrade.resolvers import ExchangeResolver

from tools.run_offline_acceptance import (
    PAIRS,
    TIMERANGE,
    inspect_trace,
    publish_bytes,
    redact_text,
    validate_coverage_scope,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mode", [RunMode.LIVE, RunMode.DRY_RUN])
def test_native_trade_clients_and_credentials_before_market_load(monkeypatch, mode):
    """Stop native construction at market-load boundary; never reach private APIs."""
    config = json.loads((ROOT / "config.json").read_text())
    config["runmode"] = mode
    config["dry_run"] = mode == RunMode.DRY_RUN
    config["exchange"].update(
        {
            "key": "test-only-placeholder",
            "secret": "test-only-placeholder",
            "enable_ws": False,
        }
    )
    observations = []

    class MarketInitializationObserved(Exception):
        pass

    def stop_at_native_market_load(self, *args, **kwargs):
        observations.append(type(self))
        assert type(self) is Binance
        assert type(self._api) is ccxt.binance
        assert type(self._api_async) is ccxt.pro.binance
        expected = "test-only-placeholder" if mode == RunMode.LIVE else ""
        assert self._api.apiKey == expected
        assert self._api.secret == expected
        assert type(self._api).fetch is ccxt.Exchange.fetch
        assert type(self)._init_ccxt is Exchange._init_ccxt
        assert type(self)._api_reload_markets is Exchange._api_reload_markets
        self.close()
        self.loop.close()
        raise MarketInitializationObserved

    monkeypatch.setattr(Binance, "reload_markets", stop_at_native_market_load)
    with pytest.raises(MarketInitializationObserved):
        ExchangeResolver.load_exchange(deepcopy(config))
    assert observations == [Binance]


def test_importing_offline_module_does_not_modify_native_classes_or_methods():
    program = """
import json
import ccxt, ccxt.pro
from freqtrade.exchange import Exchange
from freqtrade.exchange.binance import Binance
from freqtrade.resolvers import ExchangeResolver
objects = lambda: (ccxt.binance, ccxt.binance.fetch, ccxt.pro.binance,
    ccxt.pro.binance.fetch, Binance._init_ccxt, Binance._api_reload_markets,
    ExchangeResolver.load_exchange)
before = objects()
import quant_strategy.execution.offline_backtest
assert all(a is b for a, b in zip(before, objects()))
print(json.dumps({'unchanged': True, 'native_exchange': Binance.__module__}))
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "unchanged": True,
        "native_exchange": "freqtrade.exchange.binance",
    }


def test_native_cli_merge_keeps_overlay_order_and_explicit_userdir(tmp_path):
    from freqtrade.commands import Arguments
    from freqtrade.commands.optimize_commands import setup_optimize_configuration

    overlay = tmp_path / "overlay.json"
    overlay.write_text(json.dumps({"exchange": {"pair_whitelist": ["SOL/USDT:USDT"]}}))
    userdir = tmp_path / "dedicated-userdir"
    userdir.mkdir()
    arguments = [
        "backtesting",
        "-c",
        "config.json",
        "-c",
        str(overlay),
        "--userdir",
        str(userdir),
        "--pairs",
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "--timerange",
        "20250101-20250115",
        "--cache",
        "none",
        "--export",
        "signals",
    ]
    parsed = Arguments(arguments).get_parsed_arg()
    config = setup_optimize_configuration(parsed, RunMode.BACKTEST)
    assert parsed["config"] == ["config.json", str(overlay)]
    # Freqtrade records loaded files in reverse precedence (load_from_files.insert(0)).
    assert config["config_files"] == [str(overlay), "config.json"]
    assert config["exchange"]["pair_whitelist"] == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    assert config["user_data_dir"] == userdir
    assert config["backtest_cache"] == "none"
    assert config["export"] == "signals"
    assert config["runmode"] == RunMode.BACKTEST


@pytest.mark.parametrize("operation", ["connect", "sendto", "sendmsg", "sendmmsg"])
def test_syscall_acceptance_rejects_attempts_even_if_syscall_failed(operation):
    trace = f"4312 {operation}(3, 0, 0) = -1 ENETUNREACH\n4312 +++ exited with 0 +++\n"
    with pytest.raises(RuntimeError, match="Unexpected connect/send"):
        inspect_trace(trace)


def test_syscall_acceptance_requires_completion_and_accepts_only_local_probe():
    with pytest.raises(RuntimeError, match="completion"):
        inspect_trace("4312 socket(AF_INET6, SOCK_STREAM, 0) = 3\n")
    result = inspect_trace(
        "4312 socket(AF_INET6, SOCK_STREAM, 0) = 3\n"
        '4312 bind(3, {sa_family=AF_INET6, sin6_addr=inet_pton(AF_INET6, "::1")}, 28)'
        " = -1 EADDRNOTAVAIL\n4312 +++ exited with 0 +++\n"
    )
    assert result["connect_or_send_count"] == 0
    assert result["bind_count"] == result["socket_creation_count"] == 1


def test_syscall_acceptance_explains_only_absent_local_name_cache():
    prefix = '4312 connect(4, {sa_family=AF_UNIX, sun_path="'
    suffix = '"}, 110) = -1 ENOENT\n4312 +++ exited with 0 +++\n'
    result = inspect_trace(prefix + "/var/run/nscd/socket" + suffix)
    assert result["failed_local_nscd_probes"] == 1
    assert result["connect_or_send_count"] == 0
    with pytest.raises(RuntimeError, match="Unexpected connect/send"):
        inspect_trace(prefix + "/other/local/socket" + suffix)
    with pytest.raises(RuntimeError, match="Unexpected connect/send"):
        inspect_trace((prefix + "/var/run/nscd/socket" + suffix).replace("-1 ENOENT", "0"))


def test_publication_changes_only_paths_preserving_all_trading_values(tmp_path):
    source = tmp_path / "metadata.json"
    value = {"data_path": "/private/run/models/x", "prediction": 0.123, "labels": ["&-s_return"]}
    source.write_text(json.dumps(value))
    published = json.loads(publish_bytes(source, [("/private/run", "/RUN")]))
    assert published == {**value, "data_path": "/RUN/models/x"}
    assert json.loads(source.read_text()) == value
    with pytest.raises(RuntimeError, match="Unmapped private path"):
        redact_text("/home/private-user/project", [])


@pytest.mark.parametrize("change", ["false_gate", "other_dates", "other_pairs", "raw", "metadata"])
def test_coverage_gate_rejects_incompatible_scope(change):
    coverage = {
        "minimum_scope_ready": True,
        "minimum_scope": {
            "pairs": PAIRS.copy(),
            "timerange": TIMERANGE,
            "raw_data_ready": True,
            "metadata_scope_ready": True,
        },
        "requirements": {"timerange": TIMERANGE},
    }
    validate_coverage_scope(coverage)
    if change == "false_gate":
        coverage["minimum_scope_ready"] = False
    elif change == "other_dates":
        coverage["minimum_scope"]["timerange"] = "20250101-20250122"
    elif change == "other_pairs":
        coverage["minimum_scope"]["pairs"] = ["SOL/USDT:USDT"]
    else:
        coverage["minimum_scope"][
            change + "_data_ready" if change == "raw" else "metadata_scope_ready"
        ] = False
    with pytest.raises(RuntimeError, match="BLOCKED"):
        validate_coverage_scope(coverage)
