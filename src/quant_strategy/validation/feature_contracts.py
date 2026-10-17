"""Reviewed feature dependencies plus executable tests for future information use.

References: repository features/momentum.py, price.py and technical.py; TA-Lib
RSI/EMA/ATR recursive definitions; technical 1.7.0 indicator implementations.
This module audits independent research features, not FreqAI's expanded schema.
"""

import importlib.metadata
import re
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from quant_strategy.config import ExperimentConfig
from quant_strategy.errors import DataContractError
from quant_strategy.features import build_features
from quant_strategy.market_data import validate_ohlcv
from quant_strategy.market_data.contracts import frame_fingerprint, validate_candle_grid
from quant_strategy.market_data.time_index import timeframe_delta

TOLERANCE = {"rtol": 0.0, "atol": 0.0}
FeatureBuilder = Callable[..., pd.DataFrame]


def _reviewed(
    sources: list[str], implementation: str, *, lookback: int = 0, recursive: bool = False
) -> dict[str, Any]:
    return {
        "status": "PASS",
        "sources": sources,
        "implementation": implementation,
        "earliest_dependency": {"kind": "segment_start"}
        if recursive
        else {
            "kind": "bounded_window",
            "offset_candles": -lookback,
            "clamp": "continuous segment start",
        },
        "latest_dependency": {"offset_candles": 0, "observation": "current candle close"},
        "available_at": "candle_open + timeframe",
        "recursive_from_segment_start": recursive,
    }


def _column_contract(column: str, config: ExperimentConfig) -> dict[str, Any]:
    match = re.fullmatch(
        r"%-(rsi|ema-distance|sma-distance|atr-ratio|relative-volume|momentum)-period-([0-9]+)",
        column,
    )
    if match and int(match[2]) in config.periods:
        name, period = match[1], int(match[2])
        if name in {"rsi", "ema-distance"}:
            return _reviewed(["close"], f"features/momentum.py:{name}", recursive=True)
        if name == "atr-ratio":
            return _reviewed(
                ["high", "low", "close"], "features/momentum.py:ATR/close", recursive=True
            )
        if name == "sma-distance":
            return _reviewed(["close"], "features/momentum.py:SMA/close", lookback=period - 1)
        if name == "relative-volume":
            return _reviewed(
                ["volume"], "features/momentum.py:volume/rolling_mean", lookback=period - 1
            )
        return _reviewed(["close"], "features/momentum.py:momentum", lookback=period)
    basic = {
        "%-return": (["close"], 1),
        "%-range": (["high", "low", "close"], 0),
        "%-body": (["open", "close"], 0),
        "%-volume-change": (["volume"], 1),
        "%-volatility-6": (["close"], 6),
        "%-volatility-24": (["close"], 24),
        "%-hour": (["date"], 0),
        "%-day-of-week": (["date"], 0),
    }
    if column in basic:
        sources, lookback = basic[column]
        return _reviewed(sources, "features/price.py or technical.py:" + column, lookback=lookback)
    optional = {
        "%-laguerre": ("laguerre", ["close"], True, 0),
        "%-vwmacd": ("vwmacd", ["close", "volume"], True, 0),
        "%-vwmacd-hist": ("vwmacd", ["close", "volume"], True, 0),
        "%-tke": ("tke", ["high", "low", "close", "volume"], True, 0),
        "%-tke-ema": ("tke", ["high", "low", "close", "volume"], True, 0),
        # Default VFI uses a 130-point sum of values whose volume limiter itself
        # uses the prior 130 observations: earliest dependency t-129-130=t-259.
        "%-vfi": ("vfi", ["high", "low", "close", "volume"], False, 259),
        "%-vfi-hist": ("vfi", ["high", "low", "close", "volume"], True, 0),
        "%-rmi": ("rmi", ["close"], True, 0),
    }
    if column in optional and optional[column][0] in config.features:
        try:
            technical_version = importlib.metadata.version("technical")
        except importlib.metadata.PackageNotFoundError:
            technical_version = None
        if technical_version != "1.7.0":
            return {
                "status": "BLOCKED",
                "reason": "Optional indicator dependency graph requires review for this technical version",
            }
        name, sources, recursive, lookback = optional[column]
        return _reviewed(
            sources,
            f"technical 1.7.0:{name}; repository defaults",
            lookback=lookback,
            recursive=recursive,
        )
    return {
        "status": "BLOCKED",
        "reason": "Unknown or unconfigured feature; no dependency declaration is invented",
    }


