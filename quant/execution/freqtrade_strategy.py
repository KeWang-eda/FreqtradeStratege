"""Freqtrade lifecycle adapter; indicators, labels and decisions live in core."""

from typing import Any

import pandas as pd
from freqtrade.exchange import timeframe_to_prev_date
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

from quant.backends.freqai import FreqAIBackendAdapter, add_freqai_period_features
from quant.config import StrategyConfig
from quant.features import add_baseline_features, add_basic_price_features
from quant.infrastructure.alignment_audit import AlignmentProbe
from quant.infrastructure.snapshot_store import (
    PredictionSnapshotStore,
    is_backtest_runmode,
)
from quant.labels import set_regression_target
from quant.portfolio import (
    PoolCandidate,
    TargetPosition,
    decide_position_action,
    resolve_target_position,
)
from quant.prediction import PredictionBatch

from .coordinator import candidates_from_batch
from .signals import read_model_prediction, should_enter_long, should_enter_short


class QuantStrategy(IStrategy):
    """Single-position, 4h regression strategy with unchanged risk parameters."""

    MAX_LIVE_SNAPSHOT_ROWS = 500
    timeframe = "4h"
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True
    minimal_roi = {"0": 999.0}
    stoploss = -1.0
    use_exit_signal = True
    trailing_stop = False

    def leverage(
        self,
        pair: str,
        current_time: Any,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> float:
        """Retain the strategy's leverage cap of two."""
        return min(2.0, float(max_leverage))

    @property
    def _exp(self) -> StrategyConfig:
        """Cache explicitly validated legacy experiment settings."""
        if getattr(self, "_exp_cache", None) is None:
            self._exp_cache = StrategyConfig.from_strategy(self.config, self.freqai_info)
        return self._exp_cache

    @property
    def _snapshots(self) -> PredictionSnapshotStore:
        """Use full replay history in backtests and bounded live snapshots."""
        if getattr(self, "_snapshot_store", None) is None:
            self._snapshot_store = PredictionSnapshotStore(
                self.MAX_LIVE_SNAPSHOT_ROWS, is_backtest_runmode(self.config)
            )
        return self._snapshot_store

    @property
    def _probe(self) -> AlignmentProbe:
        """Initialize the optional alignment audit only once."""
        if getattr(self, "_alignment_probe", None) is None:
            self._alignment_probe = AlignmentProbe(self._exp.probe)
        return self._alignment_probe

    def feature_engineering_expand_all(
        self, dataframe: pd.DataFrame, period: int, metadata: dict, **kwargs: Any
    ) -> pd.DataFrame:
        """Use the legacy FreqAI column schema; the framework expands periods."""
        return add_freqai_period_features(dataframe, period)

    def feature_engineering_expand_basic(
        self, dataframe: pd.DataFrame, metadata: dict, **kwargs: Any
    ) -> pd.DataFrame:
        """Append historical single-candle price and volume features."""
        return add_basic_price_features(dataframe)

    def feature_engineering_standard(
        self, dataframe: pd.DataFrame, metadata: dict, **kwargs: Any
    ) -> pd.DataFrame:
        """Append baseline features and validated optional indicators."""
        return add_baseline_features(dataframe, self._exp.features)

    def set_freqai_targets(
        self, dataframe: pd.DataFrame, metadata: dict, **kwargs: Any
    ) -> pd.DataFrame:
        """Write raw or ATR-normalized labels using the configured horizon."""
        return set_regression_target(dataframe, self._exp.label_period_candles, self._exp.label)

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Delegate the complete training/prediction lifecycle to FreqAI."""
        dataframe = FreqAIBackendAdapter().start(dataframe, metadata, self)
        self._snapshots.remember(metadata.get("pair"), dataframe)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Generate sign-based signals; global ranking gates the actual entry."""
        dataframe["enter_long"], dataframe["enter_short"] = 0, 0
        ready = dataframe["do_predict"] == 1
        prediction = read_model_prediction(dataframe)
        for mask, signal, tag in (
            (should_enter_long(prediction, ready), "enter_long", "reg_up"),
            (should_enter_short(prediction, ready), "enter_short", "reg_down"),
        ):
            dataframe.loc[mask, signal] = 1
            dataframe.loc[mask, "enter_tag"] = tag
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Keep exit signals empty; custom_exit owns rotation and exit reasons."""
        dataframe["exit_long"], dataframe["exit_short"] = 0, 0
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: Any,
        entry_tag: Any,
        side: str,
        **kwargs: Any,
    ) -> bool:
        """Only the selected pair and direction may enter."""
        target = self._target_position(current_time)
        return target is not None and target.pair == pair and target.side == side

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: Any,
        current_rate: float,
        current_profit: float,
        **kwargs: Any,
    ) -> str | None:
        """An incomplete snapshot defers decisions rather than forcing an exit."""
        target = self._target_position(current_time)
        if target is None:
            return None
        decision = decide_position_action(pair, "short" if trade.is_short else "long", target)
        return decision.reason

    def _target_position(self, evaluation_time: Any) -> TargetPosition | None:
        """Resolve one synchronized cross-pair target."""
        candidates = self._pool_candidates(evaluation_time)
        return None if candidates is None else resolve_target_position(candidates)

    def _pool_candidates(self, evaluation_time: Any) -> tuple[PoolCandidate, ...] | None:
        """Cache complete snapshots; retry incomplete snapshots on later calls."""
        timestamp = timeframe_to_prev_date(self.timeframe, evaluation_time)
        if getattr(self, "_pool_cache_timestamp", None) == timestamp:
            return self._pool_cache_value
        candidates = self._compute_candidates(timestamp)
        if candidates is not None:
            self._pool_cache_timestamp, self._pool_cache_value = timestamp, candidates
        return candidates

    def _compute_candidates(
        self, candle_timestamp: pd.Timestamp
    ) -> tuple[PoolCandidate, ...] | None:
        """Adapt exactly matching rows and let the coordinator check completeness."""
        pairs = tuple(self.dp.current_whitelist())
        rows = {pair: self._snapshots.get_row(pair, candle_timestamp) for pair in pairs}
        complete = bool(pairs) and all(row is not None for row in rows.values())
        records = []
        for pair, row_data in rows.items():
            row, row_count = row_data if row_data is not None else (None, 0)
            self._probe.record(
                pair=pair,
                candle_timestamp=candle_timestamp,
                last_candle_date=None if row is None else row["date"],
                row_count=row_count,
                raw_prediction=None if row is None else row["&-s_return"],
                complete=complete,
            )
            if row is not None:
                batch = FreqAIBackendAdapter().from_frame(
                    pd.DataFrame([row]),
                    pair,
                    self._exp,
                    model_name=self.config.get("freqaimodel", "unknown"),
                    model_version=self.config.get("freqai", {}).get("identifier", "unknown"),
                )
                records.extend(batch.records)
        return candidates_from_batch(
            PredictionBatch(tuple(records), "freqai", "freqai"), pairs, candle_timestamp
        )

    def _pair_candidate(self, pair: str, candle_timestamp: pd.Timestamp) -> PoolCandidate | None:
        """Compatibility helper returning an exact-time candidate."""
        from quant.portfolio import build_candidate

        row_data = self._snapshots.get_row(pair, candle_timestamp)
        if row_data is None:
            return None
        row, _ = row_data
        return build_candidate(pair, row["&-s_return"], row["do_predict"] == 1)
