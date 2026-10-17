"""Offline preflight and native failure paths release resources deterministically."""

import asyncio
import json
from pathlib import Path

import pytest
from freqtrade.enums import RunMode

from quant_strategy.execution.market_snapshot import SnapshotError
from quant_strategy.execution.offline_backtest import SnapshotBinance

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs/baseline/acceptance/binance-usdt-market-snapshot.json"


@pytest.fixture
def config():
    value = json.loads((ROOT / "config.json").read_text())
    value["runmode"] = RunMode.BACKTEST
    value["exchange"]["pair_whitelist"] = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    return value


@pytest.mark.parametrize(
    "failure",
    [
        "live",
        "dry_run",
        "hyperopt",
        "exchange",
        "cross",
        "dynamic",
        "pattern",
        "duplicate",
        "tls",
        "default_type",
    ],
)
def test_preflight_rejects_invalid_config_before_clients(config, monkeypatch, failure):
    if failure in {"live", "dry_run", "hyperopt"}:
        config["runmode"] = RunMode(failure)
    elif failure == "exchange":
        config["exchange"]["name"] = "kraken"
    elif failure == "cross":
        config["margin_mode"] = "cross"
    elif failure == "dynamic":
        config["pairlists"] = [{"method": "VolumePairList"}]
    elif failure == "pattern":
        config["exchange"]["pair_whitelist"] = [".*/USDT:USDT"]
    elif failure == "duplicate":
        config["exchange"]["pair_whitelist"] *= 2
    elif failure == "tls":
        config["exchange"]["ccxt_config"] = {"verify": False}
    else:
        config["exchange"]["ccxt_config"] = {"options": {"defaultType": "spot"}}
    calls = []
    monkeypatch.setattr(SnapshotBinance, "_init_ccxt", lambda *a: calls.append(a))
    with pytest.raises(SnapshotError):
        SnapshotBinance(config, SNAPSHOT, 36500)
    assert calls == []


def test_failed_native_constructor_closes_both_clients_and_loop(config, monkeypatch):
    original = SnapshotBinance._init_ccxt
    resources = []
    closed = []

    def factory(self, exchange_config, sync, kwargs):
        client = original(self, exchange_config, sync, kwargs)
        close = client.close
        if sync:

            def sync_close():
                closed.append("sync")
                return close()

            client.close = sync_close
        else:

            async def async_close():
                closed.append("async")
                return await close()

            client.close = async_close
        resources.append(self.loop)
        return client

    monkeypatch.setattr(SnapshotBinance, "_init_ccxt", factory)
    config["timeframe"] = "7h"
    with pytest.raises(Exception, match="7h"):
        SnapshotBinance(config, SNAPSHOT, 36500)
    assert closed == ["async", "sync"]
    assert resources and all(loop.is_closed() for loop in resources)


def test_close_is_idempotent_and_repeated_refresh_retains_rules(config):
    exchange = SnapshotBinance(config, SNAPSHOT, 36500)
    try:
        before = dict(exchange.markets)
        for force in (False, True, True):
            exchange.reload_markets(force=force)
        assert before == dict(exchange.markets)
    finally:
        exchange.close()
        exchange.close()
    assert exchange.loop.is_closed()


def test_active_event_loop_rejected_before_client_creation(config):
    async def construct():
        with pytest.raises(SnapshotError, match="running event loop"):
            SnapshotBinance(config, SNAPSHOT, 36500)

    asyncio.run(construct())
