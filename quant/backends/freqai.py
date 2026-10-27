"""Adapt actual FreqAI start() lifecycle, without reimplementing its trainer.

Reference: https://www.freqtrade.io/en/stable/freqai-feature-engineering/
Verified against Freqtrade 2026.7 data_kitchen.populate_features and BaseRegressionModel.
"""

from typing import Any

import pandas as pd

from quant.config.schema import StrategyConfig
from quant.errors import UnsupportedCapabilityError
from quant.features import add_period_expanded_features
from quant.prediction import PredictionBatch, PredictionRecord

from .base import BackendCapabilities


def add_freqai_period_features(dataframe: pd.DataFrame, period: int) -> pd.DataFrame:
    """Keep legacy output names: FreqAI itself appends period/pair/timeframe.

    The research builder retains explicit periods. This adapter keeps production
    feature schema and cache compatibility while avoiding double period suffixes.
    """
    add_period_expanded_features(dataframe, period)
    return dataframe.rename(
        columns={
            c: c.removesuffix(f"-{period}")
            for c in dataframe
            if c.startswith("%") and c.endswith(f"-period-{period}")
        }
    )


class FreqAIBackendAdapter:
    """FreqAI owns splitting, preprocessing, training, persistence and predict."""

    def describe_capabilities(self) -> BackendCapabilities:
        """External walk-forward control and standalone save/load are unsupported."""
        return BackendCapabilities(False, True, False)

    def run_training(self, request: Any) -> None:
        """Reject requests that bypass FreqAI's framework-managed lifecycle."""
        raise UnsupportedCapabilityError(
            "FreqAI training must run through strategy.freqai.start(); use standalone for research splits"
        )

    def start(self, dataframe: pd.DataFrame, metadata: dict, strategy: Any) -> pd.DataFrame:
        """Delegate to the installed framework using its actual callback contract."""
        return strategy.freqai.start(dataframe, metadata, strategy)

    def predict(self, request: Any) -> PredictionBatch:
        """Require explicit metadata conversion instead of calling a fake predict."""
        raise UnsupportedCapabilityError("Use from_frame() to adapt FreqAI lifecycle output")

    def from_frame(
        self,
        dataframe: pd.DataFrame,
        pair: str,
        settings: StrategyConfig,
        *,
        model_name: str,
        model_version: str,
        experiment_id: str = "freqai",
        feature_version: str = "freqai-v1",
    ) -> PredictionBatch:
        """Convert framework predictions; unavailable training cutoff stays unknown."""
        records = tuple(
            PredictionRecord(
                pair=pair,
                candle_timestamp=pd.Timestamp(row.date),
                prediction=float(row.prediction) if pd.notna(row.prediction) else float("nan"),
                prediction_kind="raw_return" if settings.label == "raw" else "volnorm_return",
                model_name=model_name,
                model_version=model_version,
                feature_version=feature_version,
                label_mode=settings.label,
                prediction_horizon=settings.label_period_candles,
                is_ready=bool(pd.notna(row.do_predict) and row.do_predict == 1),
            )
            for row in dataframe[["date", "&-s_return", "do_predict"]]
            .rename(columns={"&-s_return": "prediction"})
            .itertuples(index=False)
        )
        return PredictionBatch(records, experiment_id, "freqai")
