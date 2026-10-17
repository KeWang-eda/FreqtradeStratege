"""Optional JSONL alignment audit; disabled in normal trading runs."""

import json
import math
from pathlib import Path
from typing import Any

ALIGN_AUDIT_LOG = Path(__file__).resolve().parents[3] / "logs" / "align_audit.jsonl"


class AlignmentProbe:
    """Deduplicate pair/candle completeness states before writing to disk."""

    def __init__(self, enabled: bool, log_path: str | Path = ALIGN_AUDIT_LOG):
        self._enabled = enabled
        self._log_path = Path(log_path)
        self._candle_timestamp = None
        self._states: dict[str, tuple] = {}

    def record(
        self,
        *,
        pair: str,
        candle_timestamp: Any,
        last_candle_date: Any,
        row_count: int,
        raw_prediction: Any,
        complete: bool,
    ) -> None:
        """Write a finite prediction or null, preserving legacy audit keys."""
        if not self._enabled:
            return
        state = (complete, None if last_candle_date is None else str(last_candle_date))
        if self._candle_timestamp != candle_timestamp:
            self._candle_timestamp, self._states = candle_timestamp, {}
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
            handle.write(json.dumps(record, allow_nan=False) + "\n")