def build_feature_contracts(config: ExperimentConfig, columns: list[str]) -> dict[str, Any]:
    """Declare every actual feature column; labels and unknown schemas cannot pass."""
    if (
        not isinstance(columns, list)
        or not columns
        or any(not isinstance(column, str) for column in columns)
        or len(columns) != len(set(columns))
    ):
        return {
            "status": "FAIL",
            "feature_count": len(columns) if isinstance(columns, list) else 0,
            "columns": {},
            "issues": ["Feature schema must be a nonempty ordered list of unique names"],
        }
    contracts = {column: _column_contract(column, config) for column in columns}
    return {
        "schema_version": 1,
        "status": "BLOCKED"
        if any(value["status"] != "PASS" for value in contracts.values())
        else "PASS",
        "timeframe": config.timeframe,
        "feature_count": len(columns),
        "columns": contracts,
        "scope": "independent research feature schema; future labels excluded",
        "continuous_segments": "recursive state starts at each segment's first observed candle",
        "bounds_semantics": "earliest dependency is inclusive; latest values are unavailable until candle close",
    }


def _compute(
    builder: FeatureBuilder, frame: pd.DataFrame, config: ExperimentConfig
) -> pd.DataFrame:
    features = builder(
        frame.copy(deep=True), periods=config.periods, enabled_features=config.features
    )
    if (
        not isinstance(features, pd.DataFrame)
        or not features.index.equals(frame.index)
        or not features.columns.is_unique
        or not len(features.columns)
        or any(not isinstance(column, str) or not column.startswith("%") for column in features)
    ):
        raise DataContractError(
            "Feature builder must preserve rows/index and return unique feature columns only"
        )
    try:
        values = features.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise DataContractError("Feature builder returned nonnumeric data") from exc
    if np.isinf(values).any():
        raise DataContractError("Feature builder returned infinite values")
    return features


def _compare(expected: pd.DataFrame, actual: pd.DataFrame) -> list[dict[str, Any]]:
    if list(expected.columns) != list(actual.columns) or not expected.index.equals(actual.index):
        return [{"reason": "feature_schema_or_index_changed"}]
    differences = []
    for column in expected:
        left, right = expected[column], actual[column]
        equal = np.isclose(
            left.to_numpy(dtype=float), right.to_numpy(dtype=float), equal_nan=True, **TOLERANCE
        )
        if not equal.all() or left.dtype != right.dtype:
            comparable = np.isfinite(left.to_numpy(dtype=float)) & np.isfinite(
                right.to_numpy(dtype=float)
            )
            differences.append(
                {
                    "column": column,
                    "mismatched_rows": int((~equal).sum()),
                    "dtype_changed": left.dtype != right.dtype,
                    "maximum_absolute_difference": (
                        float(
                            np.max(
                                np.abs(
                                    left.to_numpy(dtype=float)[comparable]
                                    - right.to_numpy(dtype=float)[comparable]
                                )
                            )
                        )
                        if comparable.any()
                        else None
                    ),
                }
            )
    return differences


