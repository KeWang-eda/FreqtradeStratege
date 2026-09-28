"""Experiment 184: 36-hour stale-trade exit."""

from datetime import datetime
from typing import Any

from VtechCryptoFreqAIRiskL20TimeEfficiency48Enabled import (
    VtechCryptoFreqAIRiskL20TimeEfficiency48Enabled,
)


class VtechCryptoFreqAIRiskL20TimeEfficiency36Enabled(
    VtechCryptoFreqAIRiskL20TimeEfficiency48Enabled
):
    """Close a low-profit trade after the 36-hour efficiency window."""

    STALE_HOURS = 36

    def custom_exit(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs: Any,
    ) -> str | None:
        """Return the stale-exit tag when the age and profit gates are met."""
        age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if age_hours >= self.STALE_HOURS and current_profit <= self.STALE_PROFIT:
            return "stale_36h"
        return None
