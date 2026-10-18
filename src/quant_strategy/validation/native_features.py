"""Run actual native feature expansion against explicitly supplied local candles.

Sources: installed Freqtrade 2026.7 data_kitchen.populate_features and
use_strategy_to_populate_indicators; strategy.merge_informative_pair (the
informative candle is available only at its close); repository QuantStrategy
feature callbacks and PredictionSnapshotStore's exact-time selection. This is
an audit adapter, not a replacement feature implementation or model trainer.
"""

import hashlib
import importlib.metadata
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from quant_strategy.errors import DataContractError
from quant_strategy.market_data import validate_ohlcv
from quant_strategy.market_data.contracts import frame_fingerprint, validate_candle_grid
from quant_strategy.market_data.time_index import timeframe_delta

FrameKey = str | tuple[str, str]
Frames = Mapping[FrameKey, pd.DataFrame]
Populator = Callable[[dict, Frames, str], pd.DataFrame]

_PERIOD_FEATURES = (
    "rsi",
    "ema-distance",
    "sma-distance",
    "atr-ratio",
    "relative-volume",
    "momentum",
)
_BASIC_FEATURES = ("return", "range", "body", "volume-change")
_STANDARD_FEATURES = ("volatility-6", "volatility-24", "hour", "day-of-week")


def _normalized(config: dict, frames: Frames, pair: str) -> dict[tuple[str, str], pd.DataFrame]:
    """Validate every needed source; never fill gaps or fetch absent frames."""
    tf = config["timeframe"]
    timeframes = config["freqai"]["feature_parameters"]["include_timeframes"]
    if not timeframes or tf not in timeframes or len(set(timeframes)) != len(timeframes):
        raise DataContractError(
            "Native audit requires unique include_timeframes containing base tf"
        )
    sources = [pair, *config["freqai"]["feature_parameters"].get("include_corr_pairlist", [])]
    result = {}
    for source in dict.fromkeys(sources):
        for timeframe in timeframes:
            key = (source, timeframe)
            value = frames.get(key)
            if value is None and timeframe == tf:
                value = frames.get(source)
            if value is None or value.empty:
                raise DataContractError(
                    f"Missing local native feature source: {source} {timeframe}"
                )
            current = validate_ohlcv(value)
            validate_candle_grid(current, timeframe)
            if not current.date.diff().dropna().eq(timeframe_delta(timeframe)).all():
                raise DataContractError(f"Native audit refuses unquarantined candle gaps: {source}")
            result[key] = current
    return result


def populate_native_features(config: dict, frames: Frames, pair: str) -> pd.DataFrame:
    """Expand the real strategy with the installed FreqaiDataKitchen, entirely local.

    A string key means (pair, base timeframe); tuple keys support explicitly
    supplied informative timeframes. Missing local data fails rather than
    falling back to a DataProvider or exchange. live=True selects the framework's
    target/name-normalization branch without starting live trading or training.
    """
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

    from quant_strategy.execution.freqtrade_strategy import QuantStrategy

    current = deepcopy(config)
    values = _normalized(current, frames, pair)
    strategy = QuantStrategy(current)
    strategy.freqai_info = current["freqai"]
    kitchen = FreqaiDataKitchen(current, live=True, pair=pair)
    base = {tf: value.copy() for (source, tf), value in values.items() if source == pair}
    corr = {
        source: {tf: value.copy() for (name, tf), value in values.items() if name == source}
        for source in current["freqai"]["feature_parameters"].get("include_corr_pairlist", [])
    }
    populated = kitchen.use_strategy_to_populate_indicators(
        strategy, base_dataframes=base, corr_dataframes=corr, pair=pair
    )
    if not populated.columns.is_unique:
        raise DataContractError("Native feature expansion produced duplicate columns")
    return populated


