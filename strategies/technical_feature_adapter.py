"""Safe adapter for selected indicators from freqtrade/technical.

The adapter is deliberately explicit. It copies the input frame because some
upstream indicators mutate their input, and it excludes known unsafe or
ambiguous outputs such as Ichimoku chikou_span.

Upstream project:
  https://github.com/freqtrade/technical
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd
from pandas import DataFrame, Series


TECHNICAL_FEATURE_VERSION = "technical-v1-causal"
_REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


@dataclass(frozen=True, slots=True)
class TechnicalFeatureSpec:
    """One explicitly approved candidate feature."""

    name: str
    category: str
    period: int
    rationale: str


DEFAULT_TECHNICAL_FEATURE_SPECS = (
    TechnicalFeatureSpec("atr_percent_14", "volatility", 14, "normalized range risk"),
    TechnicalFeatureSpec("bollinger_width_20", "volatility", 20, "range expansion"),
    TechnicalFeatureSpec("bollinger_percent_b_20", "volatility", 20, "relative band position"),
    TechnicalFeatureSpec("chopiness_14", "regime", 14, "trend versus range state"),
    TechnicalFeatureSpec("rmi_20_5", "momentum", 20, "smoothed directional momentum"),
    TechnicalFeatureSpec("williams_percent_14", "momentum", 14, "bounded position momentum"),
    TechnicalFeatureSpec("supertrend_distance_10_3", "trend", 10, "volatility-aware trend distance"),
    TechnicalFeatureSpec("supertrend_direction_10_3", "trend", 10, "volatility-aware trend direction"),
    TechnicalFeatureSpec("vfi_130", "volume", 130, "volume flow state"),
    TechnicalFeatureSpec("vfi_hist_130_5", "volume", 130, "volume flow change"),
    TechnicalFeatureSpec("vwma_distance_20", "volume", 20, "volume-weighted price distance"),
)


def _normalise_series(series: Series, index: pd.Index) -> Series:
    """Return a numeric series aligned by position."""
    values = pd.to_numeric(pd.Series(series), errors="coerce").to_numpy()
    return pd.Series(values, index=index, dtype="float64")


def compute_technical_features(
    dataframe: DataFrame,
    feature_specs: tuple[TechnicalFeatureSpec, ...] = DEFAULT_TECHNICAL_FEATURE_SPECS,
) -> DataFrame:
    """Compute the approved causal technical feature candidates.

    Args:
        dataframe: One pair's chronologically ordered OHLCV frame.
        feature_specs: Explicit candidate list. Do not pass the whole upstream
            indicator catalogue into a model without a separate audit.

    Returns:
        A copy of ``dataframe`` with ``technical_<name>`` columns.

    Raises:
        ValueError: If required columns, ordering, or feature names are invalid.
        ImportError: If the optional ``technical`` package is not installed.
    """
    missing_columns = _REQUIRED_COLUMNS.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(f"missing OHLCV columns: {sorted(missing_columns)}")
    if not dataframe.index.is_monotonic_increasing:
        raise ValueError("dataframe index must be monotonically increasing")

    import technical.indicators as technical_indicators

    result = dataframe.copy()
    index = result.index
    feature_names = [spec.name for spec in feature_specs]
    if len(feature_names) != len(set(feature_names)):
        raise ValueError("feature_specs contains duplicate names")

    for spec in feature_specs:
        feature_name = f"technical_{spec.name}"
        if spec.name == "atr_percent_14":
            value = technical_indicators.atr_percent(result, period=spec.period) / 100.0
        elif spec.name == "bollinger_width_20":
            bands = technical_indicators.bollinger_bands(
                result.copy(), period=spec.period, stdv=2, field="close", colum_prefix="candidate_bb"
            )
            value = (bands["candidate_bb_upper"] - bands["candidate_bb_lower"]) / bands[
                "candidate_bb_middle"
            ]
        elif spec.name == "bollinger_percent_b_20":
            bands = technical_indicators.bollinger_bands(
                result.copy(), period=spec.period, stdv=2, field="close", colum_prefix="candidate_bb"
            )
            value = (result["close"] - bands["candidate_bb_lower"]) / (
                bands["candidate_bb_upper"] - bands["candidate_bb_lower"]
            )
        elif spec.name == "chopiness_14":
            value = technical_indicators.chopiness(result.copy(), period=spec.period)
        elif spec.name == "rmi_20_5":
            value = technical_indicators.RMI(result.copy(), length=20, mom=5)
        elif spec.name == "williams_percent_14":
            value = technical_indicators.williams_percent(result.copy(), period=spec.period)
        elif spec.name == "supertrend_distance_10_3":
            supertrend_value, _ = technical_indicators.supertrend(
                result.copy(), period=10, multiplier=3
            )
            value = (result["close"] - _normalise_series(supertrend_value, index)) / result[
                "close"
            ]
        elif spec.name == "supertrend_direction_10_3":
            _, direction = technical_indicators.supertrend(
                result.copy(), period=10, multiplier=3
            )
            value = pd.Series(direction, index=index).map({"up": 1.0, "down": -1.0})
        elif spec.name == "vfi_130":
            value, _, _ = technical_indicators.vfi(result.copy(), length=130, signalLength=5)
        elif spec.name == "vfi_hist_130_5":
            _, _, value = technical_indicators.vfi(result.copy(), length=130, signalLength=5)
        elif spec.name == "vwma_distance_20":
            value = result["close"] / technical_indicators.vwma(result.copy(), window=20) - 1.0
        else:
            raise ValueError(f"unsupported technical feature: {spec.name}")

        result[feature_name] = _normalise_series(value, index)

    return result


def validate_technical_features(dataframe: DataFrame) -> None:
    """Validate feature output before model training or inference."""
    feature_columns = [
        column for column in dataframe.columns if column.startswith("technical_")
    ]
    if not feature_columns:
        raise ValueError("no technical feature columns found")
    if dataframe[feature_columns].replace([float("inf"), float("-inf")], pd.NA).isna().all().all():
        raise ValueError("all technical feature values are missing")
