"""Explicit, read-only source contracts for independent research.

Timestamps follow the repository's candle-open convention. Funding files contain
payment events: the storage timeframe never establishes their payment schedule.
These helpers do not change native Freqtrade loading or strategy behavior.
"""

import hashlib
import json
import math
from datetime import datetime
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd

from quant_strategy.errors import ConfigurationError, DataContractError
from quant_strategy.market_data.time_index import timeframe_delta

OHLCV_COLUMNS = ("date", "open", "high", "low", "close", "volume")


def _scalar(value: Any) -> Any:
    """Encode actual values, including signed zero/nonfinite values, without imputation."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime, np.datetime64)):
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC")
        return {"datetime_ns": timestamp.as_unit("ns").value}
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return {"float_hex": float(value).hex()}
    if isinstance(value, str):
        return value
    raise DataContractError(
        f"Unsupported scalar type in source fingerprint: {type(value).__name__}"
    )


def frame_fingerprint(frame: pd.DataFrame) -> str:
    """Hash ordered schema/dtypes/values; row positions, not pandas index labels, matter.

    Aware timestamps use canonical UTC nanoseconds, so ms/us/ns storage resolutions
    and equivalent timezone representations share identity. Numeric dtypes remain
    part of the schema. This is a content fingerprint, not proof of source authenticity.
    """
    if (
        not isinstance(frame, pd.DataFrame)
        or not frame.columns.is_unique
        or any(not isinstance(column, str) for column in frame.columns)
    ):
        raise DataContractError("Source fingerprint requires unique string column names")
    digest = hashlib.sha256()
    schema = []
    for column in frame:
        dtype = frame[column].dtype
        name = "datetime64[ns, UTC]" if isinstance(dtype, pd.DatetimeTZDtype) else str(dtype)
        schema.append({"column": column, "dtype": name})
    digest.update(json.dumps({"schema_version": 1, "schema": schema}, sort_keys=True).encode())
    for row in frame.itertuples(index=False, name=None):
        digest.update(b"\n")
        digest.update(
            json.dumps(
                [_scalar(value) for value in row],
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        )
    return digest.hexdigest()


def _dates(frame: pd.DataFrame) -> pd.DatetimeIndex:
    if "date" not in frame or not isinstance(frame["date"].dtype, pd.DatetimeTZDtype):
        raise DataContractError("Source dates must be timezone-aware datetimes")
    dates = pd.DatetimeIndex(frame["date"]).tz_convert("UTC").as_unit("ns")
    if dates.empty or dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise DataContractError("Source dates must be nonempty, nonmissing, unique and increasing")
    return dates


def _origin(timeframe: str) -> pd.Timestamp:
    # Exchange weekly candles start Monday, unlike the Unix epoch (Thursday).
    return pd.Timestamp("1970-01-05" if timeframe.endswith("w") else "1970-01-01", tz="UTC")


def validate_candle_grid(frame: pd.DataFrame, timeframe: str) -> None:
    """Reject off-grid and fractional-bar intervals; whole missing bars remain visible."""
    dates = _dates(frame)
    step = timeframe_delta(timeframe)
    offsets = dates.asi8 - _origin(timeframe).value
    if (offsets % step.value != 0).any():
        raise DataContractError("Candle timestamps are not aligned to the configured UTC grid")
    if len(dates) > 1 and (np.diff(dates.asi8) % step.value != 0).any():
        raise DataContractError("Candle intervals are not integer multiples of the timeframe")


def _bound(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise DataContractError("Expected range boundaries must be timezone-aware datetimes")
    return timestamp.tz_convert("UTC").as_unit("ns")


def _coverage(
    dates: pd.DatetimeIndex, step: pd.Timedelta, start: Any, end: Any, origin: pd.Timestamp
) -> dict[str, Any]:
    begin = dates[0] if start is None else _bound(start)
    finish = dates[-1] + step if end is None else _bound(end)
    if finish <= begin:
        raise DataContractError("Expected source range must increase")
    if (begin - origin) % step != pd.Timedelta(0) or (finish - origin) % step != pd.Timedelta(0):
        raise DataContractError("Expected source range must align with the declared event grid")
    intervals = []
    cursor = begin
    for timestamp in dates[(dates >= begin) & (dates < finish)]:
        if timestamp > cursor:
            intervals.append(
                {
                    "start": cursor.isoformat(),
                    "end_exclusive": timestamp.isoformat(),
                    "rows": int((timestamp - cursor) / step),
                }
            )
        cursor = timestamp + step
    if cursor < finish:
        intervals.append(
            {
                "start": cursor.isoformat(),
                "end_exclusive": finish.isoformat(),
                "rows": int((finish - cursor) / step),
            }
        )
    return {
        "expected_start": begin.isoformat(),
        "expected_end_exclusive": finish.isoformat(),
        "expected_rows": int((finish - begin) / step),
        "missing_rows": sum(item["rows"] for item in intervals),
        "missing_intervals": intervals,
    }


def audit_source(
    frame: pd.DataFrame,
    *,
    kind: str,
    timeframe: str,
    expected_start: Any = None,
    expected_end: Any = None,
    funding_interval_hours: float | None = None,
) -> dict[str, Any]:
    """Report PASS/PARTIAL/BLOCKED/FAIL without filling, dropping or sorting any row.

    Expected ranges are half-open. A supplied funding interval is an assertion by
    the caller, which must retain its schedule provenance separately. An observed
    modal interval is never promoted into a verified historical payment schedule.
    """
    funding = kind == "funding_rate"
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": kind,
        "timeframe": timeframe,
        "status": "FAIL",
        "raw_rows": len(frame),
        "issues": [],
        "missing_rows": None,
        "missing_intervals": [],
        "contract": {
            "timestamp": "UTC funding event time" if funding else "UTC candle open",
            "available_at": (
                "recorded funding event timestamp; publication delay not verified"
                if funding
                else "candle_open + timeframe"
            ),
            "value_units": (
                {
                    "open": "dimensionless funding fraction per payment event",
                    "high/low/close/volume": "native storage placeholders; not OHLC prices",
                }
                if funding
                else {
                    "open/high/low/close": "quote currency per base unit",
                    "volume": "exchange-defined raw candle volume",
                }
            ),
            "funding_interval_hours": (
                float(funding_interval_hours)
                if isinstance(funding_interval_hours, Real)
                and not isinstance(funding_interval_hours, bool)
                and math.isfinite(funding_interval_hours)
                else None
            ),
            "funding_schedule_source": "caller-declared; provenance required"
            if funding_interval_hours is not None
            else None,
            "fills_missing_values": False,
        },
    }
    try:
        if kind not in {"futures", "mark", "funding_rate"}:
            raise DataContractError("Unsupported source kind")
        timeframe_delta(timeframe)
        if not frame.columns.is_unique or set(OHLCV_COLUMNS) - set(frame.columns):
            raise DataContractError(
                "Source requires unique date/open/high/low/close/volume columns"
            )
        dates = _dates(frame)
        for column in OHLCV_COLUMNS[1:]:
            if not pd.api.types.is_numeric_dtype(frame[column]) or pd.api.types.is_bool_dtype(
                frame[column]
            ):
                raise DataContractError(f"Source column must have a numeric dtype: {column}")
        values = frame[list(OHLCV_COLUMNS[1:])].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise DataContractError("Source numeric values must be finite")
        if not funding:
            if (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
                raise DataContractError("Source prices must be positive and volume nonnegative")
            if (frame.high < frame[["open", "low", "close"]].max(axis=1)).any() or (
                frame.low > frame[["open", "high", "close"]].min(axis=1)
            ).any():
                raise DataContractError("Source OHLC bounds are inconsistent")
        report["fingerprint"] = frame_fingerprint(frame)
        report["start"] = dates[0].isoformat()
        report["end"] = dates[-1].isoformat()
        deltas = dates.to_series().diff().dropna()
        report["observed_interval_seconds"] = {
            str(int(delta.total_seconds())): int(count)
            for delta, count in deltas.value_counts().items()
        }
        if funding:
            if funding_interval_hours is None:
                report["status"] = "BLOCKED"
                report["issues"].append(
                    {
                        "code": "funding_schedule_missing",
                        "message": "Payment schedule not verified; storage timeframe and observed intervals do not establish it",
                    }
                )
                return report
            if (
                isinstance(funding_interval_hours, bool)
                or not isinstance(funding_interval_hours, Real)
                or not math.isfinite(funding_interval_hours)
                or funding_interval_hours <= 0
            ):
                raise DataContractError("Funding interval must be finite, positive hours")
            step = pd.Timedelta(hours=float(funding_interval_hours))
            if step <= pd.Timedelta(0):
                raise DataContractError("Funding interval must resolve to a positive duration")
            if ((dates.asi8 - dates[0].value) % step.value != 0).any():
                raise DataContractError("Funding events contradict the supplied fixed schedule")
            origin = dates[0]
        else:
            validate_candle_grid(frame, timeframe)
            step, origin = timeframe_delta(timeframe), _origin(timeframe)
        report.update(_coverage(dates, step, expected_start, expected_end, origin))
        report["status"] = "PARTIAL" if report["missing_rows"] else "PASS"
        if report["missing_rows"]:
            report["issues"].append(
                {
                    "code": "missing_observations",
                    "message": "Raw observations are absent; no rows or values were created",
                }
            )
    except (DataContractError, ConfigurationError, TypeError, ValueError, OverflowError) as exc:
        report["status"] = "FAIL"
        report["issues"].append({"code": "invalid_source_contract", "message": str(exc)})
    return report
