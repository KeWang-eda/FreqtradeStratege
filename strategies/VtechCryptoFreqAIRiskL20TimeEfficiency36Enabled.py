"""Experiment 184: 36-hour stale-trade exit."""
from VtechCryptoFreqAIRiskL20TimeEfficiency48Enabled import VtechCryptoFreqAIRiskL20TimeEfficiency48Enabled


class VtechCryptoFreqAIRiskL20TimeEfficiency36Enabled(VtechCryptoFreqAIRiskL20TimeEfficiency48Enabled):
    STALE_HOURS = 36

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if age_hours >= self.STALE_HOURS and current_profit <= self.STALE_PROFIT:
            return "stale_36h"
        return None
