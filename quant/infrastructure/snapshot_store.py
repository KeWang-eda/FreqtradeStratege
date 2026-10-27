"""Exact-time, per-strategy prediction storage with bounded live history."""

import pandas as pd


def is_backtest_runmode(config: dict) -> bool:
    """Backtest/hyperopt need complete prediction history for framework replay."""
    mode = config.get("runmode")
    return getattr(mode, "value", mode) in {"backtest", "hyperopt"}


class PredictionSnapshotStore:
    """Merge incoming predictions; never substitute a different candle's row."""

    REQUIRED_COLUMNS = {"date", "&-s_return", "do_predict"}

    def __init__(self, max_live_rows: int, keep_full_history: bool):
        self._max_live_rows = max_live_rows
        self._keep_full_history = keep_full_history
        self._snapshots: dict[str, pd.DataFrame] = {}

    def remember(self, pair: str | None, dataframe: pd.DataFrame) -> None:
        """Keep the latest received value per timestamp, preserving old rows."""
        if not pair or dataframe is None or not self.REQUIRED_COLUMNS.issubset(dataframe.columns):
            return
        current = dataframe[["date", "&-s_return", "do_predict"]].copy()
        current = current.dropna(subset=["date"]).sort_values("date")
        if not self._keep_full_history:
            current = current.tail(self._max_live_rows)
        previous = self._snapshots.get(pair)
        if previous is not None:
            current = pd.concat([previous, current], ignore_index=True)
        current = current.drop_duplicates(subset=["date"], keep="last").sort_values("date")
        if not self._keep_full_history:
            current = current.tail(self._max_live_rows)
        self._snapshots[pair] = current.reset_index(drop=True)

    def get_row(self, pair: str, candle_timestamp: pd.Timestamp) -> tuple[pd.Series, int] | None:
        """Return the exact row and historical row count, or None if absent."""
        snapshot = self._snapshots.get(pair)
        if snapshot is None or snapshot.empty:
            return None
        matched = snapshot.loc[snapshot["date"] == candle_timestamp]
        if matched.empty:
            return None
        return matched.iloc[-1], int((snapshot["date"] <= candle_timestamp).sum())
