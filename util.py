"""Strategy infrastructure for prediction snapshots, configuration, and probes."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from pandas import DataFrame, concat

# Cross-pair alignment audit log. Production keeps the probe disabled.
ALIGN_AUDIT_LOG = Path(__file__).resolve().parent / "logs" / "align_audit.jsonl"


def is_backtest_runmode(config) -> bool:
    """Return whether a run needs the complete historical prediction snapshot."""
    runmode = config.get("runmode")
    runmode_value = getattr(runmode, "value", runmode)
    return runmode_value in {"backtest", "hyperopt"}


class PredictionSnapshotStore:
    """Store dated model predictions and retrieve one exact candle per pair."""

    REQUIRED_COLUMNS = {"date", "&-s_return", "do_predict"}

    def __init__(self, max_live_rows: int, keep_full_history: bool):
        self._max_live_rows = max_live_rows
        self._keep_full_history = keep_full_history
        self._snapshots: dict[str, DataFrame] = {}

    def remember(self, pair: str | None, dataframe: DataFrame) -> None:
        """Merge one analyzed dataframe into a pair snapshot."""
        if not pair or dataframe is None:
            return
        if not self.REQUIRED_COLUMNS.issubset(dataframe.columns):
            return

        current = dataframe[["date", "&-s_return", "do_predict"]].copy()
        current = current.dropna(subset=["date"]).sort_values("date")
        if not self._keep_full_history:
            current = current.tail(self._max_live_rows)

        previous = self._snapshots.get(pair)
        if previous is not None:
            current = concat([previous, current], ignore_index=True)
        current = current.drop_duplicates(subset=["date"], keep="last").sort_values("date")
        if not self._keep_full_history:
            current = current.tail(self._max_live_rows)
        self._snapshots[pair] = current.reset_index(drop=True)

    def get_row(self, pair: str, candle_timestamp):
        """Return ``(row, row_count)`` for an exact candle, or ``None``."""
        snapshot = self._snapshots.get(pair)
        if snapshot is None or snapshot.empty:
            return None
        matched = snapshot.loc[snapshot["date"] == candle_timestamp]
        if matched.empty:
            return None
        row_count = int((snapshot["date"] <= candle_timestamp).sum())
        return matched.iloc[-1], row_count


@dataclass(frozen=True)
class ExperimentConfig:
    """Cached strategy experiment settings used by feature and label hooks."""

    label: str = "raw"
    features: tuple[str, ...] = ()
    probe: bool = False
    label_period_candles: int = 1

    @classmethod
    def from_strategy(cls, config, freqai_info) -> "ExperimentConfig":
        raw = config.get("my_experiment", {}) or {}
        feature_parameters = freqai_info["feature_parameters"]
        return cls(
            label=str(raw.get("label", "raw")),
            features=tuple(raw.get("features", []) or ()),
            probe=bool(raw.get("probe", False)),
            label_period_candles=int(feature_parameters.get("label_period_candles", 1)),
        )


class AlignmentProbe:
    """Write one alignment record per pair/candle state."""

    def __init__(self, enabled: bool, log_path=ALIGN_AUDIT_LOG):
        self._enabled = enabled
        self._log_path = Path(log_path)
        self._candle_timestamp = None
        self._states: dict[str, tuple] = {}

    def record(
        self,
        *,
        pair: str,
        candle_timestamp,
        last_candle_date,
        row_count: int,
        raw_prediction,
        complete: bool,
    ) -> None:
        """Record an alignment state unless the same state was already written."""
        if not self._enabled:
            return

        state = (
            complete,
            None if last_candle_date is None else str(last_candle_date),
        )
        if self._candle_timestamp != candle_timestamp:
            self._candle_timestamp = candle_timestamp
            self._states = {}
        if self._states.get(pair) == state:
            return
        self._states[pair] = state

        try:
            score = None if raw_prediction is None else float(raw_prediction)
        except (TypeError, ValueError):
            score = None
        if score is not None and not math.isfinite(score):
            score = None

        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "kind": "align",
            "candle_timestamp": str(candle_timestamp),
            "pair": pair,
            "last_date": None if last_candle_date is None else str(last_candle_date),
            "rows": row_count,
            "score": score,
            "complete": complete,
        }
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str, allow_nan=False) + "\n")
