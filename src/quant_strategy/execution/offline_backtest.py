"""Backtest-only injection into the native Freqtrade engine; no runtime patching.

Version-specific hooks: Exchange._init_ccxt/_api_reload_markets (Freqtrade 2026.7).
Public injection: Backtesting(config, exchange=...), CCXT set_markets().
See market_snapshot.py for upstream references and compatibility checks.
"""

import argparse
import asyncio
import logging
from copy import deepcopy
from pathlib import Path

import ccxt
import ccxt.pro
from freqtrade.enums import RunMode
from freqtrade.exchange.binance import Binance

from quant_strategy.execution.market_snapshot import (
    SnapshotError,
    capture_snapshot,
    load_snapshot,
    validate_pairs,
    versions,
)


class OfflineNetworkError(RuntimeError):
    """An offline backtest attempted an unexpected exchange HTTP operation."""


class LocalBinanceClient(ccxt.binance):
    """Real CCXT client whose transport fails before any HTTP/DNS/socket access."""

    def fetch(self, url, method="GET", headers=None, body=None):
        raise OfflineNetworkError(f"Offline backtest forbids exchange HTTP: {method} {url}")


class LocalBinanceAsyncClient(ccxt.pro.binance):
    """Async transport guard; native backtesting never starts websocket clients."""

    async def fetch(self, url, method="GET", headers=None, body=None):
        raise OfflineNetworkError(f"Offline backtest forbids exchange HTTP: {method} {url}")


def check_config(config: dict) -> list[str]:
    """Reject other modes/scopes before creating any exchange client."""
    versions()
    if config.get("runmode") != RunMode.BACKTEST:
        raise SnapshotError("Local market snapshots are allowed only in RunMode.BACKTEST")
    exchange = config["exchange"]
    if (
        exchange["name"] != "binance"
        or config.get("trading_mode") != "futures"
        or config.get("margin_mode") != "isolated"
        or config.get("stake_currency") != "USDT"
        or exchange.get("demo_trading")
        or exchange.get("sandbox")
    ):
        raise SnapshotError("Adapter supports Binance USDT futures isolated backtests only")
    pairlists = config.get("pairlists", [])
    if len(pairlists) != 1 or pairlists[0].get("method") != "StaticPairList":
        raise SnapshotError("Offline backtest requires a single StaticPairList")
    if config.get("enable_dynamic_pairlist") or config.get("freqai_backtest_live_models"):
        raise SnapshotError("Dynamic pairlists/live-model backtests are outside offline scope")
    pairs = exchange["pair_whitelist"]
    correlated = (
        config.get("freqai", {}).get("feature_parameters", {}).get("include_corr_pairlist", [])
    )
    validate_pairs(pairs)
    if correlated:
        validate_pairs(correlated)
    required = sorted(set(pairs) | set(correlated))
    for key in ("ccxt_config", "ccxt_sync_config", "ccxt_async_config"):
        options = exchange.get(key, {})
        if (
            options.get("verify") is False
            or options.get("options", {}).get("defaultType", "swap") != "swap"
        ):
            raise SnapshotError(
                "Offline client requires native swap scope and verified TLS settings"
            )
        ccxt_options = options.get("options", {})
        fetch_markets = ccxt_options.get("fetchMarkets", {})
        if (
            "urls" in options
            or ccxt_options.get("sandboxMode")
            or ccxt_options.get("enableDemoTrading")
            or ccxt_options.get("defaultSubType", "linear") != "linear"
            or not isinstance(fetch_markets, dict)
            or fetch_markets.get("types", ["linear"]) != ["linear"]
        ):
            raise SnapshotError(
                "Offline metadata supports only the Binance production linear market scope"
            )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise SnapshotError("Construct the synchronous backtest outside a running event loop")
    return required