def _feature_contracts(
    config: dict, pair: str, columns: Sequence[str] | None = None
) -> dict[str, dict]:
    """Account for actual FreqAI naming, period/shift/source and close availability."""
    params = config["freqai"]["feature_parameters"]
    expected: dict[str, dict] = {}
    sources = list(dict.fromkeys([pair, *params.get("include_corr_pairlist", [])]))
    for source in sources:
        for tf in params["include_timeframes"]:
            for shift in range(params.get("include_shifted_candles", 0) + 1):
                specs = [
                    (f"%-{name}-period_{period}", name, period)
                    for period in params["indicator_periods_candles"]
                    for name in _PERIOD_FEATURES
                ] + [(f"%-{name}_gen", name, None) for name in _BASIC_FEATURES]
                for prefix, name, period in specs:
                    column = (
                        prefix + (f"_shift-{shift}" if shift else "") + f"_{source}_{tf}"
                    ).replace(":", "")
                    recursive = name in {"rsi", "ema-distance", "atr-ratio"}
                    if recursive:
                        earliest = {"kind": "source_segment_start"}
                    else:
                        bars = (
                            period
                            if name == "momentum"
                            else period - 1
                            if period is not None
                            else 1
                            if name in {"return", "volume-change"}
                            else 0
                        )
                        earliest = {"offset_source_candles": -(bars + shift)}
                    expected[column] = {
                        "status": "PASS",
                        "source_pair": source,
                        "source_timeframe": tf,
                        "rule": name,
                        "period": period,
                        "shift": shift,
                        "earliest_dependency": earliest,
                        "latest_dependency": {"offset_source_candles": -shift},
                        "available_at": "source_candle_open + source_timeframe; merge at base close",
                        "recursive_from_segment_start": recursive,
                        "cross_pair": source != pair,
                    }
    for name in _STANDARD_FEATURES:
        expected[f"%-{name}"] = {
            "status": "PASS",
            "source_pair": pair,
            "source_timeframe": config["timeframe"],
            "rule": name,
            "shift": 0,
            "earliest_dependency": {
                "offset_source_candles": -int(name.split("-")[-1])
                if name.startswith("volatility-")
                else 0
            },
            "latest_dependency": {"offset_source_candles": 0},
            "available_at": "base_candle_open + base_timeframe",
            "recursive_from_segment_start": False,
            "cross_pair": False,
        }
    if columns is None:
        return expected
    return {
        column: expected.get(column, {"status": "BLOCKED", "reason": "Unreviewed native feature"})
        for column in columns
    }


def _prefix_difference(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    columns: Sequence[str],
    cutoff: pd.Timestamp,
    base_tf: str,
) -> list[dict]:
    """Compare by immutable candle identity, including missing-value masks."""
    original = baseline.loc[baseline.date + timeframe_delta(base_tf) <= cutoff].set_index("date")
    current = candidate.loc[candidate.date + timeframe_delta(base_tf) <= cutoff].set_index("date")
    if list(current.columns) != list(original.columns) or not current.index.equals(original.index):
        return [{"column": "__schema_or_sample_identity__", "maximum_absolute_difference": None}]
    result = []
    for column in columns:
        left = original[column].to_numpy(dtype=float)
        right = current[column].to_numpy(dtype=float)
        equal = (left == right) | (np.isnan(left) & np.isnan(right))
        if not equal.all():
            finite = np.isfinite(left) & np.isfinite(right) & ~equal
            result.append(
                {
                    "column": column,
                    "changed_observations": int((~equal).sum()),
                    "maximum_absolute_difference": float(
                        np.max(np.abs(left[finite] - right[finite]))
                    )
                    if finite.any()
                    else None,
                }
            )
    return result


def _mutate_future(
    values: Mapping[tuple[str, str], pd.DataFrame],
    cutoff: pd.Timestamp,
    *,
    keep_pair: str | None = None,
    truncate: bool = False,
) -> dict[tuple[str, str], pd.DataFrame]:
    result = {}
    for (source, tf), frame in values.items():
        after = frame.date + timeframe_delta(tf) > cutoff
        if truncate:
            result[source, tf] = frame.loc[~after].copy().reset_index(drop=True)
            continue
        current = frame.copy()
        if source != keep_pair:
            current.loc[after, ["open", "high", "low", "close"]] *= 3.718
            current.loc[after, "volume"] = current.loc[after, "volume"] * 7.123 + 13
        result[source, tf] = current
    return result


