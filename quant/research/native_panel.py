"""Build identity-only global metadata and materialize an early development prefix.

Holdout identities use only the date column. Feature/label materialization uses
an Arrow date predicate and never returns rows from the real reserved tail.
Source inventory may inspect complete files; model-facing access is separate.
"""

import hashlib

import numpy as np
import pandas as pd
import pyarrow.dataset as arrow_dataset

from quant.errors import DataContractError
from quant.infrastructure.experiment_store import file_hash
from quant.market_data.contracts import frame_fingerprint
from quant.market_data.time_index import timeframe_delta
from quant.research.contract import ROOT, contract_identity
from quant.validation.native_features import populate_native_features


def identity_metadata(contract: dict) -> pd.DataFrame:
    """Read only dates, preserving actual label end observations across all pairs."""
    dates = {}
    step = timeframe_delta(contract["label"]["timeframe"])
    for pair in contract["pairs"]:
        item = contract["input_files"][pair + "|futures"]
        path = ROOT / item["path"]
        if file_hash(path) != item["sha256"]:
            raise DataContractError("Input changed before identity metadata read")
        current = pd.DatetimeIndex(pd.read_feather(path, columns=["date"]).date)
        if (
            current.tz is None
            or current.hasnans
            or not current.is_unique
            or not current.is_monotonic_increasing
            or not (current[1:] - current[:-1] == step).all()
        ):
            raise DataContractError("Controlled identity source has an unquarantined time gap")
        if file_hash(path) != item["sha256"]:
            raise DataContractError("Input changed during identity metadata read")
        dates[pair] = current
    common = dates[contract["pairs"][0]]
    for other in list(dates.values())[1:]:
        common = common.intersection(other)
    warmup = contract["feature_context_candles"]
    horizon = contract["label"]["horizon_candles"]
    if len(common) <= warmup + horizon:
        raise DataContractError("No controlled samples after context and future label tail")
    usable = common[warmup:-horizon]
    if not (usable[1:] - usable[:-1] == step).all():
        raise DataContractError("Global shared history is discontinuous")
    if (
        usable[0].isoformat() != contract["sample_interval"]["first_open"]
        or usable[-1].isoformat() != contract["sample_interval"]["last_open"]
        or len(usable) != contract["sample_interval"]["global_timestamps"]
    ):
        raise DataContractError("Frozen global sample interval/count differs from actual dates")
    signature = contract_identity(contract)
    rows = []
    for pair in contract["pairs"]:
        source = dates[pair]
        positions = source.get_indexer(usable)
        for stamp, end in zip(usable, source[positions + horizon] + step, strict=True):
            identity = hashlib.sha256(
                f"{signature}|{pair}|{stamp.isoformat()}".encode()
            ).hexdigest()
            rows.append(
                {
                    "sample_id": identity,
                    "pair": pair,
                    "candle_timestamp": stamp,
                    "available_at": stamp + step,
                    "label_start_time": stamp + step,
                    "label_end_time": end,
                    "data_version": contract["input_files"][pair + "|futures"]["sha256"],
                }
            )
    return (
        pd.DataFrame(rows)
        .sort_values(["available_at", "pair"], kind="stable")
        .set_index("sample_id", drop=False)
    )


def probe_metadata(metadata: pd.DataFrame, contract: dict) -> pd.DataFrame:
    """Use the exact predeclared earliest prefix, never silently shorten it."""
    requested = contract["development_probe"]["global_timestamps"]
    times = pd.DatetimeIndex(metadata.available_at.unique())
    if len(times) < requested:
        raise DataContractError("Insufficient unshortened development prefix")
    prefix = metadata.loc[metadata.available_at <= times[requested - 1]].copy()
    holdout_start = times[int(len(times) * (1 - contract["validation"]["final_holdout_fraction"]))]
    if not (prefix.label_end_time < holdout_start).all():
        raise DataContractError("Development probe reaches the true reserved holdout")
    return prefix


def materialize_native_prefix(
    native: dict, contract: dict, metadata: pd.DataFrame
) -> tuple[dict[str, pd.DataFrame], dict]:
    """Compute native features/labels only for the frozen early prefix and context."""
    expected = probe_metadata(identity_metadata(contract), contract)
    if not metadata.equals(expected):
        raise DataContractError(
            "Numeric materialization requires the exact frozen development prefix"
        )
    end = metadata.label_end_time.max()
    frames = {}
    for pair in contract["pairs"]:
        item = contract["input_files"][pair + "|futures"]
        path = ROOT / item["path"]
        if file_hash(path) != item["sha256"]:
            raise DataContractError("Native prefix input changed before predicate read")
        # Arrow returns only the early prefix; reserved price/target rows never
        # enter the model-facing DataFrames, even though inventory hashes bytes.
        values = arrow_dataset.dataset(path, format="ipc").to_table(
            filter=arrow_dataset.field("date") < end,
            columns=["date", "open", "high", "low", "close", "volume"],
        )
        frames[pair] = values.to_pandas()
        if file_hash(path) != item["sha256"]:
            raise DataContractError("Native prefix input changed during predicate read")
    tables = {}
    audit = {
        "scope": "development",
        "materialized_stop_exclusive": end.isoformat(),
        "feature_engine": "FreqaiDataKitchen.use_strategy_to_populate_indicators",
        "holdout_numeric_values_materialized": False,
        "holdout_scope": "true final tail; early prefix fixture reserved values are guarded separately",
        "prefix_fixture_reserved_values_present_in_storage": True,
        "pairs": {},
    }
    for pair in contract["pairs"]:
        populated = populate_native_features(native, frames, pair)
        schema = [c for c in populated if c.startswith("%")]
        if schema != contract["feature_schema_by_pair"][pair]:
            raise DataContractError("Actual native feature schema differs from frozen contract")
        target = "&-s_return"
        pair_metadata = metadata.loc[metadata.pair == pair]
        positions = pd.DatetimeIndex(populated.date).get_indexer(pair_metadata.candle_timestamp)
        if (positions < 0).any():
            raise DataContractError("Development sample is missing from native prefix")
        table = populated.iloc[positions][["date", *schema, target]].copy()
        table.index = pair_metadata.index
        table = table.rename(columns={target: "target"})
        if not np.isfinite(table[[*schema, "target"]].to_numpy()).all():
            raise DataContractError("A frozen sample lacks valid native features/labels")
        tables[pair] = table
        audit["pairs"][pair] = {
            "samples": len(table),
            "features": len(schema),
            "table_sha256": frame_fingerprint(table),
            "first_open": table.date.min().isoformat(),
            "last_open": table.date.max().isoformat(),
        }
    return tables, audit
