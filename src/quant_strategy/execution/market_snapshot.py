"""Verified Binance metadata for the historical-backtest adapter only.

Contracts inspected: Freqtrade 2026.7 Exchange.reload_markets/Binance.load_leverage_tiers;
CCXT 4.5.75 Binance.parse_markets/Exchange.set_markets. References:
https://www.freqtrade.io/en/stable/backtesting/
https://docs.ccxt.com/#/?id=markets
https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/Exchange-Information
"""

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SUPPORTED = {"freqtrade": "2026.7", "ccxt": "4.5.75"}
ENDPOINT = "https://fapi.binance.com/fapi/v1/exchangeInfo"
SCHEMA = 1


class SnapshotError(ValueError):
    """Metadata is missing, incompatible or cannot be verified."""


def digest(value: Any) -> str:
    """Hash deterministic JSON; reject non-finite numbers."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def versions() -> dict[str, str]:
    """Fail closed on framework versions the adapter has not been verified against."""
    import ccxt
    import freqtrade

    actual = {"freqtrade": freqtrade.__version__, "ccxt": ccxt.__version__}
    if actual != SUPPORTED:
        raise SnapshotError(f"Unsupported runtime {actual}; adapter requires {SUPPORTED}")
    return actual


def leverage_rules(pairs: list[str]) -> dict:
    """Fingerprint native backtest rules, without inventing/fetching leverage tiers."""
    import freqtrade.exchange.binance as module

    path = Path(module.__file__).with_name("binance_leverage_tiers.json")
    content = path.read_bytes()
    tiers = json.loads(content)
    missing = set(pairs) - tiers.keys()
    if missing:
        raise SnapshotError(f"Native bundled leverage tiers missing pairs: {sorted(missing)}")
    return {
        "source": "freqtrade/exchange/binance_leverage_tiers.json",
        "sha256": hashlib.sha256(content).hexdigest(),
        "pairs": {pair: tiers[pair] for pair in pairs},
    }


def parse_response(raw: dict, pairs: list[str]) -> dict:
    """Use the real CCXT parser on the genuine response, without any API emulation."""
    import ccxt

    api = ccxt.binance({"options": {"defaultType": "swap"}})
    try:
        markets = api.parse_markets(raw["symbols"])
        indexed = {market["symbol"]: market for market in markets}
        missing = set(pairs) - indexed.keys()
        if missing:
            raise SnapshotError(f"Real exchangeInfo does not contain pairs: {sorted(missing)}")
        api.set_markets([indexed[pair] for pair in pairs])
        for pair, market in api.markets.items():
            if not (
                market["linear"]
                and market["swap"]
                and market["settle"] == "USDT"
                and market["contractSize"] > 0
            ):
                raise SnapshotError(f"Not a Binance USDT perpetual market: {pair}")
        return {
            "markets": dict(api.markets),
            "currencies": dict(api.currencies),
            "precision_mode": api.precisionMode,
        }
    finally:
        api.close()


def capture_snapshot(path: Path, pairs: list[str], proxy: str | None = None) -> dict:
    """Explicit online acquisition: one real public exchangeInfo request, no candles."""
    import ccxt

    runtime = versions()
    pairs = sorted(set(pairs))
    if not pairs:
        raise SnapshotError("Specify at least one exact pair")
    if path.exists():
        raise SnapshotError(f"Refusing to overwrite snapshot: {path}")
    options = {"options": {"defaultType": "swap"}, "timeout": 30000}
    if proxy:
        options["httpsProxy"] = proxy
    api = ccxt.binance(options)
    started = datetime.now(UTC).isoformat()
    try:
        raw = api.fapiPublicGetExchangeInfo()
    finally:
        api.close()
    snapshot = {
        "schema_version": SCHEMA,
        "exchange": "binance",
        "market_type": "linear-usdt-perpetual",
        "request_started_at": started,
        "acquired_at": datetime.now(UTC).isoformat(),
        "source": {"url": ENDPOINT, "method": "GET", "authenticated": False},
        "versions": runtime,
        "pairs": pairs,
        "raw_response": raw,
        "raw_sha256": digest(raw),
        "normalized": parse_response(raw, pairs),
        "leverage_rules": leverage_rules(pairs),
    }
    snapshot["sha256"] = digest(snapshot)
    # Exclusive create also protects an existing snapshot against concurrent capture.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return snapshot


def _unique_object(items: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise SnapshotError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_snapshot(path: Path, required_pairs: list[str], max_age_days: float = 30) -> dict:
    """Validate integrity, origin, scope, freshness and real-response parsing before use."""
    try:
        runtime = versions()
        if not math.isfinite(max_age_days) or max_age_days <= 0:
            raise SnapshotError("snapshot-max-age-days must be finite and positive")
        snapshot = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        claimed_hash = snapshot.pop("sha256")
        if digest(snapshot) != claimed_hash:
            raise SnapshotError("Snapshot SHA256 mismatch")
        if (
            snapshot["schema_version"] != SCHEMA
            or snapshot["exchange"] != "binance"
            or snapshot["market_type"] != "linear-usdt-perpetual"
            or snapshot["source"] != {"url": ENDPOINT, "method": "GET", "authenticated": False}
            or snapshot["versions"] != runtime
        ):
            raise SnapshotError("Snapshot schema/exchange/source/version mismatch")
        acquired = datetime.fromisoformat(snapshot["acquired_at"])
        started = datetime.fromisoformat(snapshot["request_started_at"])
        now = datetime.now(UTC)
        if (
            acquired.tzinfo is None
            or started.tzinfo is None
            or started > acquired
            or acquired > now + timedelta(minutes=5)
            or now - acquired > timedelta(days=max_age_days)
        ):
            raise SnapshotError("Snapshot timestamps invalid or snapshot expired")
        pairs = snapshot["pairs"]
        if not pairs or pairs != sorted(set(pairs)) or set(required_pairs) - set(pairs):
            raise SnapshotError(f"Snapshot pair scope does not cover {sorted(required_pairs)}")
        raw = snapshot["raw_response"]
        if snapshot["raw_sha256"] != digest(raw):
            raise SnapshotError("Raw response SHA256 mismatch")
        if snapshot["normalized"] != parse_response(raw, pairs):
            raise SnapshotError("Normalized rules differ from genuine response parsed by CCXT")
        if snapshot["leverage_rules"] != leverage_rules(pairs):
            raise SnapshotError("Native leverage bundle or recorded rules changed")
        snapshot["sha256"] = claimed_hash
        return snapshot
    except SnapshotError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise SnapshotError(f"Cannot validate market snapshot {path}: {exc}") from exc
