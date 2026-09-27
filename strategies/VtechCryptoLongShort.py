"""VtechCrypto 多头与镜像空头的合并策略.

多空共享资金和 max_open_trades，不为任一方向额外放大风险预算。

实现参考:
  - https://www.freqtrade.io/en/stable/strategy-customization/#entry-signal-rules
  - https://www.freqtrade.io/en/stable/strategy-customization/#exit-signal-rules
"""
from pandas import DataFrame

from VtechCryptoShort import VtechCryptoShort


class VtechCryptoLongShort(VtechCryptoShort):
    """同时执行 Vtech 正动量多头和对称负动量空头信号."""

    can_short = True

    def populate_entry_trend(self, dataframe: DataFrame,
                             metadata: dict) -> DataFrame:
        """分别按趋势方向生成多头和空头入场信号."""
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        dataframe.loc[
            (dataframe['mom_score'] >= self.MOMENTUM_MIN_SCORE)
            & (dataframe['close'] > dataframe['ma20'])
            & (dataframe['ma20'] > 0)
            & (dataframe['volume'] > 0),
            'enter_long'] = 1
        dataframe.loc[
            (dataframe['short_mom_score'] >= self.MOMENTUM_MIN_SCORE)
            & (dataframe['close'] < dataframe['ma20'])
            & (dataframe['ma20'] > 0)
            & (dataframe['volume'] > 0),
            'enter_short'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame,
                            metadata: dict) -> DataFrame:
        """分别按各自方向的动量衰减信号退出."""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        dataframe.loc[
            (dataframe['mom_score_prev'] > 0)
            & (dataframe['mom_score']
               < dataframe['mom_score_prev'] * self.MOMENTUM_DECAY_RATE),
            'exit_long'] = 1
        dataframe.loc[
            (dataframe['short_mom_score_prev'] > 0)
            & (dataframe['short_mom_score']
               < dataframe['short_mom_score_prev']
               * self.MOMENTUM_DECAY_RATE),
            'exit_short'] = 1
        return dataframe


class VtechCryptoLongShort30m(VtechCryptoLongShort):
    """30 分钟周期实验版，其他逻辑与 1h 基线完全一致."""

    N_MINUTES = 30
    timeframe = "30m"
    BARS_PER_DAY = 48
    BARS_PER_YEAR = 365 * BARS_PER_DAY


class VtechCryptoLongShort15m(VtechCryptoLongShort):
    """15 分钟周期实验版，其他逻辑与 1h 基线完全一致."""

    N_MINUTES = 15
    timeframe = "15m"
    BARS_PER_DAY = 96
    BARS_PER_YEAR = 365 * BARS_PER_DAY


class VtechCryptoLongShort5m(VtechCryptoLongShort):
    """5 分钟周期实验版，其他逻辑与 1h 基线完全一致."""

    N_MINUTES = 5
    timeframe = "5m"
    BARS_PER_DAY = 288
    BARS_PER_YEAR = 365 * BARS_PER_DAY


class VtechCryptoLongShort4h(VtechCryptoLongShort):
    """4 小时 bar 实验版，其他逻辑与 1h 基线完全一致."""

    N_MINUTES = 240
    timeframe = "4h"
    BARS_PER_DAY = 6
    BARS_PER_YEAR = 365 * BARS_PER_DAY


class VtechCryptoLongShort6h(VtechCryptoLongShort):
    """6 小时 bar 实验版，其他逻辑与 1h 基线完全一致."""

    N_MINUTES = 360
    timeframe = "6h"
    BARS_PER_DAY = 4
    BARS_PER_YEAR = 365 * BARS_PER_DAY


class VtechCryptoLongShort12h(VtechCryptoLongShort):
    """12 小时 bar 实验版，其他逻辑与 1h 基线完全一致."""

    N_MINUTES = 720
    timeframe = "12h"
    BARS_PER_DAY = 2
    BARS_PER_YEAR = 365 * BARS_PER_DAY


class VtechCryptoLongShort24h(VtechCryptoLongShort):
    """24 小时 bar 实验版；Freqtrade 用 1d 表示 24 小时周期."""

    N_MINUTES = 1440
    timeframe = "1d"
    BARS_PER_DAY = 1
    BARS_PER_YEAR = 365


class VtechCryptoLongShortSymmetric(VtechCryptoLongShort):
    """仅替换动量分数变换的 1h 对照实验版.

    其他策略规则、阈值、周期、费用和资金限制均继承 1h 多空基线。
    """

    MOMENTUM_SCORE_MODE = "signed_log"


class VtechCryptoLongShortStop10(VtechCryptoLongShort):
    """仅将固定止损收紧到 -10% 的 1h 单变量实验版."""

    stoploss = -0.10


class VtechCryptoLongShortDecay60(VtechCryptoLongShort):
    """仅将动量衰减退出阈值放宽到 0.60 的 1h 单变量实验版."""

    MOMENTUM_DECAY_RATE = 0.60
