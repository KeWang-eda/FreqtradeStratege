"""VtechCrypto 的严格镜像仅空头版本.

多头与空头对称关系:
  - 正动量 -> 负动量绝对值
  - close > MA20 -> close < MA20
  - 单根下跌惩罚 -> 单根上涨惩罚
  - 多头动量衰减退出 -> 空头动量衰减退出

实现参考:
  - https://www.freqtrade.io/en/stable/strategy-customization/#enter-tag
  - https://www.freqtrade.io/en/stable/strategy-customization/#can-short
"""
import numpy as np
from pandas import DataFrame

from VtechCrypto import VtechCrypto


class VtechCryptoShort(VtechCrypto):
    """负动量轮动策略，只建立空头仓位."""

    can_short = True

    def populate_indicators(self, dataframe: DataFrame,
                            metadata: dict) -> DataFrame:
        """复用多头原始指标，并构造完全镜像的空头强度."""
        dataframe = super().populate_indicators(dataframe, metadata)
        recent_returns = dataframe['close'].pct_change()
        rise_flag = recent_returns.rolling(4, min_periods=1).max()
        rise_penalty = np.where(
            rise_flag > -self.RECENT_DROP_RETURN,
            self.RECENT_DROP_PENALTY,
            1.0,
        )
        dataframe['short_mom_score'] = (
            np.maximum(-dataframe['raw_mom_score'], 0.0) * rise_penalty
        )
        dataframe['short_mom_score_prev'] = (
            np.maximum(-dataframe['raw_mom_score_prev'], 0.0) * rise_penalty
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame,
                             metadata: dict) -> DataFrame:
        """入场：负动量达到门槛，且价格位于 MA20 下方."""
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        dataframe.loc[
            (dataframe['short_mom_score'] >= self.MOMENTUM_MIN_SCORE)
            & (dataframe['close'] < dataframe['ma20'])
            & (dataframe['ma20'] > 0)
            & (dataframe['volume'] > 0),
            'enter_short'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame,
                            metadata: dict) -> DataFrame:
        """出场：空头负动量强度相对长窗口发生衰减."""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        dataframe.loc[
            (dataframe['short_mom_score_prev'] > 0)
            & (dataframe['short_mom_score']
               < dataframe['short_mom_score_prev']
               * self.MOMENTUM_DECAY_RATE),
            'exit_short'] = 1
        return dataframe
