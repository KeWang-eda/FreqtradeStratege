"""Cross-sectional XGBoost ranking model for same-timestamp asset selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
from pandas import DataFrame, Series
from xgboost import XGBRanker

from logging_config import get_layer_logger, log_failures, log_layer_event


LOGGER = get_layer_logger("rank_model")


@dataclass(frozen=True, slots=True)
class RankModelConfig:
    """Time-series panel ranking configuration."""

    validation_fraction: float = 0.2
    early_stopping_rounds: int = 50
    n_estimators: int = 400
    max_depth: int = 3
    learning_rate: float = 0.03
    min_child_weight: float = 16.0
    subsample: float = 0.85
    colsample_bytree: float = 0.70
    random_state: int = 42


@dataclass(frozen=True, slots=True)
class RankModelFitReport:
    """Auditable result of one panel ranker fit."""

    model_identifier: str
    feature_count: int
    train_rows: int
    validation_rows: int
    train_queries: int
    validation_queries: int
    best_iteration: int | None
    best_score: float | None


class CrossSectionalRankModel:
    """XGBoost LambdaMART model with one query group per timestamp."""

    def __init__(
        self,
        model_identifier: str,
        feature_columns: Sequence[str],
        config: RankModelConfig | None = None,
    ) -> None:
        if not model_identifier:
            raise ValueError("model_identifier must not be empty")
        if not feature_columns:
            raise ValueError("feature_columns must not be empty")
        self.model_identifier = model_identifier
        self.feature_columns = tuple(feature_columns)
        self.config = config or RankModelConfig()
        if not 0 < self.config.validation_fraction < 1:
            raise ValueError("validation_fraction must be between 0 and 1")
        self._model: XGBRanker | None = None
        self.fit_report: RankModelFitReport | None = None

    @staticmethod
    def _prepare_query_ids(timestamps: Series) -> np.ndarray:
        """Map sorted timestamps to contiguous query IDs."""
        values = pd.to_datetime(timestamps, utc=True)
        return values.factorize(sort=True)[0].astype(np.int64)

    @log_failures("rank_model")
    def fit(self, panel: DataFrame, target_column: str) -> RankModelFitReport:
        """Fit on complete timestamp groups with chronological validation."""
        required = {"timestamp", target_column, *self.feature_columns}
        missing = required.difference(panel.columns)
        if missing:
            raise ValueError(f"rank panel missing columns: {sorted(missing)}")
        frame = panel.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.sort_values(["timestamp", "pair" if "pair" in frame else "timestamp"])
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna(
            subset=[*self.feature_columns, target_column]
        )
        frame["__ranking_target__"] = (
            frame.groupby("timestamp")[target_column]
            .rank(method="first", ascending=True)
            .astype("int64")
            - 1
        )
        query_timestamps = frame["timestamp"].drop_duplicates().sort_values()
        split_index = int(len(query_timestamps) * (1.0 - self.config.validation_fraction))
        if split_index < 2 or len(query_timestamps) - split_index < 2:
            raise ValueError("time split leaves too few query groups")
        train_end = query_timestamps.iloc[split_index]
        train = frame[frame["timestamp"] < train_end]
        validation = frame[frame["timestamp"] >= train_end]
        train_qid = self._prepare_query_ids(train["timestamp"])
        validation_qid = self._prepare_query_ids(validation["timestamp"])
        if len(np.unique(train_qid)) < 2 or len(np.unique(validation_qid)) < 2:
            raise ValueError("ranker requires at least two query groups per split")

        model = XGBRanker(
            objective="rank:pairwise",
            eval_metric=["ndcg@1", "ndcg@3"],
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            min_child_weight=self.config.min_child_weight,
            subsample=self.config.subsample,
            colsample_bytree=self.config.colsample_bytree,
            tree_method="hist",
            n_jobs=1,
            random_state=self.config.random_state,
            early_stopping_rounds=self.config.early_stopping_rounds,
        )
        model.fit(
            train.loc[:, self.feature_columns],
            train["__ranking_target__"],
            qid=train_qid,
            eval_set=[
                (validation.loc[:, self.feature_columns], validation["__ranking_target__"])
            ],
            eval_qid=[validation_qid],
            verbose=False,
        )
        self._model = model
        self.fit_report = RankModelFitReport(
            model_identifier=self.model_identifier,
            feature_count=len(self.feature_columns),
            train_rows=len(train),
            validation_rows=len(validation),
            train_queries=len(np.unique(train_qid)),
            validation_queries=len(np.unique(validation_qid)),
            best_iteration=getattr(model, "best_iteration", None),
            best_score=getattr(model, "best_score", None),
        )
        log_layer_event(
            LOGGER,
            logging.INFO,
            "rank_model_fit_complete",
            model_identifier=self.model_identifier,
            feature_count=len(self.feature_columns),
            train_rows=len(train),
            validation_rows=len(validation),
            train_queries=len(np.unique(train_qid)),
            validation_queries=len(np.unique(validation_qid)),
            best_iteration=self.fit_report.best_iteration,
            best_score=self.fit_report.best_score,
        )
        return self.fit_report

    @log_failures("rank_model")
    def predict(self, panel: DataFrame) -> Series:
        """Return comparable within-timestamp ranking scores."""
        if self._model is None:
            raise RuntimeError("rank model must be fitted before prediction")
        missing = set(self.feature_columns).difference(panel.columns)
        if missing:
            raise ValueError(f"rank panel missing prediction features: {sorted(missing)}")
        values = self._model.predict(panel.loc[:, self.feature_columns])
        return Series(values, index=panel.index, dtype="float64")
