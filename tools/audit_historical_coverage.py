"""Read-only audit of raw local candles before native FreqAI backtesting.

Sources: installed Freqtrade DataProvider.get_required_startup,
Backtesting.load_bt_data/_load_bt_data_detail and IFreqaiModel.start_backtesting.
Those methods, rather than filename guesses, define prehistory and funding semantics.
No data handler fill/reindex, exchange instance, model directory or downloader is used.
"""

import argparse
import hashlib
import importlib.metadata
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OHLCV = ["date", "open", "high", "low", "close", "volume"]


def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def public_path(path: Path) -> str:
    """Reports never publish a workstation's absolute path or username."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "${EXTERNAL}/" + path.name


def iso(value) -> str:
    return pd.Timestamp(value).isoformat()


def missing_intervals(index: pd.DatetimeIndex, step: pd.Timedelta) -> list[dict]:
    """Compact exact missing timestamps into half-open intervals, without filling data."""
    if index.empty:
        return []
    groups = pd.Series(index).diff().ne(step).cumsum()
    return [
        {
            "start": iso(group.iloc[0]),
            "stop_exclusive": iso(group.iloc[-1] + step),
            "rows": len(group),
        }
        for _, group in pd.Series(index).groupby(groups)
    ]


def regular_coverage(
    dates: pd.DatetimeIndex, start: pd.Timestamp, stop: pd.Timestamp, step: pd.Timedelta
) -> dict:
    expected = pd.date_range(start, stop, freq=step, inclusive="left")
    missing = expected.difference(dates)
    return {
        "required_start": iso(start),
        "required_stop_exclusive": iso(stop),
        "expected_rows": len(expected),
        "missing_rows": len(missing),
        "missing_intervals": missing_intervals(missing, step),
        "complete": len(missing) == 0,
    }


def inspect_file(
    path: Path,
    kind: str,
    timeframe: str,
    start: pd.Timestamp,
    stop: pd.Timestamp,
    baseline_sha: str | None = None,
) -> tuple[dict, pd.DataFrame | None]:
    """Validate the raw file, retaining absent/invalid observations as audit failures."""
    from freqtrade.exchange import timeframe_to_seconds

    report = {
        "path": public_path(path),
        "kind": kind,
        "timeframe": timeframe,
        "exists": path.is_file(),
    }
    errors: list[str] = []
    report["errors"] = errors
    if not path.is_file():
        errors.append("missing_file")
        report["usable"] = False
        return report, None
    initial_sha = file_hash(path)
    report["sha256"] = initial_sha
    report["baseline_sha256"] = baseline_sha
    report["baseline_match"] = None if baseline_sha is None else initial_sha == baseline_sha
    if report["baseline_match"] is False:
        errors.append("changed_since_baseline")
    try:
        if path.suffix == ".feather":
            frame = pd.read_feather(path)
        elif path.suffix == ".parquet":
            frame = pd.read_parquet(path)
        else:
            raise ValueError("Unsupported raw format; expected feather or parquet")
    except Exception as exc:
        errors.append("unreadable_file:" + type(exc).__name__)
        report["usable"] = False
        return report, None
    report["rows"] = len(frame)
    report["columns"] = list(frame.columns)
    if list(frame.columns) != OHLCV:
        errors.append("invalid_ohlcv_schema")
    if frame.empty:
        errors.append("empty_file")
    if "date" not in frame or not isinstance(frame["date"].dtype, pd.DatetimeTZDtype):
        errors.append("date_requires_timezone_aware_datetime")
    elif str(frame["date"].dt.tz) != "UTC":
        errors.append("date_timezone_is_not_UTC")
    if errors and (frame.empty or "date" not in frame or "UTC" not in str(frame["date"].dtype)):
        report["usable"] = False
        return report, frame
    dates = pd.DatetimeIndex(frame["date"])
    report.update(
        start=iso(dates.min()),
        end=iso(dates.max()),
        timezone=str(dates.tz),
        duplicate_timestamps=int(dates.duplicated().sum()),
        sorted=dates.is_monotonic_increasing,
        null_timestamps=int(dates.isna().sum()),
    )
    if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        errors.append("invalid_time_index")
    if dates.isna().all():
        report["usable"] = False
        return report, frame
    numeric_errors = {}
    for column in OHLCV[1:]:
        if column not in frame or not pd.api.types.is_numeric_dtype(frame[column]):
            numeric_errors[column] = "missing_or_non_numeric"
        else:
            count = int((~np.isfinite(frame[column].to_numpy(dtype=float))).sum())
            if count:
                numeric_errors[column] = count
    report["invalid_numeric_values"] = numeric_errors
    if numeric_errors:
        errors.append("non_finite_or_non_numeric_values")
    if not numeric_errors:
        # Funding's rate is in open; the other OHLC fields are native zero placeholders.
        # Negative funding is valid. Do not apply positive-price/OHLC tests to it.
        if kind != "funding_rate":
            invalid = (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
            invalid |= frame["high"] < frame[["open", "close", "low"]].max(axis=1)
            invalid |= frame["low"] > frame[["open", "close", "high"]].min(axis=1)
            report["invalid_price_rows"] = int(invalid.sum())
            if invalid.any():
                errors.append("invalid_prices_or_ohlc_bounds")
        report["negative_volume_rows"] = int((frame["volume"] < 0).sum())
        if report["negative_volume_rows"]:
            errors.append("negative_volume")
    step = pd.Timedelta(seconds=timeframe_to_seconds(timeframe))
    deltas = dates.to_series().diff().dropna()
    report["observed_interval_seconds"] = {
        str(int(delta.total_seconds())): int(count)
        for delta, count in deltas.value_counts().items()
    }
    if kind == "funding_rate":
        report["cadence"] = (
            "uniform_observed_events"
            if len(deltas.unique()) == 1
            else "variable_requires_schedule_verification"
        )
        report["filename_timeframe_is_payment_cadence"] = False
        selected = dates[(dates >= start) & (dates < stop)]
        report["window_event_rows"] = len(selected)
        report["window_observed_interval_seconds"] = {
            str(int(delta.total_seconds())): int(count)
            for delta, count in selected.to_series().diff().dropna().value_counts().items()
        }
        if len(deltas.unique()) > 1:
            # These are observed transitions, never asserted missing payment events.
            different = deltas.ne(deltas.shift())
            report["observed_cadence_transitions"] = [
                {
                    "event_time": iso(timestamp),
                    "preceding_interval_seconds": int(delta.total_seconds()),
                }
                for timestamp, delta in deltas[different].items()
            ]
        if len(deltas.unique()) == 1 and len(deltas) and deltas.iloc[0] > pd.Timedelta(0):
            payment_step = deltas.iloc[0]
            # Preserve the real event phase; do not assume an hourly event or midnight start.
            offset = (start - dates[0]) % payment_step
            event_start = start if offset == pd.Timedelta(0) else start + payment_step - offset
            report["coverage"] = regular_coverage(dates, event_start, stop, payment_step)
        else:
            report["coverage"] = {
                "complete": False,
                "reason": "unknown_payment_schedule_no_events_inferred",
            }
            errors.append("funding_schedule_requires_verification")
        report["global_gaps"] = None
    else:
        valid_dates = dates.dropna().unique().sort_values()
        # pandas 3 preserves Feather's microsecond unit; normalize explicitly before
        # comparing integer epochs with Timedelta.value (nanoseconds).
        report["off_grid_rows"] = int(((dates.as_unit("ns").asi8 % step.value) != 0).sum())
        if report["off_grid_rows"]:
            errors.append("off_grid_timestamps")
        report["coverage"] = regular_coverage(valid_dates, start, stop, step)
        report["global_gaps"] = regular_coverage(valid_dates, dates.min(), dates.max() + step, step)
    if not report["coverage"]["complete"] and "reason" not in report["coverage"]:
        errors.append("incomplete_requested_window")
    report["changed_during_audit"] = initial_sha != file_hash(path)
    if report["changed_during_audit"]:
        errors.append("changed_during_audit")
    report["usable"] = not errors
    return report, frame


def load_requirements(
    config_paths: list[str], timerange: str, strategy_name: str
) -> tuple[dict, object, dict]:
    """Resolve native strategy/config/startup without constructing an exchange or FreqAI model."""
    from freqtrade.configuration import TimeRange
    from freqtrade.configuration.load_config import load_from_files
    from freqtrade.data.dataprovider import DataProvider
    from freqtrade.enums import CandleType, RunMode, TradingMode
    from freqtrade.exchange import timeframe_to_seconds
    from freqtrade.resolvers import StrategyResolver

    config = load_from_files(config_paths)
    if (
        config.get("trading_mode") != "futures"
        or config.get("exchange", {}).get("name") != "binance"
    ):
        raise ValueError("This audit supports the repository's Binance futures data layout only")
    if config.get("dataformat_ohlcv", "feather") not in {"feather", "parquet"}:
        raise ValueError("This audit reads unfilled Feather/Parquet files only")
    config.update(
        strategy=strategy_name,
        strategy_path=str(ROOT),
        user_data_dir=ROOT,
        runmode=RunMode.BACKTEST,
        trading_mode=TradingMode.FUTURES,
        candle_type_def=CandleType.FUTURES,
        timerange=timerange,
    )
    strategy = StrategyResolver.load_strategy(config)
    strategy.freqai_info = config.get("freqai", {})
    config["startup_candle_count"] = strategy.startup_candle_count
    timeframe = strategy.timeframe
    features = config.get("freqai", {}).get("feature_parameters", {})
    timeframes = list(dict.fromkeys([timeframe, *features.get("include_timeframes", [])]))
    provider = DataProvider(deepcopy(config), exchange=None)
    startup = {tf: provider.get_required_startup(tf) for tf in timeframes}
    tr = TimeRange.parse_timerange(timerange)
    if not tr.startts or not tr.stopts or tr.stopts <= tr.startts:
        raise ValueError("A closed, increasing timerange is required")
    requirements = {
        "timerange": timerange,
        "timeframe": timeframe,
        "include_timeframes": timeframes,
        "start": iso(tr.startdt),
        "stop_exclusive": iso(tr.stopdt),
        "strategy_startup_candles": strategy.startup_candle_count,
        "required_startup_candles": startup,
        "required_starts": {
            tf: iso(tr.startdt - pd.Timedelta(seconds=startup[tf] * timeframe_to_seconds(tf)))
            for tf in timeframes
        },
        "train_period_days": config.get("freqai", {}).get("train_period_days"),
        "backtest_period_days": config.get("freqai", {}).get("backtest_period_days"),
        "label_horizon_candles": features.get("label_period_candles", 1),
        "include_shifted_candles": features.get("include_shifted_candles", 0),
        "indicator_periods_candles": features.get("indicator_periods_candles", []),
    }
    return config, strategy, requirements


def audit_labels(frame: pd.DataFrame, strategy, requirements: dict, pair: str) -> dict:
    """Check real target callbacks on the same bounded training prefixes as native FreqAI."""
    from freqtrade.configuration import TimeRange
    from freqtrade.exchange import timeframe_to_seconds
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

    horizon = requirements["label_horizon_candles"]
    step = pd.Timedelta(seconds=timeframe_to_seconds(requirements["timeframe"]))
    start = pd.Timestamp(requirements["start"])
    stop = pd.Timestamp(requirements["stop_exclusive"])
    loaded = frame.loc[
        (frame.date >= pd.Timestamp(requirements["required_starts"][requirements["timeframe"]]))
        & (frame.date < stop)
    ].copy()
    endpoint = loaded.date.shift(-horizon)
    available = endpoint.notna()
    misaligned = int((endpoint[available] != loaded.date[available] + horizon * step).sum())
    # Avoid FreqaiDataKitchen.__init__: it creates model paths/config copies.
    # These two methods only read config and timeranges (verified in pinned source).
    kitchen = object.__new__(FreqaiDataKitchen)
    kitchen.config = {"timerange": requirements["timerange"]}
    full = TimeRange.parse_timerange(requirements["timerange"])
    full.startts -= int(requirements["train_period_days"] * 86400)
    train_ranges, _ = kitchen.split_timerange(
        full.timerange_str, requirements["train_period_days"], requirements["backtest_period_days"]
    )
    windows = []
    for tr in train_ranges:
        prefix = loaded.loc[loaded.date < tr.stopdt].copy()
        targets = strategy.set_freqai_targets(prefix, {"pair": pair})
        train = targets.loc[(targets.date >= tr.startdt) & (targets.date < tr.stopdt)]
        label_columns = [c for c in train.columns if c.startswith("&")]
        if len(label_columns) != 1:
            raise ValueError("Expected this strategy's one native regression target")
        column = label_columns[0]
        tails = train.tail(horizon)
        endpoints = prefix.date.shift(-horizon) + step
        finite = train.index[np.isfinite(train[column])]
        outside = int((endpoints.loc[finite] > pd.Timestamp(tr.stopdt)).sum())
        windows.append(
            {
                "start": iso(tr.startdt),
                "stop_exclusive": iso(tr.stopdt),
                "rows": len(train),
                "finite_labels": int(np.isfinite(train[column]).sum()),
                "missing_labels": int(train[column].isna().sum()),
                "tail_labels_remain_missing": len(tails) == horizon
                and bool(tails[column].isna().all()),
                "labels_outside_training_boundary": outside,
            }
        )
    expected_missing = all(
        w["tail_labels_remain_missing"]
        and w["missing_labels"] == horizon
        and w["labels_outside_training_boundary"] == 0
        for w in windows
    )
    return {
        "shift_horizon": horizon,
        "horizon_timestamp_misalignments": misaligned,
        "unavailable_last_loaded_labels": int(endpoint.isna().sum()),
        "training_windows": windows,
        "training_targets_checked_without_future_rows": True,
        "ready": misaligned == 0 and expected_missing and bool(windows) and start < stop,
    }


def audit(
    config_paths: list[str],
    timerange: str,
    strategy_name: str,
    baseline: Path,
    snapshot: Path,
    snapshot_max_age_days: float = 30,
    selected_pairs: list[str] | None = None,
) -> dict:
    from freqtrade.exchange import Exchange
    from freqtrade.misc import pair_to_filename

    from quant_strategy.execution.market_snapshot import load_snapshot

    config, strategy, req = load_requirements(config_paths, timerange, strategy_name)
    whitelist = config["exchange"]["pair_whitelist"]
    if selected_pairs and not set(selected_pairs) <= set(whitelist):
        raise ValueError("--pairs must be a subset of the configured static whitelist")
    trading_pairs = selected_pairs or whitelist
    corr_pairs = (
        config.get("freqai", {}).get("feature_parameters", {}).get("include_corr_pairlist", [])
    )
    pairs = list(dict.fromkeys([*trading_pairs, *corr_pairs]))
    initial = json.loads(baseline.read_text())
    baseline_hashes = {
        item["path"]: item["sha256"] for item in initial["files"] if item.get("sha256")
    }
    snapshot_value = json.loads(snapshot.read_text())
    # Validate all the recorded rules, separately from whether they cover all trading pairs.
    validated = load_snapshot(snapshot, snapshot_value["pairs"], snapshot_max_age_days)
    snapshot_pairs = set(validated["pairs"])
    stop, start = pd.Timestamp(req["stop_exclusive"]), pd.Timestamp(req["start"])
    mark_tf = Exchange._ft_has_default["mark_ohlcv_timeframe"]
    funding_tf = Exchange._ft_has_default["funding_fee_timeframe"]
    suffix = config.get("dataformat_ohlcv", "feather")
    datadir = Path(config["datadir"])
    file_reports, frames = {}, {}
    for pair in pairs:
        specs = [
            ("futures", tf, pd.Timestamp(req["required_starts"][tf]))
            for tf in req["include_timeframes"]
        ]
        if pair in trading_pairs:
            specs.extend([("mark", mark_tf, start), ("funding_rate", funding_tf, start)])
        for kind, tf, needed in specs:
            path = datadir / "futures" / f"{pair_to_filename(pair)}-{tf}-{kind}.{suffix}"
            item, frame = inspect_file(
                path, kind, tf, needed, stop, baseline_hashes.get(public_path(path))
            )
            key = (pair, kind, tf)
            file_reports[key] = item
            # Keep a rejected index in its file report, but never compare a naive,
            # non-datetime or invalid index to a valid correlated UTC timeline.
            frames[key] = (
                frame
                if item.get("timezone") == "UTC" and "invalid_time_index" not in item["errors"]
                else None
            )
    outcomes = []
    for pair in pairs:
        items = [value for (p, _, _), value in file_reports.items() if p == pair]
        data_ready = all(item["usable"] for item in items)
        alignment = []
        for tf in req["include_timeframes"]:
            base = frames[(pair, "futures", tf)]
            for corr in corr_pairs:
                related = frames[(corr, "futures", tf)]
                needed = pd.Timestamp(req["required_starts"][tf])
                base_dates = (
                    pd.DatetimeIndex([])
                    if base is None or "date" not in base
                    else pd.DatetimeIndex(base.date[(base.date >= needed) & (base.date < stop)])
                )
                corr_dates = (
                    pd.DatetimeIndex([])
                    if related is None or "date" not in related
                    else pd.DatetimeIndex(
                        related.date[(related.date >= needed) & (related.date < stop)]
                    )
                )
                missing = base_dates.difference(corr_dates)
                alignment.append(
                    {
                        "timeframe": tf,
                        "correlation_pair": corr,
                        "base_candles_missing_correlation": len(missing),
                    }
                )
        alignment_ready = all(item["base_candles_missing_correlation"] == 0 for item in alignment)
        related_ready = all(
            file_reports[(corr, "futures", tf)]["usable"]
            for corr in corr_pairs
            for tf in req["include_timeframes"]
        )
        frame = frames[(pair, "futures", req["timeframe"])]
        labels = (
            audit_labels(frame, strategy, req, pair)
            if frame is not None and file_reports[(pair, "futures", req["timeframe"])]["usable"]
            else {"ready": False, "reason": "raw_data_not_ready"}
        )
        funding_alignment = None
        if pair in trading_pairs:
            rates, marks = (
                frames[(pair, "funding_rate", funding_tf)],
                frames[(pair, "mark", mark_tf)],
            )
            if rates is not None and marks is not None and "date" in rates and "date" in marks:
                events = pd.DatetimeIndex(rates.date[(rates.date >= start) & (rates.date < stop)])
                unmatched = events.difference(pd.DatetimeIndex(marks.date))
                funding_alignment = {
                    "events": len(events),
                    "events_missing_mark_price": len(unmatched),
                    "ready": len(unmatched) == 0 and len(events) > 0,
                }
            else:
                funding_alignment = {"ready": False, "reason": "missing_funding_or_mark"}
        raw_ready = (
            data_ready
            and alignment_ready
            and related_ready
            and labels["ready"]
            and (funding_alignment is None or funding_alignment["ready"])
        )
        outcomes.append(
            {
                "pair": pair,
                "role": "trading" if pair in trading_pairs else "correlation_only",
                "raw_data_ready": raw_ready,
                "metadata_scope_ready": pair in snapshot_pairs,
                "offline_backtest_ready": raw_ready and pair in snapshot_pairs,
                "correlation_alignment": alignment,
                "correlation_history_ready": related_ready,
                "labels": labels,
                "funding_mark_alignment": funding_alignment,
                "files": items,
            }
        )
    minimum = [
        outcome for outcome in outcomes if outcome["pair"] in {"BTC/USDT:USDT", "ETH/USDT:USDT"}
    ]
    all_files = list(file_reports.values())
    minimum_ready = len(minimum) == 2 and all(item["offline_backtest_ready"] for item in minimum)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "versions": {
            key: importlib.metadata.version(key)
            for key in ["freqtrade", "ccxt", "pandas", "numpy", "pyarrow"]
        },
        "configs": [
            {"path": public_path(Path(path)), "sha256": file_hash(Path(path))}
            for path in config_paths
        ],
        "baseline": {"path": public_path(baseline), "sha256": file_hash(baseline)},
        "requirements": req,
        "trading_pairs": trading_pairs,
        "correlation_pairs": corr_pairs,
        "snapshot": {
            "path": public_path(snapshot),
            "file_sha256": file_hash(snapshot),
            "sha256": validated["sha256"],
            "acquired_at": validated["acquired_at"],
            "pairs": validated["pairs"],
            "versions": validated["versions"],
            "represents_historical_market_rules": False,
        },
        "pairs": outcomes,
        "minimum_scope_ready": minimum_ready,
        "minimum_scope": {
            "pairs": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "timerange": req["timerange"],
            "raw_data_ready": len(minimum) == 2 and all(item["raw_data_ready"] for item in minimum),
            "metadata_scope_ready": len(minimum) == 2
            and all(item["metadata_scope_ready"] for item in minimum),
        },
        "summary": {
            "pair_count": len(outcomes),
            "file_count": len(all_files),
            "existing_files": sum(item["exists"] for item in all_files),
            "raw_data_ready_pairs": sum(outcome["raw_data_ready"] for outcome in outcomes),
            "offline_backtest_ready_pairs": sum(
                outcome["offline_backtest_ready"] for outcome in outcomes
            ),
            "changed_since_baseline": sum(
                item.get("baseline_match") is False for item in all_files
            ),
            "changed_during_audit": sum(
                item.get("changed_during_audit", False) for item in all_files
            ),
            "minimum_scope_ready": minimum_ready,
            "all_requested_pairs_ready": all(
                outcome["offline_backtest_ready"]
                for outcome in outcomes
                if outcome["role"] == "trading"
            ),
            "all_requested_pairs_raw_ready": all(
                outcome["raw_data_ready"] for outcome in outcomes if outcome["role"] == "trading"
            ),
        },
        "limitations": [
            "Read-only preflight, not a claim that all pairs were backtested or trained.",
            "Current market snapshot is not a reconstruction of historical exchange/leverage rules.",
            "Funding event cadence is observed, not established by an archived exchange payment schedule.",
            "Native OHLCV/mark loading may fill missing candles; this audit does not fill or change them.",
            "No data download, zero-funding fallback, market-rule fabrication or strategy change.",
        ],
    }


def render_markdown(report: dict) -> str:
    rows = [
        "# 原始历史数据逐交易对覆盖表",
        "",
        f"生成时间：{report['generated_at']}。区间：`{report['requirements']['timerange']}`；停止时间不含。",
        "",
        "`raw` 包含训练预热、相关币对对齐、标签边界与 funding/mark 对齐。metadata 单列，不把行情文件存在当作可离线回测。",
        "",
        "| 交易对 | raw | metadata | 离线可用 | 缺口或限制 |",
        "|---|---|---|---|---|",
    ]
    for item in report["pairs"]:
        errors = []
        for file in item["files"]:
            if file["errors"]:
                errors.append(f"{file['path']}: {', '.join(file['errors'])}")
            for gap in file.get("coverage", {}).get("missing_intervals", []):
                errors.append(f"缺 [{gap['start']}, {gap['stop_exclusive']})，{gap['rows']}行")
        if not item["metadata_scope_ready"]:
            errors.append("不在当前可信市场快照范围")
        rows.append(
            f"| {item['pair']} | {item['raw_data_ready']} | {item['metadata_scope_ready']} | {item['offline_backtest_ready']} | {'；'.join(errors) or '无窗口缺口'} |"
        )
    rows.extend(
        [
            "",
            "## 文件范围与全历史质量",
            "",
            "| 文件 | 行数 | 起始 UTC | 最后 UTC | 重复 | 全历史缺失行/事件间隔 | SHA与Phase0一致 |",
            "|---|---:|---|---|---:|---|---|",
        ]
    )
    for item in report["pairs"]:
        for file in item["files"]:
            gaps = file.get("global_gaps")
            gaps_text = (
                str(gaps["missing_rows"])
                if gaps is not None
                else json.dumps(file.get("observed_interval_seconds", {}), ensure_ascii=False)
            )
            rows.append(
                f"| {file['path']} | {file.get('rows', 0)} | {file.get('start', 'missing')} | {file.get('end', 'missing')} | {file.get('duplicate_timestamps', 'N/A')} | {gaps_text} | {file.get('baseline_match')} |"
            )
    rows.extend(
        [
            "",
            "Funding 文件名 1h 是原生存储键，不表示每小时付款。变频事件明确待核实，不补造缺失事件。精确区间、非法值、标签及 SHA 见配套 JSON。",
            "",
        ]
    )
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", action="append", required=True, help="Native config merge order; repeatable"
    )
    parser.add_argument(
        "--timerange", required=True, help="Closed native timerange, e.g. 20250101-20250115"
    )
    parser.add_argument("--strategy", default="MyStrategy")
    parser.add_argument(
        "--pairs",
        nargs="+",
        help="Optional configured whitelist subset; correlation pairs remain required",
    )
    parser.add_argument(
        "--baseline", type=Path, default=Path("docs/acceptance/phase0_inventory.json")
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("docs/baseline/acceptance/binance-usdt-market-snapshot.json"),
    )
    parser.add_argument("--snapshot-max-age-days", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.config,
            args.timerange,
            args.strategy,
            args.baseline,
            args.snapshot,
            args.snapshot_max_age_days,
            args.pairs,
        )
    except Exception as exc:
        # Do not expose exception paths/config credentials in public audit output.
        print(
            f"Audit failed ({type(exc).__name__}); verify config, dependencies and snapshot locally"
        )
        return 2
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    if args.markdown:
        args.markdown.write_text(render_markdown(report))
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["all_requested_pairs_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
