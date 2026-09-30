"""Point-in-time tradable-universe layer for local Freqtrade data.

This module reads local OHLCV and funding-rate feather files without accessing
future rows. Minimum stake remains optional because exchange market metadata is
not stored in OHLCV files.

References:
  - Freqtrade pairlist and data-provider documentation.
  - freqtrade/technical repository utilities are intentionally not used here;
    this layer only defines data availability and tradability inputs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Protocol

import pandas as pd

from contracts import DataPoolSnapshot, TradableAsset, require_timezone_aware
from logging_config import get_layer_logger, log_failures, log_layer_event


LOGGER = get_layer_logger("data_pool")


class DataPoolLayer(Protocol):
    """Build the assets that were tradable at a timestamp."""

    def build_tradable_pool(
        self, snapshot: DataPoolSnapshot
    ) -> DataPoolSnapshot:
        """Return a validated point-in-time pool."""
        ...


@dataclass(frozen=True, slots=True)
class LocalDataPoolConfig:
    """Settings for the local point-in-time pool loader."""

    data_directory: Path
    timeframe: str = "1h"
    minimum_age_bars: int = 0
    minimum_average_quote_volume: float = 0.0
    quote_volume_window_bars: int = 24


def _pair_from_ohlcv_filename(path: Path) -> str:
    """Convert Freqtrade futures filename to a CCXT-style pair."""
    symbol = path.name.rsplit("-", 2)[0]
    base, quote, margin = symbol.split("_")
    return f"{base}/{quote}:{margin}"


def _funding_path(ohlcv_path: Path) -> Path:
    """Return the matching funding-rate filename."""
    return ohlcv_path.with_name(
        ohlcv_path.name.replace("-futures.feather", "-funding_rate.feather")
    )


def _read_available_rows(path: Path, decision_timestamp: datetime) -> pd.DataFrame:
    """Read rows whose candle timestamp is known at the decision time."""
    frame = pd.read_feather(path)
    required_columns = {"date", "close", "volume"}
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"{path.name} missing columns: {sorted(missing_columns)}")

    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    frame = frame.loc[frame["date"] <= decision_timestamp].copy()
    return frame.sort_values("date").drop_duplicates("date", keep="last")


def _last_funding_rate(
    ohlcv_path: Path, decision_timestamp: datetime
) -> float | None:
    """Read the last known funding rate from the funding candle open column."""
    path = _funding_path(ohlcv_path)
    if not path.exists():
        return None
    funding_frame = _read_available_rows(path, decision_timestamp)
    if funding_frame.empty or "open" not in funding_frame.columns:
        return None
    return float(funding_frame.iloc[-1]["open"])


@log_failures("data_pool")
def load_point_in_time_pool(
    config: LocalDataPoolConfig,
    decision_timestamp: datetime,
    minimum_stake_by_pair: Mapping[str, float | None] | None = None,
) -> DataPoolSnapshot:
    """Build a pool from rows available at one closed-candle timestamp.

    Args:
        config: Local data and filtering settings.
        decision_timestamp: UTC-aware timestamp at which the decision is made.
        minimum_stake_by_pair: Optional exchange metadata captured separately.

    Returns:
        A point-in-time ``DataPoolSnapshot``.

    Raises:
        ValueError: If the timestamp or configuration is invalid.
        FileNotFoundError: If the data directory has no matching OHLCV files.
    """
    require_timezone_aware(decision_timestamp, "decision_timestamp")
    if config.minimum_age_bars < 0:
        raise ValueError("minimum_age_bars must be non-negative")
    if config.minimum_average_quote_volume < 0:
        raise ValueError("minimum_average_quote_volume must be non-negative")
    if config.quote_volume_window_bars < 1:
        raise ValueError("quote_volume_window_bars must be positive")

    pattern = f"*-{config.timeframe}-futures.feather"
    ohlcv_paths = sorted(config.data_directory.glob(pattern))
    if not ohlcv_paths:
        raise FileNotFoundError(f"no OHLCV files matched {config.data_directory / pattern}")

    minimum_stake_by_pair = minimum_stake_by_pair or {}
    assets: list[TradableAsset] = []
    for ohlcv_path in ohlcv_paths:
        available = _read_available_rows(ohlcv_path, decision_timestamp)
        if available.empty:
            continue

        pair = _pair_from_ohlcv_filename(ohlcv_path)
        quote_volume = (
            available["close"].astype(float) * available["volume"].astype(float)
        )
        average_quote_volume = float(
            quote_volume.tail(config.quote_volume_window_bars).mean()
        )
        age_bars = len(available)
        if age_bars < config.minimum_age_bars:
            continue
        if average_quote_volume < config.minimum_average_quote_volume:
            continue

        assets.append(
            TradableAsset(
                pair=pair,
                age_bars=age_bars,
                average_quote_volume=average_quote_volume,
                minimum_stake=minimum_stake_by_pair.get(pair),
                funding_rate=_last_funding_rate(ohlcv_path, decision_timestamp),
                is_active=True,
            )
        )

    snapshot = DataPoolSnapshot(
        timestamp=decision_timestamp,
        assets=tuple(sorted(assets, key=lambda asset: asset.pair)),
    )
    validate_data_pool_snapshot(snapshot)
    log_layer_event(
        LOGGER,
        logging.INFO,
        "data_pool_snapshot_ready",
        timestamp=decision_timestamp,
        asset_count=len(snapshot.assets),
        timeframe=config.timeframe,
    )
    return snapshot


def validate_data_pool_snapshot(snapshot: DataPoolSnapshot) -> None:
    """Validate the data-pool invariants shared by every experiment."""
    require_timezone_aware(snapshot.timestamp, "DataPoolSnapshot.timestamp")
    if not snapshot.assets:
        raise ValueError("DataPoolSnapshot.assets must not be empty")
    pair_names = snapshot.pairs
    if len(pair_names) != len(set(pair_names)):
        raise ValueError("DataPoolSnapshot contains duplicate pairs")
    for asset in snapshot.assets:
        if not asset.pair:
            raise ValueError("TradableAsset.pair must not be empty")
        if asset.age_bars < 0:
            raise ValueError("TradableAsset.age_bars must be non-negative")
        if asset.average_quote_volume < 0:
            raise ValueError("average_quote_volume must be non-negative")
        if asset.minimum_stake is not None and asset.minimum_stake < 0:
            raise ValueError("minimum_stake must be non-negative")
