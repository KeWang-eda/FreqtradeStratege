"""Auditable development-only time plans with an independent reference verifier.

The native splitter remains unchanged. A plan reserves the last configured
fraction of global availability timestamps, then excludes every earlier sample
whose label reaches that reservation. No target/feature values are read here.
This does not restore the independence of a historically accessed holdout.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from quant.config import ValidationConfig
from quant.errors import DataContractError
from quant.validation import TimeSeriesSplitter

_TIME_COLUMNS = (
    "candle_timestamp",
    "available_at",
    "label_start_time",
    "label_end_time",
)
_REQUIRED = ("sample_id", "pair", *_TIME_COLUMNS, "data_version")
_STEP = pd.Timedelta(hours=4)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _checked_metadata(metadata: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(metadata, pd.DataFrame) or metadata.empty:
        raise DataContractError("A nonempty, unshortened metadata panel is required")
    if set(_REQUIRED) - set(metadata.columns):
        raise DataContractError("Missing sample identity, time or data-version metadata")
    if not metadata.columns.is_unique or not metadata.index.is_unique:
        raise DataContractError("Duplicate metadata columns or sample index")
    result = metadata.loc[:, list(_REQUIRED)].copy()
    for column in ("sample_id", "pair", "data_version"):
        if not result[column].map(lambda value: isinstance(value, str) and bool(value)).all():
            raise DataContractError(f"Nonempty string metadata required: {column}")
    if result.sample_id.duplicated().any() or result.index.tolist() != result.sample_id.tolist():
        raise DataContractError("Metadata index must preserve unique sample_id identity")
    if result.duplicated(["pair", "candle_timestamp"]).any():
        raise DataContractError("Duplicate pair/candle sample")
    for column in _TIME_COLUMNS:
        values = result[column]
        if (
            not isinstance(values.dtype, pd.DatetimeTZDtype)
            or values.isna().any()
            or str(values.dt.tz) not in {"UTC", "Etc/UTC", "UTC+00:00"}
        ):
            raise DataContractError(f"UTC-aware, nonmissing timestamps required: {column}")
        result[column] = values.dt.tz_convert("UTC")
        if (pd.DatetimeIndex(result[column]).as_unit("ns").asi8 % _STEP.value != 0).any():
            raise DataContractError(f"Timestamp violates the UTC 4h grid: {column}")
    if not result.available_at.is_monotonic_increasing:
        raise DataContractError("Metadata must be sorted by global availability time")
    if (
        not result.available_at.eq(result.candle_timestamp + _STEP).all()
        or not result.label_start_time.eq(result.available_at).all()
        or not result.label_end_time.ge(result.label_start_time).all()
    ):
        raise DataContractError("Invalid candle-close availability or label information interval")
    for pair, group in result.groupby("pair", sort=False):
        if not group.candle_timestamp.diff().dropna().eq(_STEP).all():
            raise DataContractError(f"Unquarantined timestamp gap or disorder for {pair}")
    return result.sort_values(["available_at", "pair"], kind="stable")


def _settings(validation: dict) -> ValidationConfig:
    if not isinstance(validation, dict):
        raise DataContractError("Validation settings must be a mapping")
    try:
        return ValidationConfig(**validation)
    except (TypeError, ValueError) as error:
        raise DataContractError(f"Invalid frozen validation settings: {error}") from error


def _metadata_records(metadata: pd.DataFrame) -> list[dict]:
    records = metadata.to_dict("records")
    for record in records:
        for column in _TIME_COLUMNS:
            record[column] = record[column].isoformat()
    return records


def _ids(frame: pd.DataFrame, mask: Any) -> list[str]:
    return frame.index[mask].tolist()


def _distribution(frame: pd.DataFrame, ids: list[str]) -> dict[str, int]:
    return {
        str(pair): int(count)
        for pair, count in frame.loc[ids].groupby("pair", sort=True).size().items()
    }


def _fold_record(
    metadata: pd.DataFrame,
    number: int,
    raw_train: list[str],
    test: list[str],
    purged: list[str],
    embargoed: list[str],
    development: list[str],
) -> dict:
    excluded = set(purged) | set(embargoed)
    train = [sample for sample in raw_train if sample not in excluded]
    if not train or not test:
        raise DataContractError("Purge/embargo leaves an empty train or test fold")
    groups = {
        "train": train,
        "test": list(test),
        "purged": purged,
        "embargoed": embargoed,
        "raw_train": raw_train,
        "raw_test": list(test),
    }
    assigned: dict[str, tuple[str, str]] = {}
    for name, reason in (
        ("train", "strictly_before_test_information_boundary"),
        ("test", "forward_only_outer_test"),
        ("purged", "label_end_at_or_after_test_start_or_explicit_purge_gap"),
        ("embargoed", "additional_pre_test_embargo_after_label_purge"),
    ):
        for sample in groups[name]:
            if sample in assigned:
                raise DataContractError("Fold sample assigned to incompatible groups")
            assigned[sample] = (name, reason)
    result = {
        "fold_id": str(number),
        **{f"{name}_ids": ids for name, ids in groups.items()},
        "counts": {name: len(ids) for name, ids in groups.items()},
        "pairs": {name: _distribution(metadata, ids) for name, ids in groups.items()},
        "train_start": metadata.loc[train, "available_at"].min().isoformat(),
        "train_end": metadata.loc[train, "available_at"].max().isoformat(),
        "raw_train_start": metadata.loc[raw_train, "available_at"].min().isoformat(),
        "raw_train_end": metadata.loc[raw_train, "available_at"].max().isoformat(),
        "test_start": metadata.loc[test, "available_at"].min().isoformat(),
        "test_end": metadata.loc[test, "available_at"].max().isoformat(),
        "training_information_end": metadata.loc[train, "label_end_time"].max().isoformat(),
        "test_label_start": metadata.loc[test, "label_start_time"].min().isoformat(),
        "test_label_end": metadata.loc[test, "label_end_time"].max().isoformat(),
        "assignments": [
            {
                "sample_id": sample,
                "assignment": assigned.get(sample, ("outside_fold", "outside_fold_time_window"))[0],
                "reason": assigned.get(sample, ("outside_fold", "outside_fold_time_window"))[1],
            }
            for sample in development
        ],
        "input_metadata_sha256": _digest(_metadata_records(metadata.loc[development])),
    }
    result["sha256"] = _digest(result)
    return result


def _plan_record(
    metadata: pd.DataFrame,
    settings: ValidationConfig,
    start: pd.Timestamp,
    cut: int,
    development: list[str],
    holdout: list[str],
    guard: list[str],
    folds: list[dict],
) -> dict:
    holdout_set, guard_set = set(holdout), set(guard)
    records = _metadata_records(metadata)
    for record in records:
        sample = record["sample_id"]
        record["assignment"] = (
            "holdout"
            if sample in holdout_set
            else "guard_excluded"
            if sample in guard_set
            else "development"
        )
        record["reason"] = (
            "reserved_final_time_segment"
            if sample in holdout_set
            else "development_label_reaches_holdout_start"
            if sample in guard_set
            else "eligible_development_sample"
        )
    result = {
        "schema_version": 1,
        "scope": "development",
        "metadata_sha256": _digest(_metadata_records(metadata)),
        "validation": asdict(settings),
        "timeframe": "4h",
        "boundary_contract": "training label_end_time < test_start; development label_end_time < holdout_start",
        "embargo_contract": "additional N global timestamps before test; counted after purge",
        "holdout": {
            "start": start.isoformat(),
            "fraction": settings.final_holdout_fraction,
            "axis": "global_unique_available_at",
            "cut_index": cut,
            "total_timestamps": int(metadata.available_at.nunique()),
            "sample_ids": holdout,
            "excluded_development_ids": guard,
            "values_accessed": False,
            "historical_independence": "NOT_ESTABLISHED_BY_SPLIT_INFRASTRUCTURE",
        },
        "development_ids": development,
        "records": records,
        "folds": folds,
    }
    result["sha256"] = _digest(result)
    return result


def build_split_plan(metadata: pd.DataFrame, validation: dict) -> dict:
    """Reserve final global times and build complete development fold identities.

    No automatic prefix shortening, missing-bar filling or final-holdout target
    evaluation is performed. In walk-forward modes the existing splitter uses
    equal blocks after min_train_size; test_size applies only to fixed_holdout.
    """
    full = _checked_metadata(metadata)
    settings = _settings(validation)
    unique = pd.DatetimeIndex(full.available_at.unique())
    cut = int(len(unique) * (1 - settings.final_holdout_fraction))
    if cut < 2 or cut >= len(unique):
        raise DataContractError("Insufficient unshortened metadata for final holdout")
    boundary = unique[cut]
    holdout = _ids(full, full.available_at >= boundary)
    guard = _ids(full, (full.available_at < boundary) & (full.label_end_time >= boundary))
    eligible = full.loc[(full.available_at < boundary) & (full.label_end_time < boundary)]
    if eligible.empty:
        raise DataContractError("Holdout label guard leaves no development samples")
    times = pd.DatetimeIndex(eligible.available_at)
    dev_unique = times.unique()
    source = TimeSeriesSplitter(settings).split(times, eligible.label_end_time)
    folds = []
    for number, fold in enumerate(source):
        start = int(dev_unique.get_loc(fold.test_start))
        lower = (
            max(0, start - settings.train_window_size) if settings.method == "rolling_window" else 0
        )
        raw = _ids(eligible, (times >= dev_unique[lower]) & (times < fold.test_start))
        folds.append(
            _fold_record(
                full,
                number,
                raw,
                eligible.index[fold.test_indices].tolist(),
                eligible.index[fold.purged_indices].tolist(),
                eligible.index[fold.embargoed_indices].tolist(),
                eligible.index.tolist(),
            )
        )
    return _plan_record(
        full, settings, boundary, cut, eligible.index.tolist(), holdout, guard, folds
    )


def _reference_plan(full: pd.DataFrame, settings: ValidationConfig) -> dict:
    """Recompute groups without calling the production splitter or plan builder."""
    global_times = sorted(set(full.available_at))
    cut = int(len(global_times) * (1 - settings.final_holdout_fraction))
    if cut < 2 or cut >= len(global_times):
        raise DataContractError("Insufficient unshortened metadata for independent holdout")
    boundary = global_times[cut]
    development, holdout, guard = [], [], []
    for row in full.itertuples():
        if row.available_at >= boundary:
            holdout.append(row.sample_id)
        elif row.label_end_time >= boundary:
            guard.append(row.sample_id)
        else:
            development.append(row.sample_id)
    if not development:
        raise DataContractError("No independently eligible development samples")
    times = sorted(set(full.loc[development, "available_at"]))
    count = len(times)
    if settings.method == "fixed_holdout":
        windows = [(int(count * (1 - settings.test_size)), count)]
    else:
        first = settings.min_train_size or count // (settings.n_splits + 1)
        if first >= count or count - first < settings.n_splits:
            raise DataContractError("Insufficient timestamps for requested independent folds")
        width, extra = divmod(count - first, settings.n_splits)
        windows = []
        cursor = first
        for number in range(settings.n_splits):
            stop = cursor + width + int(number < extra)
            windows.append((cursor, stop))
            cursor = stop
    folds = []
    for number, (start, stop) in enumerate(windows):
        if start < 1 or stop <= start:
            raise DataContractError("Empty independent train/test window")
        lower = (
            max(0, start - settings.train_window_size) if settings.method == "rolling_window" else 0
        )
        raw_train, test, purged, embargoed = [], [], [], []
        for row in full.loc[development].itertuples():
            stamp = row.available_at
            if times[start] <= stamp <= times[stop - 1]:
                test.append(row.sample_id)
            if times[lower] <= stamp < times[start]:
                raw_train.append(row.sample_id)
                label_overlap = row.label_end_time >= times[start]
                explicit_gap = (
                    bool(settings.purge_candles)
                    and stamp >= times[max(0, start - settings.purge_candles)]
                )
                if label_overlap or explicit_gap:
                    purged.append(row.sample_id)
                elif (
                    settings.embargo_candles
                    and stamp >= times[max(0, start - settings.embargo_candles)]
                ):
                    embargoed.append(row.sample_id)
        folds.append(_fold_record(full, number, raw_train, test, purged, embargoed, development))
    return _plan_record(full, settings, boundary, cut, development, holdout, guard, folds)


def verify_split_plan(metadata: pd.DataFrame, validation: dict, plan: dict) -> dict:
    """Independently rederive every identity, boundary and assignment, not a subset.

    An external frozen research contract must also bind the original input and
    metadata fingerprint: replacing both a plan and its entire input cannot be
    detected from those two replaced objects alone.
    """
    full = _checked_metadata(metadata)
    expected = _reference_plan(full, _settings(validation))
    if not isinstance(plan, dict):
        raise DataContractError("Independent split verification requires a plan mapping")
    for key in expected:
        if key not in plan or plan[key] != expected[key]:
            raise DataContractError(f"Independent split verification mismatch: {key}")
    if set(plan) != set(expected):
        raise DataContractError("Independent split verification: unexpected plan fields")
    return {
        "status": "PASS",
        "scope": "development",
        "metadata_sha256": expected["metadata_sha256"],
        "plan_sha256": expected["sha256"],
        "sample_count": len(full),
        "fold_count": len(expected["folds"]),
        "holdout_count": len(expected["holdout"]["sample_ids"]),
        "guard_excluded_count": len(expected["holdout"]["excluded_development_ids"]),
        "training_label_boundary_violations": 0,
        "train_test_identity_overlaps": 0,
        "holdout_values_read": False,
        "formal_admission": "BLOCKED",
    }


class DevelopmentAccess:
    """Select development identities and log every allowed or denied operation.

    This is a scoped API boundary, not a claim that arbitrary user Python cannot
    read files. Metadata-only holdout identity registration is explicitly logged.
    """

    _PURPOSES = {"train", "fit", "transform", "tune", "predict", "metrics", "validation", "test"}

    def __init__(self, metadata: pd.DataFrame, plan: dict, audit_path: Path | None = None) -> None:
        if not isinstance(plan, dict):
            raise DataContractError("Development access requires a verified split plan mapping")
        verify_split_plan(metadata, plan.get("validation", {}), plan)
        self._metadata = _checked_metadata(metadata)
        self._allowed = frozenset(plan["development_ids"])
        self._reserved = frozenset(plan["holdout"]["sample_ids"])
        self._guard = frozenset(plan["holdout"]["excluded_development_ids"])
        self._plan_sha256 = plan["sha256"]
        self._audit_path = Path(audit_path) if audit_path is not None else None
        self.events: list[dict] = []
        self._record(
            "register_metadata",
            "registered",
            list(self._metadata.index),
            "metadata_identity_only; no feature, label or prediction values read",
        )

    def _record(self, purpose: str, status: str, sample_ids: list, reason: str) -> None:
        event = {
            "event_id": len(self.events),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scope": "development",
            "purpose": purpose,
            "status": status,
            "sample_ids": sample_ids,
            "reason": reason,
            "plan_sha256": self._plan_sha256,
        }
        self.events.append(event)
        if self._audit_path is not None:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")

    def select(self, frame: pd.DataFrame, sample_ids: list[str], purpose: str) -> pd.DataFrame:
        """Return an ordered defensive copy only after identity/holdout checks."""
        reason = None
        if not isinstance(sample_ids, list) or any(not isinstance(x, str) for x in sample_ids):
            reason = "sample_ids must be a list of string identities"
            ids: list = [str(sample_ids)]
        else:
            ids = sample_ids
        if reason is None and (not isinstance(purpose, str) or purpose not in self._PURPOSES):
            reason = "Unsupported development access purpose"
        if reason is None and (not ids or len(set(ids)) != len(ids)):
            reason = "Empty or duplicate requested sample identities"
        if reason is None and (set(ids) & (self._reserved | self._guard)):
            reason = "Holdout or label-boundary guard sample access is denied"
        if reason is None and not set(ids) <= self._allowed:
            reason = "Unknown or nondevelopment sample identity"
        if reason is None and (
            not isinstance(frame, pd.DataFrame)
            or not frame.index.is_unique
            or not set(ids) <= set(frame.index)
        ):
            reason = "Frame/request sample index is missing, duplicate or misaligned"
        if (
            reason is None
            and "sample_id" in frame
            and frame.index.tolist() != frame.sample_id.tolist()
        ):
            reason = "Frame sample_id column is not aligned with its identity index"
        if reason is not None:
            self._record(purpose, "denied", ids, reason)
            raise DataContractError(reason)
        self._record(purpose, "allowed", ids, "validated_development_identity_selection")
        return frame.loc[ids].copy()