def audit_native_features(
    config: dict,
    frames: Frames,
    *,
    pairs: Sequence[str] | None = None,
    cut_points: Sequence[int] | None = None,
    populator: Populator = populate_native_features,
) -> dict[str, Any]:
    """Exercise every expanded column on full, future-perturbed and truncated input.

    Exact equality is required because each comparison retains the same prefix,
    indicator initialization and software. Labels intentionally observe the
    future and are excluded. A callback exists for isolated fault injection;
    production audit defaults to the actual native pipeline above.
    """
    universe = config.get("exchange", {}).get("pair_whitelist", [])
    requested = list(pairs if pairs is not None else universe)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "BLOCKED",
        "audited_pairs": requested,
        "configured_pair_count": len(universe),
        "pairs": {},
        "differences": [],
        "tolerance": {"rtol": 0.0, "atol": 0.0},
        "cut_points": list(cut_points) if cut_points is not None else None,
        "scope": "Native full configured feature expansion; future labels are excluded",
        "pipeline": "FreqaiDataKitchen.use_strategy_to_populate_indicators(live=True)",
        "configuration_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode()
        ).hexdigest(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("freqtrade", "numpy", "pandas", "TA-Lib")
        },
        "ranking_scope": "Exact-time snapshot/coordinator ranking has a separate runtime audit",
        "universe_scope": "Frozen current StaticPairList, not evidence of historical listing membership or absence of survivorship bias",
        "label_contract": {
            "mode": config.get("my_experiment", {}).get("label", "raw"),
            "horizon": config["freqai"]["feature_parameters"]["label_period_candles"],
            "label_end": "future horizon candle CLOSE, inclusive",
        },
    }
    if config.get("pairlists") != [{"method": "StaticPairList"}] and any(
        value.get("method") != "StaticPairList" for value in config.get("pairlists", [])
    ):
        report["reason"] = "Only StaticPairList has a frozen historical universe contract"
        return report
    if not config.get("pairlists") or not requested or len(set(requested)) != len(requested):
        report.update(status="FAIL", reason="Empty or duplicate audit universe")
        return report
    if any(pair not in universe for pair in requested):
        report.update(status="FAIL", reason="Audit pair is outside configured universe")
        return report
    for pair in requested:
        try:
            values = _normalized(config, frames, pair)
            full = populator(config, values, pair)
            columns = [column for column in full if column.startswith("%")]
            contracts = _feature_contracts(config, pair, columns)
            missing_expected = sorted(set(_feature_contracts(config, pair)) - set(columns))
            cuts = list(cut_points) if cut_points is not None else [len(full) // 2, len(full) - 20]
            if not cuts or any(
                type(cut) is not int or cut < 1 or cut >= len(full) - 1 for cut in cuts
            ):
                raise DataContractError("Native audit cutoff must be inside actual candle history")
            if not columns or not full.columns.is_unique:
                raise DataContractError("Empty or duplicate native feature schema")
            if not np.isfinite(full[columns].replace(np.nan, 0).to_numpy(dtype=float)).all():
                raise DataContractError("Native feature output contains infinity")
            observations = {column: 0 for column in columns}
            checks = []
            for cut in cuts:
                cutoff = full.date.iloc[cut] + timeframe_delta(config["timeframe"])
                prefix = full.loc[full.date + timeframe_delta(config["timeframe"]) <= cutoff]
                for column in columns:
                    observations[column] += int(np.isfinite(prefix[column]).sum())
                for kind in ("future_perturbation", "truncation", "correlated_future_perturbation"):
                    changed = _mutate_future(
                        values,
                        cutoff,
                        truncate=kind == "truncation",
                        keep_pair=pair if kind == "correlated_future_perturbation" else None,
                    )
                    other = populator(config, changed, pair)
                    differences = _prefix_difference(
                        full, other, columns, cutoff, config["timeframe"]
                    )
                    checks.append(
                        {
                            "kind": kind,
                            "cutoff_available_at": cutoff.isoformat(),
                            "passed": not differences,
                        }
                    )
                    report["differences"].extend(
                        {"pair": pair, "kind": kind, "cutoff": cutoff.isoformat(), **value}
                        for value in differences
                    )
            unverified = [
                column
                for column, count in observations.items()
                if count == 0 or contracts[column]["status"] != "PASS"
            ]
            unverified.extend(f"missing:{column}" for column in missing_expected)
            report["pairs"][pair] = {
                "status": "FAIL"
                if any(not value["passed"] for value in checks)
                else "BLOCKED"
                if unverified
                else "PASS",
                "feature_count": len(columns),
                "columns": columns,
                "contracts": contracts,
                "missing_expected_columns": missing_expected,
                "checks": checks,
                "unverified_columns": unverified,
                "finite_prefix_observations": observations,
                "input_fingerprints": {
                    f"{source}|{tf}": frame_fingerprint(value)
                    for (source, tf), value in values.items()
                },
                "populated_feature_sha256": frame_fingerprint(full[["date", *columns]]),
                "candle_start": full.date.iloc[0].isoformat(),
                "candle_end": full.date.iloc[-1].isoformat(),
                "candle_count": len(full),
            }
        except (DataContractError, KeyError, TypeError, ValueError) as exc:
            report["pairs"][pair] = {"status": "FAIL", "reason": str(exc)}
    statuses = [value["status"] for value in report["pairs"].values()]
    report["status"] = (
        "FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses else "PASS"
    )
    report["all_configured_pairs_audited"] = requested == universe
    return report


def _snapshot_target(
    config: dict, predictions: Mapping[str, pd.DataFrame], timestamp: pd.Timestamp
) -> Any:
    from quant_strategy.execution.freqtrade_strategy import QuantStrategy

    class LocalUniverse:
        def current_whitelist(self) -> list[str]:
            return list(config["exchange"]["pair_whitelist"])

    strategy = QuantStrategy(deepcopy(config))
    strategy.freqai_info = config["freqai"]
    strategy.dp = LocalUniverse()
    for pair, frame in predictions.items():
        strategy._snapshots.remember(pair, frame)
    target = strategy._target_position(timestamp)
    return None if target is None or target.pair is None else asdict(target)


def audit_snapshot_ranking(
    config: dict,
    predictions: Mapping[str, pd.DataFrame],
    timestamp: pd.Timestamp,
    *,
    evaluator: Callable[[dict, Mapping[str, pd.DataFrame], pd.Timestamp], Any] = _snapshot_target,
) -> dict:
    """Run real snapshot/coordinator/ranking with future prediction changes.

    These inputs are predictions, not mock market data. Passing test-generated
    predictions tests selection only; it never claims a model training result.
    A real-training caller can supply its actual native prediction artifacts.
    """
    configured = config["exchange"]["pair_whitelist"]
    if set(configured) != set(predictions) or not configured:
        return {
            "status": "BLOCKED",
            "reason": "Ranking needs complete configured prediction universe",
        }
    changed, truncated = {}, {}
    for position, pair in enumerate(configured):
        frame = predictions[pair]
        if not {"date", "&-s_return", "do_predict"} <= set(frame):
            return {"status": "FAIL", "reason": "Missing ranking prediction fields"}
        if frame.date.duplicated().any() or not (frame.date == timestamp).any():
            return {"status": "FAIL", "reason": "Ambiguous or missing exact-time prediction"}
        changed[pair] = frame.copy()
        changed[pair].loc[frame.date > timestamp, "&-s_return"] = (len(configured) - position) * 1e9
        truncated[pair] = frame.loc[frame.date <= timestamp].copy()
    baseline = evaluator(config, predictions, timestamp)
    if baseline is None:
        return {"status": "BLOCKED", "reason": "No usable current-time ranking observation"}
    checks = {
        "future_perturbation": baseline == evaluator(config, changed, timestamp),
        "truncation": baseline == evaluator(config, truncated, timestamp),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "timestamp": timestamp.isoformat(),
        "checks": checks,
        "target": baseline,
        "pair_count": len(configured),
        "scope": "Actual QuantStrategy snapshots/coordinator/ranking; supplied predictions only",
    }
