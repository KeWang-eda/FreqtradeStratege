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
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SUPPORTED = {"freqtrade": "2026.7", "ccxt": "4.5.75"}
ENDPOINT = "https://fapi.binance.com/fapi/v1/exchangeInfo"
SCHEMA = 1
ENVELOPE_FIELDS = {
    "schema_version",
    "exchange",
    "market_type",
    "request_started_at",
    "acquired_at",
    "source",
    "versions",
    "pairs",
    "raw_response",
    "raw_sha256",
    "normalized",
    "leverage_rules",
    "sha256",
}


class SnapshotError(ValueError):
    """Metadata is missing, incompatible or cannot be verified."""


def validate_pairs(pairs: list[str]) -> list[str]:
    """Require an explicit, nonempty, unambiguous market scope."""
    if (
        not isinstance(pairs, list)
        or not pairs
        or any(
            not isinstance(pair, str) or not re.fullmatch(r"[A-Z0-9]+/USDT:USDT", pair)
            for pair in pairs
        )
        or len(pairs) != len(set(pairs))
    ):
        raise SnapshotError("Specify unique exact Binance USDT perpetual pairs")
    return sorted(pairs)


def _positive(value: Any, label: str, *, zero: bool = False) -> float:
    if isinstance(value, bool):
        raise SnapshotError(f"Invalid numeric rule: {label}")
    number = float(value)
    if not math.isfinite(number) or number < 0 or (not zero and number == 0):
        raise SnapshotError(f"Missing or invalid market rule: {label}")
    return number


def _raw_rules(market: dict) -> None:
    """CCXT permits fallback precision: reject incomplete raw rules before parsing."""
    if (
        market.get("contractType") != "PERPETUAL"
        or market.get("quoteAsset") != "USDT"
        or market.get("marginAsset") != "USDT"
        or not market.get("baseAsset")
        or not isinstance(market.get("status"), str)
        or not market["status"]
        or not isinstance(market.get("orderTypes"), list)
        or not market["orderTypes"]
        or any(not isinstance(order, str) or not order for order in market["orderTypes"])
    ):
        raise SnapshotError("Incomplete USDT perpetual market identity/order rules")
    filters = market["filters"]
    indexed = {entry["filterType"]: entry for entry in filters}
    if len(filters) != len(indexed):
        raise SnapshotError("Duplicate market filter types")
    for kind, minimum, maximum, step in (
        ("PRICE_FILTER", "minPrice", "maxPrice", "tickSize"),
        ("LOT_SIZE", "minQty", "maxQty", "stepSize"),
        ("MARKET_LOT_SIZE", "minQty", "maxQty", "stepSize"),
    ):
        if kind not in indexed:
            raise SnapshotError(f"Missing market rule: {kind}")
        rule = indexed[kind]
        lower = _positive(rule[minimum], f"{kind}/{minimum}")
        upper = _positive(rule[maximum], f"{kind}/{maximum}")
        _positive(rule[step], f"{kind}/{step}")
        if upper < lower:
            raise SnapshotError(f"Reversed limits: {kind}")
    notional = indexed.get("MIN_NOTIONAL", indexed.get("NOTIONAL"))
    if not notional:
        raise SnapshotError("Missing market rule: MIN_NOTIONAL/NOTIONAL")
    _positive(notional.get("minNotional", notional.get("notional")), "minimum notional")
    if "contractSize" in market:
        _positive(market["contractSize"], "contractSize")
    # Binance USDT-M usually omits contractSize. CCXT's native parser defines it
    # as 1 in that case; retain this native interpretation, never supply a rule.


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
    for pair in pairs:
        if not tiers[pair]:
            raise SnapshotError(f"Empty native leverage tiers: {pair}")
        for tier in tiers[pair]:
            lower = _positive(tier["minNotional"], "tier/minNotional", zero=True)
            upper = _positive(tier["maxNotional"], "tier/maxNotional")
            _positive(tier["maxLeverage"], "tier/maxLeverage")
            _positive(tier["maintenanceMarginRate"], "tier/maintenanceMarginRate")
            if upper <= lower:
                raise SnapshotError(f"Invalid native leverage tier: {pair}")
    return {
        "source": "freqtrade/exchange/binance_leverage_tiers.json",
        "sha256": hashlib.sha256(content).hexdigest(),
        "pairs": {pair: tiers[pair] for pair in pairs},
    }