class SnapshotBinance(Binance):
    """Keep native validation, leverage, pricing and precision; replace metadata I/O."""

    def __init__(self, config: dict, snapshot_path: Path, max_age_days: float = 30):
        required = check_config(config)
        self._snapshot = load_snapshot(snapshot_path, required, max_age_days)
        # Native Backtesting also forces this, but injection constructs the exchange first.
        config["dry_run"] = True
        try:
            super().__init__(config, validate=True, load_leverage_tiers=True)
        except BaseException:
            self.close()
            raise

    def close(self):
        # Failed preflight must also be safe when the native destructor calls close().
        loop = getattr(self, "loop", None)
        if loop is None or getattr(self, "_snapshot_closed", False):
            return
        try:
            try:
                client = getattr(self, "_api_async", None)
                if client is not None and not loop.is_closed():
                    loop.run_until_complete(client.close())
            finally:
                client = getattr(self, "_api", None)
                if client is not None:
                    client.close()
        finally:
            if not loop.is_closed():
                loop.close()
            self._snapshot_closed = True

    def _init_ccxt(self, exchange_config, sync, ccxt_kwargs):
        # Native constructor already merged _ccxt_config and sync/async configuration.
        # Backtesting strips credentials and does not use demo/private initialization.
        # Preserve any native static parameters using the same merge precedence.
        from freqtrade.misc import deep_merge_dicts

        options = deep_merge_dicts(self._ccxt_params, deepcopy(ccxt_kwargs))
        return (LocalBinanceClient if sync else LocalBinanceAsyncClient)(options)

    async def _api_reload_markets(self, reload=False):
        # No network fallback, including forced/scheduled reloads. Native reload_markets
        # shares these markets/options with the sync client and retains validation.
        normalized = deepcopy(self._snapshot["normalized"])
        self._api_async.set_markets(normalized["markets"], normalized["currencies"])
        if (
            self._api_async.precisionMode != normalized["precision_mode"]
            or dict(self._api_async.markets) != normalized["markets"]
        ):
            raise SnapshotError("CCXT market restoration changed the recorded rules")


def run_backtest(arguments: list[str], snapshot: Path, max_age_days: float = 30) -> None:
    """Parse native options and execute the original Backtesting.start() unchanged."""
    from freqtrade.commands import Arguments
    from freqtrade.commands.optimize_commands import setup_optimize_configuration
    from freqtrade.loggers import setup_logging_pre
    from freqtrade.optimize.backtesting import Backtesting
    from freqtrade.system import asyncio_setup, gc_set_threshold, set_mp_start_method

    setup_logging_pre()
    asyncio_setup()
    parsed = Arguments(["backtesting", *arguments]).get_parsed_arg()
    gc_set_threshold()
    set_mp_start_method()
    config = setup_optimize_configuration(parsed, RunMode.BACKTEST)
    exchange = SnapshotBinance(config, snapshot, max_age_days)
    logging.getLogger(__name__).info(
        "Offline snapshot %s SHA256=%s acquired=%s",
        snapshot,
        exchange._snapshot["sha256"],
        exchange._snapshot["acquired_at"],
    )
    try:
        backtesting = Backtesting(config, exchange=exchange)
        backtesting.start()
    finally:
        Backtesting.cleanup()
        exchange.close()


def main(argv: list[str] | None = None) -> int:
    """Separate explicit online capture from strictly local historical backtesting."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="Explicitly fetch genuine public metadata")
    capture.add_argument("--snapshot", type=Path, required=True)
    capture.add_argument("--pairs", nargs="+", required=True)
    capture.add_argument("--proxy", help="Process-local HTTPS proxy, e.g. http://127.0.0.1:7890")
    backtest = subparsers.add_parser(
        "backtesting", help="Native engine with verified local metadata"
    )
    backtest.add_argument("--snapshot", type=Path, required=True)
    backtest.add_argument("--snapshot-max-age-days", type=float, default=30)
    backtest.add_argument(
        "arguments", nargs=argparse.REMAINDER, help="-- followed by native options"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            snapshot = capture_snapshot(args.snapshot, args.pairs, args.proxy)
            print(f"Captured {args.snapshot} SHA256={snapshot['sha256']}")
        else:
            arguments = args.arguments
            if arguments and arguments[0] == "--":
                arguments = arguments[1:]
            run_backtest(arguments, args.snapshot, args.snapshot_max_age_days)
    except (SnapshotError, OfflineNetworkError) as exc:
        parser.exit(2, f"Offline backtest error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
