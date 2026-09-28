"""Experiment 180: single-variable low-efficiency holding exit at 48 hours."""
from datetime import datetime

from VtechCryptoFreqAIRiskL20DynamicROI100 import VtechCryptoFreqAIRiskL20DynamicROI100


class VtechCryptoFreqAIRiskL20TimeEfficiency48(VtechCryptoFreqAIRiskL20DynamicROI100):
    """Exit only stale trades whose leveraged profit remains near flat."""

    STALE_HOURS = 48
    STALE_PROFIT = 0.002

    def custom_exit(self, pair: str, trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if age_hours >= self.STALE_HOURS and current_profit <= self.STALE_PROFIT:
            return "stale_48h"
        return None