def parse_response(raw: dict, pairs: list[str]) -> dict:
    """Use the real CCXT parser on the genuine response, without any API emulation."""
    import ccxt

    pairs = validate_pairs(pairs)
    api = ccxt.binance({"options": {"defaultType": "swap"}})
    try:
        raw_markets = raw["symbols"]
        ids = [market["symbol"] for market in raw_markets]
        if len(ids) != len(set(ids)):
            raise SnapshotError("Duplicate raw market symbols")
        markets = api.parse_markets(raw["symbols"])
        indexed = {market["symbol"]: market for market in markets}
        if len(indexed) != len(markets):
            raise SnapshotError("Ambiguous normalized market symbols")
        missing = set(pairs) - indexed.keys()
        if missing:
            raise SnapshotError(f"Real exchangeInfo does not contain pairs: {sorted(missing)}")
        for pair in pairs:
            _raw_rules(indexed[pair]["info"])
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
    except (KeyError, TypeError, ValueError, ccxt.BaseError) as exc:
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotError(f"Incomplete or invalid genuine response: {exc}") from exc
    finally:
        api.close()


def capture_snapshot(path: Path, pairs: list[str], proxy: str | None = None) -> dict:
    """Explicit online acquisition: one real public exchangeInfo request, no candles."""
    import ccxt

    runtime = versions()
    pairs = validate_pairs(pairs)
    if path.exists() or path.is_symlink():
        raise SnapshotError(f"Refusing to overwrite snapshot: {path}")
    options = {"options": {"defaultType": "swap"}, "timeout": 30000}
    if proxy:
        options["httpsProxy"] = proxy
    api = ccxt.binance(options)
    started = datetime.now(UTC).isoformat()
    try:
        raw = api.fapiPublicGetExchangeInfo()
    except ccxt.BaseError as exc:
        raise SnapshotError(f"Explicit market acquisition failed: {exc}") from exc
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
    publish_snapshot(path, snapshot)
    return snapshot


def publish_snapshot(path: Path, snapshot: dict) -> None:
    """Publish a fully synced file atomically without ever replacing an existing name.

    Same-directory os.link is the POSIX no-clobber publication primitive. A killed
    writer may leave an obvious hidden .tmp file, never a partially written final.
    https://docs.python.org/3/library/tempfile.html#tempfile.NamedTemporaryFile
    https://docs.python.org/3/library/os.html#os.link
    """
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(snapshot, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise SnapshotError(f"Cannot atomically publish snapshot {path}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
        if isinstance(max_age_days, bool) or not math.isfinite(max_age_days) or max_age_days <= 0:
            raise SnapshotError("snapshot-max-age-days must be finite and positive")
        snapshot = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(snapshot, dict) or set(snapshot) != ENVELOPE_FIELDS:
            raise SnapshotError(
                f"Cannot validate market snapshot {path}: envelope has missing or unknown fields"
            )
        claimed_hash = snapshot.pop("sha256")
        if digest(snapshot) != claimed_hash:
            raise SnapshotError("Snapshot SHA256 mismatch")
        if (
            type(snapshot["schema_version"]) is not int
            or snapshot["schema_version"] != SCHEMA
            or snapshot["exchange"] != "binance"
            or snapshot["market_type"] != "linear-usdt-perpetual"
            or snapshot["source"] != {"url": ENDPOINT, "method": "GET", "authenticated": False}
            or snapshot["source"]["authenticated"] is not False
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
        validate_pairs(required_pairs)
        if pairs != validate_pairs(pairs) or set(required_pairs) - set(pairs):
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