def audit_causality(
    frame: pd.DataFrame,
    config: ExperimentConfig,
    cut_points: list[int] | None = None,
    feature_builder: FeatureBuilder | None = None,
) -> dict[str, Any]:
    """Test all columns against prefix truncation and controlled future perturbation.

    Explicit cut points count rows retained in the global input prefix, and must
    fall strictly within a continuous segment. Default cuts sample each segment.
    Comparisons include NaN masks and require exact values (rtol=atol=0).
    This is finite empirical
    evidence, not a proof for all inputs. Labels are intentionally outside this audit.
    """
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "FAIL",
        "passed": False,
        "scope": "features only; future labels are outside this audit",
        "tolerance": dict(TOLERANCE),
        "checks": [],
        "differences": [],
        "issues": [],
        "segments": [],
        "segment_count": 0,
        "feature_count": 0,
        "finite_prefix_observations": {},
        "unverified_columns": [],
    }
    try:
        raw = validate_ohlcv(frame)
        validate_candle_grid(raw, config.timeframe)
        report["input_fingerprint"] = frame_fingerprint(raw)
        if cut_points is not None and (
            not isinstance(cut_points, list)
            or not cut_points
            or any(type(cut) is not int or not 0 < cut < len(raw) for cut in cut_points)
            or len(cut_points) != len(set(cut_points))
        ):
            raise DataContractError(
                "Cut points must be unique integer prefix lengths in (0, row_count)"
            )
        step = timeframe_delta(config.timeframe)
        segment_ids = raw.date.diff().ne(step).cumsum()
        builder = feature_builder or build_features
        unaudited_segments = []
        schema: list[str] | None = None
        for number, (_, original_segment) in enumerate(raw.groupby(segment_ids, sort=False)):
            offset = int(original_segment.index[0])
            segment = original_segment.reset_index(drop=True)
            full = _compute(builder, segment, config)
            if schema is None:
                schema = list(full)
                report["feature_count"] = len(schema)
                report["feature_contracts"] = build_feature_contracts(config, schema)
                report["finite_prefix_observations"] = dict.fromkeys(schema, 0)
            elif schema != list(full):
                raise DataContractError("Feature schema differs between continuous segments")
            local_cuts = (
                sorted(set(cut - offset for cut in cut_points if 0 < cut - offset < len(segment)))
                if cut_points is not None
                else sorted(
                    {
                        cut
                        for cut in (len(segment) // 3, 2 * len(segment) // 3, len(segment) - 1)
                        if 0 < cut < len(segment)
                    }
                )
            )
            report["segments"].append(
                {
                    "segment_id": number,
                    "start": segment.date.iloc[0].isoformat(),
                    "end": segment.date.iloc[-1].isoformat(),
                    "rows": len(segment),
                    "global_offset": offset,
                    "local_cut_points": local_cuts,
                    "finite_prefix_observations": dict.fromkeys(schema, 0),
                }
            )
            if not local_cuts:
                unaudited_segments.append(number)
            for cut in local_cuts:
                expected = full.iloc[:cut]
                for column in schema:
                    count = int(np.isfinite(expected[column]).sum())
                    report["finite_prefix_observations"][column] += count
                    report["segments"][-1]["finite_prefix_observations"][column] += count
                truncated = _compute(builder, segment.iloc[:cut], config)
                changed = segment.copy(deep=True)
                future = changed.index[cut:]
                scales = np.linspace(1.25, 2.0, len(future))
                changed.loc[future, ["open", "high", "low", "close"]] *= scales[:, None]
                changed.loc[future, "volume"] = changed.loc[future, "volume"] * 2.0 + 7.0
                perturbed = _compute(builder, changed, config).iloc[:cut]
                for kind, actual in (("truncation", truncated), ("future_perturbation", perturbed)):
                    differences = _compare(expected, actual)
                    context = {
                        "kind": kind,
                        "segment_id": number,
                        "global_cut": offset + cut,
                        "last_prefix_open": segment.date.iloc[cut - 1].isoformat(),
                    }
                    report["checks"].append({**context, "passed": not differences, "rows": cut})
                    report["differences"].extend({**context, **item} for item in differences)
        report["segment_count"] = len(report["segments"])
        report["unverified_columns"] = [
            column for column, count in report["finite_prefix_observations"].items() if count == 0
        ]
        report["unaudited_segments"] = unaudited_segments
        report["unverified_segment_columns"] = [
            {"segment_id": segment["segment_id"], "columns": missing}
            for segment in report["segments"]
            if (
                missing := [
                    column
                    for column, count in segment["finite_prefix_observations"].items()
                    if count == 0
                ]
            )
        ]
        if report["differences"]:
            report["status"] = "FAIL"
        elif (
            not report["checks"]
            or report["unverified_columns"]
            or unaudited_segments
            or report["unverified_segment_columns"]
            or report["feature_contracts"]["status"] != "PASS"
        ):
            report["status"] = "BLOCKED"
        else:
            report["status"], report["passed"] = "PASS", True
    except Exception as exc:
        # An indicator computation failure is itself an audit failure. Preserve its
        # type/message; never report success by dropping its columns or failed cuts.
        report["issues"].append({"type": type(exc).__name__, "message": str(exc)})
        report["status"], report["passed"] = "FAIL", False
    return report
