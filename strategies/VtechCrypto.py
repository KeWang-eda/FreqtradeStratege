"""VtechCrypto: 动量轮动策略, Binance USDT 永续合约版.

源策略: /home/wangke/project/quant/strategy/Vtech.py
  聚宽「V科技队-7月量化策略竞技场」科技股池纯动量轮动(全实时分时触发版)

源逻辑(忠实转换):
  1. 动量打分 = 加权log线性回归斜率 x R2(拟合度)
  2. 近4根出现单根回撤 < -3% 则打分 x 0.5
  3. 打分 >= 阈值买入; 动量衰减(score_now < score_prev x 0.8)或止损卖出
  4. 最多5持仓, 等分资金

N 分钟映射(全部指标在主表 N 分钟 K 线上直算, 无跨周期数据):
  - 源"1根=1个交易日" -> 本策略"1根=N 分钟"; 年化K线数折算:
    BARS_PER_YEAR = 365 * 24 * 60 / N (5min -> 105120, 币市 7x24)
  - 分钟级扫描 -> 5m 主周期执行(T+0)
  - T+1 当根买入限制 -> 删除(加密 T+0)
  - 杠杆 -> LEVERAGE 超参数(2/5, 回测用2); 只做多(源策略无做空逻辑)

入场/出场信号由 freqtrade 统一 shift 1 根 K 线后执行.

实现参考:
  - https://www.freqtrade.io/en/stable/strategy-customization/
  - https://www.freqtrade.io/en/stable/backtesting/
"""
from typing import Any

import numpy as np

from pandas import DataFrame
from util import weighted_log_regression

from freqtrade.strategy import IStrategy


class VtechCrypto(IStrategy):
    """动量轮动: 加权log回归斜率xR2打分, 动量衰减+止损出场."""

    # ===== 调仓周期超参数 =====
    N_MINUTES = 60                  # 基线: 1 根 = 60 分钟
    timeframe = "1h"               # Binance/Freqtrade 的规范周期名

    # ===== 周期折算基准("1根=N 分钟") =====
    BARS_PER_DAY = 24 * 60 // N_MINUTES         # 288 @5min
    BARS_PER_YEAR = 365 * BARS_PER_DAY          # 105120 @5min(币市 7x24)

    # ===== 超参数(用户可调) =====
    LEVERAGE = 2                    # 杠杆: 2 或 5, 回测用 2
    LOOKBACK_BARS = 20              # 动量打分窗口: 20 根 N 分钟 K 线
    LOOKBACK_BARS_PREV = 22         # 衰减对比窗口: 22 根(源 20:22 原比例)
    MOMENTUM_MIN_SCORE = 0.003      # 买入最低打分(默认 exp 分数口径)
    MOMENTUM_SCORE_MODE = "exp"     # 基线; 实验类可切换为 signed_log
    MOMENTUM_DECAY_RATE = 0.60      # 动量衰减卖出阈值(四段验证后固化)
    STOP_LOSS_RATIO = -0.15         # 止损线(-15%)
    RECENT_DROP_RETURN = -0.02      # 近4根单根大回撤判定(回撤2%即惩罚, 过滤弱入场)
    RECENT_DROP_PENALTY = 0.5       # 大回撤打分折扣

    # ===== freqtrade 组合层(对应源策略"最多5持仓") =====
    max_open_trades = 5

    # ===== 出场/风控 =====
    # 源策略无固定止盈: 只有动量衰减和止损. 加密映射加 ROI 止盈
    # (纯参数: 盈利>=6% 即锁定, 缓解无止盈导致的利润回吐)
    minimal_roi = {"0": 0.06}
    stoploss = STOP_LOSS_RATIO
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    process_only_new_candles = True
    startup_candle_count = 30

    def leverage(self, pair: str, current_time, current_rate,
                 proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        """返回超参数杠杆值(2或5). freqtrade futures 专用回调."""
        return self.LEVERAGE

    def populate_indicators(self, dataframe: DataFrame,
                            metadata: dict[str, Any]) -> DataFrame:
        """全部指标基于主表(N 分钟 K 线)直算, 每根新 bar 更新.

        无跨周期数据源/shift/merge/ffill; 入场/出场信号由 freqtrade
        统一 shift 1 根执行, 指标本身即当前已收盘 bar 的值.
        """
        closes = dataframe['close']
        if len(dataframe) < self.LOOKBACK_BARS_PREV + 5:
            dataframe['raw_mom_score'] = 0.0
            dataframe['raw_mom_score_prev'] = 0.0
            dataframe['mom_score'] = 0.0
            dataframe['mom_score_prev'] = 0.0
            dataframe['ma20'] = 0.0
            return dataframe

        # ---- 1. 动量打分: 引擎加权log回归(FFT卷积), 年化按币市7x24折算 ----
        # 默认 score = (exp(年化log收益)-1) x R2; 实验模式可改为对称log分数
        score, _, _ = weighted_log_regression(
            closes, self.LOOKBACK_BARS, weight_power=1.0,
            annualize_bars=self.BARS_PER_YEAR,
            score_mode=self.MOMENTUM_SCORE_MODE)
        dataframe['raw_mom_score'] = score
        mom_score = np.where(score < 0, 0.0, score)

        # 衰减对比: 同日 22 根窗口打分(20 vs 22 同终点, 源策略口径)
        score_prev, _, _ = weighted_log_regression(
            closes, self.LOOKBACK_BARS_PREV, weight_power=1.0,
            annualize_bars=self.BARS_PER_YEAR,
            score_mode=self.MOMENTUM_SCORE_MODE)
        dataframe['raw_mom_score_prev'] = score_prev
        mom_score_prev = np.where(score_prev < 0, 0.0, score_prev)

        # ---- 2. 近4根回撤惩罚(源策略: 出现单根回撤<-阈值 则打分x0.5) ----
        recent_returns = closes / closes.shift(1) - 1
        drop_flag = recent_returns.rolling(4, min_periods=1).min()
        penalty = np.where(drop_flag < self.RECENT_DROP_RETURN,
                           self.RECENT_DROP_PENALTY, 1.0)
        dataframe['mom_score'] = mom_score * penalty
        dataframe['mom_score_prev'] = mom_score_prev * penalty

        # ---- 3. MA20 趋势过滤(20 根 N 分钟 K 线) ----
        dataframe['ma20'] = closes.rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame,
                             metadata: dict[str, Any]) -> DataFrame:
        """入场: 动量打分达阈值 + 价格在 MA20 上方(趋势过滤)."""
        dataframe.loc[
            (dataframe['mom_score'] >= self.MOMENTUM_MIN_SCORE)
            & (dataframe['close'] > dataframe['ma20'])
            & (dataframe['ma20'] > 0)
            & (dataframe['volume'] > 0),
            'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame,
                            metadata: dict[str, Any]) -> DataFrame:
        """出场: 动量衰减(score_now < score_prev x 0.8)."""
        dataframe.loc[
            (dataframe['mom_score_prev'] > 0)
            & (dataframe['mom_score']
               < dataframe['mom_score_prev'] * self.MOMENTUM_DECAY_RATE),
            'exit_long'] = 1
        return dataframe
