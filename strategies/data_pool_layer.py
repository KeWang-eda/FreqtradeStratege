"""Point-in-time tradable-universe contract."""

from __future__ import annotations

from typing import Protocol

from contracts import DataPoolSnapshot


class DataPoolLayer(Protocol):
    """Build the assets that were tradable at a timestamp."""

    def build_tradable_pool(
        self, snapshot: DataPoolSnapshot
    ) -> DataPoolSnapshot:
        """Return a validated point-in-time pool."""
        ...


def validate_data_pool_snapshot(snapshot: DataPoolSnapshot) -> None:
    """Validate the data-pool invariants shared by every experiment."""
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
