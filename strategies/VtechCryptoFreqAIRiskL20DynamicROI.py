"""Experiment 156: volatility-scaled custom ROI on the Experiment 136 parent.

Only the exit callback is changed.  ATR is computed from completed candles at
callback time and is not added to the FreqAI feature/target set.
"""

from datetime import datetime

from VtechCryptoFreqAIRiskL20RecentDropPenaltyActivated import (
    VtechCryptoFreqAIRiskL20RecentDropPenaltyP050,
)


class _DynamicROIBase(VtechCryptoFreqAIRiskL20RecentDropPenaltyP050):
    use_custom_roi = True
    minimal_roi = {"0": 0.20}
    ATR_PERIOD = 14
    ROI_ATR_MULTIPLIER = 1.0

    def custom_roi(
        self,
        pair: str,
        trade,
        current_time: datetime,
        trade_duration: int,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float | None:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < self.ATR_PERIOD + 2:
            return None
        # Keep one extra completed candle so the first TR includes its
        # previous close. The last row is the still-forming candle.
        candle = dataframe.iloc[:-1].tail(self.ATR_PERIOD + 1)
        if not __import__("numpy").isfinite(candle[["high", "low", "close"]].to_numpy()).all():
            return None
        previous_close = candle["close"].shift(1)
        true_range = __import__("pandas").concat(
            [
                candle["high"] - candle["low"],
                (candle["high"] - previous_close).abs(),
                (candle["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        true_range = true_range.iloc[1:]
        last_close = float(candle["close"].iloc[-1])
        if last_close <= 0.0 or not __import__("numpy").isfinite(last_close):
            return None
        if true_range.isna().any() or not __import__("numpy").isfinite(true_range).all():
            return None
        atr_ratio = float(true_range.mean() / last_close)
        # custom_roi is evaluated in leveraged profit space; convert the
        # price-volatility target using the trade's actual leverage.
        leverage = float(getattr(trade, "leverage", 1.0) or 1.0)
        threshold = atr_ratio * leverage * float(self.ROI_ATR_MULTIPLIER)
        return max(0.05, min(0.20, threshold))


class VtechCryptoFreqAIRiskL20DynamicROIControl(_DynamicROIBase):
    """Control: defer to the parent's fixed minimal ROI."""

    use_custom_roi = False


class VtechCryptoFreqAIRiskL20DynamicROI05(_DynamicROIBase):
    ROI_ATR_MULTIPLIER = 0.5


class VtechCryptoFreqAIRiskL20DynamicROI10(_DynamicROIBase):
    ROI_ATR_MULTIPLIER = 1.0


class VtechCryptoFreqAIRiskL20DynamicROI15(_DynamicROIBase):
    ROI_ATR_MULTIPLIER = 1.5
