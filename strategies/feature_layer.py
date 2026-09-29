"""Causal feature layer for the clean-room Vtech framework.

The first model feature set preserves the historical 72-feature contract and
adds an explicitly allowlisted technical-indicator candidate pack. Features
are produced from closed candles only; future targets remain in label_layer.

References:
  - Historical Vtech FreqAI feature_engineering_* implementation on main.
  - FreqAI feature-engineering documentation.
  - freqtrade/technical audited adapter in technical_feature_adapter.py.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import pandas as pd
from pandas import DataFrame

from contracts import FeatureFrame, require_timezone_aware
from technical_feature_adapter import compute_technical_features


BASE_VTECH_FEATURE_COUNT = 72
MOMENTUM_FEATURE_COUNT = 6
TECHNICAL_CANDIDATE_FEATURE_COUNT = 11
MODEL_FEATURE_COUNT = (
    BASE_VTECH_FEATURE_COUNT + MOMENTUM_FEATURE_COUNT + TECHNICAL_CANDIDATE_FEATURE_COUNT
)
FEATURE_VERSION = "vtech-base72-plus-momentum6-plus-technical11-v1"
INDICATOR_PERIODS = (8, 20, 48)
HISTORY_SHIFTS = (0, 1, 2)
MOMENTUM_LOOKBACK_BARS = 20
MOMENTUM_LOOKBACK_PREV_BARS = 22
MOMENTUM_ANNUALIZE_BARS = 365 * 24  # 1h bars per year.


class FeatureLayer(Protocol):
    """Compute features without reading future bars."""

    def compute_causal_features(
        self, market_snapshot: Any, pair: str
    ) -> FeatureFrame:
        """Return one feature frame."""
        ...


def _require_columns(dataframe: DataFrame, columns: set[str]) -> None:
    """Reject incomplete market frames before feature construction."""
    missing_columns = columns.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(f"missing feature input columns: {sorted(missing_columns)}")


def _compress_signed_score(series: pd.Series) -> pd.Series:
    """Compress unstable exponential momentum while preserving direction."""
    clipped = series.clip(-1_000_000.0, 1_000_000.0).fillna(0.0)
    return np.sign(clipped) * np.log1p(clipped.abs())


def _calculate_weighted_log_regression_score(
    closes: pd.Series,
    window: int,
    annualize_bars: int,
) -> pd.Series:
    """Calculate causal weighted log-regression score.

    This first implementation is intentionally simple and auditable. It is
    O(number_of_bars * window); replace with the historical FFT implementation
    only after numerical equivalence tests exist.
    """
    values = closes.astype(float).to_numpy()
    scores = np.zeros(len(values), dtype=float)
    window_length = window + 1
    positions = np.arange(window_length, dtype=float)
    weights = np.linspace(1.0, 2.0, window_length)
    weight_total = weights.sum()
    weighted_position_mean = (weights * positions).sum() / weight_total
    denominator = (
        weights * (positions - weighted_position_mean) ** 2
    ).sum()

    for end_index in range(window_length, len(values)):
        window_values = values[end_index - window_length + 1 : end_index + 1]
        if np.any(~np.isfinite(window_values)) or np.any(window_values <= 0):
            continue
        log_values = np.log(window_values)
        weighted_mean = (weights * log_values).sum() / weight_total
        slope = (
            weights
            * (positions - weighted_position_mean)
            * (log_values - weighted_mean)
        ).sum() / denominator
        fitted_values = weighted_mean + slope * (
            positions - weighted_position_mean
        )
        total_sum_squares = (weights * (log_values - weighted_mean) ** 2).sum()
        if total_sum_squares <= 0:
            continue
        residual_sum_squares = (weights * (log_values - fitted_values) ** 2).sum()
        r_squared = max(0.0, 1.0 - residual_sum_squares / total_sum_squares)
        annualized_return = np.expm1(slope * annualize_bars)
        scores[end_index] = annualized_return * r_squared

    return pd.Series(scores, index=closes.index, dtype="float64")


def _add_vtech_momentum_features(dataframe: DataFrame) -> None:
    """Add the historical momentum and moving-average feature inputs."""
    close_series = dataframe["close"]
    raw_score = _calculate_weighted_log_regression_score(
        close_series, MOMENTUM_LOOKBACK_BARS, MOMENTUM_ANNUALIZE_BARS
    )
    previous_score = _calculate_weighted_log_regression_score(
        close_series, MOMENTUM_LOOKBACK_PREV_BARS, MOMENTUM_ANNUALIZE_BARS
    )
    recent_return = close_series.pct_change()
    drop_penalty = np.where(
        recent_return.rolling(4, min_periods=1).min() < -0.02, 0.5, 1.0
    )
    rise_penalty = np.where(
        recent_return.rolling(4, min_periods=1).max() > 0.02, 0.5, 1.0
    )

    dataframe["raw_mom_score"] = raw_score
    dataframe["raw_mom_score_prev"] = previous_score
    dataframe["mom_score"] = raw_score.clip(lower=0.0) * drop_penalty
    dataframe["mom_score_prev"] = previous_score.clip(lower=0.0) * drop_penalty
    dataframe["short_mom_score"] = (-raw_score).clip(lower=0.0) * rise_penalty
    dataframe["short_mom_score_prev"] = (-previous_score).clip(lower=0.0) * rise_penalty
    dataframe["ma20"] = close_series.rolling(20).mean()


def _add_expanded_indicator_features(dataframe: DataFrame) -> None:
    """Add the historical five-indicator, three-period, three-shift block."""
    import talib.abstract as ta

    for period in INDICATOR_PERIODS:
        indicator_values = {
            "rsi": ta.RSI(dataframe, timeperiod=period),
            "mfi": ta.MFI(dataframe, timeperiod=period),
            "roc": ta.ROC(dataframe, timeperiod=period),
            "atr_ratio": ta.ATR(dataframe, timeperiod=period) / dataframe["close"],
            "relative_volume": dataframe["volume"]
            / dataframe["volume"].rolling(period).mean(),
        }
        for name, values in indicator_values.items():
            for shift in HISTORY_SHIFTS:
                dataframe[f"%-{name}-{period}-shift{shift}"] = values.shift(shift)


def _add_expanded_basic_features(dataframe: DataFrame) -> None:
    """Add the historical four-basic-feature, three-shift block."""
    basic_values = {
        "return": dataframe["close"].pct_change(),
        "candle_body": dataframe["close"] / dataframe["open"] - 1.0,
        "candle_range": dataframe["high"] / dataframe["low"] - 1.0,
        "volume_change": dataframe["volume"].pct_change(),
    }
    for name, values in basic_values.items():
        for shift in HISTORY_SHIFTS:
            dataframe[f"%-{name}-shift{shift}"] = values.shift(shift)


def _add_standard_vtech_features(dataframe: DataFrame) -> None:
    """Add the historical 15 standard Vtech features."""
    required = {
        "date",
        "close",
        "volume",
        "raw_mom_score",
        "raw_mom_score_prev",
        "mom_score",
        "mom_score_prev",
        "short_mom_score",
        "short_mom_score_prev",
        "ma20",
    }
    _require_columns(dataframe, required)

    compressed_score = _compress_signed_score(dataframe["raw_mom_score"])
    compressed_score_previous = _compress_signed_score(
        dataframe["raw_mom_score_prev"]
    )
    momentum_penalty = np.where(
        dataframe["close"].pct_change().rolling(4, min_periods=1).min() < -0.02,
        0.5,
        1.0,
    )
    short_penalty = np.where(
        dataframe["close"].pct_change().rolling(4, min_periods=1).max() > 0.02,
        0.5,
        1.0,
    )
    return_series = dataframe["close"].pct_change()
    volume_change = dataframe["volume"].pct_change()
    volume_mean = volume_change.rolling(48).mean()
    volume_std = volume_change.rolling(48).std()

    dataframe["%-vtech-score"] = compressed_score
    dataframe["%-vtech-score-change"] = compressed_score - compressed_score_previous
    dataframe["%-vtech-ma-distance"] = dataframe["close"] / dataframe["ma20"] - 1.0
    dataframe["%-vtech-direction"] = (
        (dataframe["mom_score"] > 0).astype(float)
        - (dataframe["short_mom_score"] > 0).astype(float)
    )
    dataframe["%-volatility-8"] = return_series.rolling(8).std()
    dataframe["%-volatility-24"] = return_series.rolling(24).std()
    dataframe["%-hour"] = pd.to_datetime(dataframe["date"], utc=True).dt.hour
    dataframe["%-day-of-week"] = pd.to_datetime(
        dataframe["date"], utc=True
    ).dt.dayofweek
    funding = dataframe.get("funding", pd.Series(0.0, index=dataframe.index))
    dataframe["%-funding"] = funding
    dataframe["%-funding-ma-8h"] = funding.rolling(8, min_periods=1).mean()
    dataframe["%-funding-deviation"] = (
        dataframe["%-funding"] - dataframe["%-funding-ma-8h"]
    )
    dataframe["%-vtech-recent-drop-penalty"] = momentum_penalty
    dataframe["%-vtech-score-penalized"] = compressed_score * momentum_penalty
    dataframe["%-vtech-short-score-penalized"] = (
        _compress_signed_score(dataframe["short_mom_score"]) * short_penalty
    )
    dataframe["%-volume-change-zscore-48"] = (
        volume_change - volume_mean
    ) / volume_std.replace(0.0, np.nan)


def build_vtech_model_features(
    dataframe: DataFrame,
    include_technical_candidates: bool = True,
) -> DataFrame:
    """Build the historical 72 features plus optional technical candidates.

    The function does not modify ``dataframe``. It does not build labels and it
    does not call a model.
    """
    _require_columns(dataframe, {"date", "open", "high", "low", "close", "volume"})
    if not dataframe.index.is_monotonic_increasing:
        raise ValueError("feature input index must be monotonically increasing")

    result = dataframe.copy()
    _add_expanded_indicator_features(result)
    _add_expanded_basic_features(result)
    _add_vtech_momentum_features(result)
    _add_standard_vtech_features(result)

    base_features = [column for column in result.columns if column.startswith("%-")]
    if len(base_features) != BASE_VTECH_FEATURE_COUNT:
        raise AssertionError(
            f"expected {BASE_VTECH_FEATURE_COUNT} base features, got {len(base_features)}"
        )

    momentum_columns = {
        "raw_mom_score": "%-vtech-raw-mom-score",
        "raw_mom_score_prev": "%-vtech-raw-mom-score-prev",
        "mom_score": "%-vtech-mom-score",
        "mom_score_prev": "%-vtech-mom-score-prev",
        "short_mom_score": "%-vtech-short-mom-score",
        "ma20": "%-vtech-ma20",
    }
    raw_momentum = result["raw_mom_score"]
    raw_momentum_previous = result["raw_mom_score_prev"]
    stable_raw_momentum = _compress_signed_score(raw_momentum)
    stable_raw_momentum_previous = _compress_signed_score(raw_momentum_previous)
    result[momentum_columns["raw_mom_score"]] = stable_raw_momentum
    result[momentum_columns["raw_mom_score_prev"]] = stable_raw_momentum_previous
    result[momentum_columns["mom_score"]] = _compress_signed_score(result["mom_score"])
    result[momentum_columns["mom_score_prev"]] = _compress_signed_score(result["mom_score_prev"])
    result[momentum_columns["short_mom_score"]] = _compress_signed_score(result["short_mom_score"])
    result[momentum_columns["ma20"]] = result["ma20"]

    if include_technical_candidates:
        technical = compute_technical_features(result)
        for column in technical.columns:
            if column.startswith("technical_"):
                result[f"%-{column}"] = technical[column]

    return result


def validate_feature_frame(feature_frame: FeatureFrame) -> None:
    """Validate feature identity before model consumption."""
    require_timezone_aware(feature_frame.timestamp, "FeatureFrame.timestamp")
    if not feature_frame.pair:
        raise ValueError("FeatureFrame.pair must not be empty")
    if not feature_frame.feature_version:
        raise ValueError("FeatureFrame.feature_version must not be empty")
    if not feature_frame.values:
        raise ValueError("FeatureFrame.values must not be empty")
