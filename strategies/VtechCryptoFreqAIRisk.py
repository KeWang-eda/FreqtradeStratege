"""Vtech FreqAI v2：预测最大不利波动并动态缩放仓位.

v1 的样本外诊断显示 XGBoost 对未来方向收益没有排序能力，但对未来最大
不利波动有一定预测力。因此 v2 不删除方向信号，只降低高预测风险候选的
资金暴露，直接服务于回撤控制。

实现参考:
  - docs/strategy-callbacks.md: custom_stake_amount
  - docs/freqai-configuration.md: 回归目标均值与标准差返回列
  - VtechCryptoFreqAI.py: 已验证的特征、候选方向和 FreqAI 数据流
"""
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import DecimalParameter

from VtechCryptoFreqAI import VtechCryptoFreqAI


class VtechCryptoFreqAIRisk(VtechCryptoFreqAI):
    """按预测最大不利波动分配仓位，保留 Vtech 原始多空和退出规则."""

    # z-score 映射的总宽度；2.0 保持历史公式的行为。
    RISK_Z_SPAN = 2.0

    # v1 的效用门槛在本策略中不参与信号，也不进入 Hyperopt 空间。
    long_min_utility = DecimalParameter(
        -0.060,
        0.005,
        default=-0.060,
        decimals=3,
        space="buy",
        optimize=False,
        load=False,
    )
    short_min_utility = DecimalParameter(
        -0.060,
        0.005,
        default=-0.060,
        decimals=3,
        space="buy",
        optimize=False,
        load=False,
    )
    di_max = DecimalParameter(0.30, 2.00, default=1.50, decimals=2, space="buy")
    min_stake_fraction = DecimalParameter(
        0.20, 1.00, default=0.50, decimals=2, space="buy"
    )
    risk_z_center = DecimalParameter(
        -1.00, 1.00, default=0.00, decimals=2, space="buy"
    )

    plot_config = {
        "main_plot": {},
        "subplots": {
            "predicted_adverse": {"&-vtech_adverse": {"color": "red"}},
            "prediction": {"do_predict": {"color": "brown"}},
        },
    }

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """训练目标为候选方向未来 8 根 K 线内的最大不利波动."""
        dataframe = self._ensure_vtech_indicators(dataframe, metadata)
        period = self.freqai_info["feature_parameters"]["label_period_candles"]
        direction = self._candidate_direction(dataframe)

        future_low = dataframe["low"].shift(-period).rolling(period).min()
        future_high = dataframe["high"].shift(-period).rolling(period).max()
        long_adverse = (1.0 - future_low / dataframe["close"]).clip(lower=0.0)
        short_adverse = (future_high / dataframe["close"] - 1.0).clip(lower=0.0)
        adverse_move = pd.Series(
            np.where(direction > 0, long_adverse, short_adverse),
            index=dataframe.index,
        )
        fee = float(self.config.get("fee", self.DEFAULT_FEE))
        predicted_risk = self.LEVERAGE * (adverse_move + 2.0 * fee)
        dataframe["&-vtech_adverse"] = predicted_risk.where(direction != 0.0, np.nan)
        return dataframe

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """保留所有分布内 Vtech 候选，ML 不再判断交易方向或收益."""
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        direction = self._candidate_direction(dataframe)
        accepted = (
            (dataframe["do_predict"] == 1)
            & (dataframe["DI_values"] <= self.di_max.value)
        )
        dataframe.loc[
            accepted & (direction == 1.0), ["enter_long", "enter_tag"]
        ] = (1, "vtech_risk_long")
        dataframe.loc[
            accepted & (direction == -1.0), ["enter_short", "enter_tag"]
        ] = (1, "vtech_risk_short")
        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """把预测风险 z-score 线性映射为最小比例至满仓之间的 stake."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return proposed_stake
        latest = dataframe.iloc[-1]
        prediction = float(latest.get("&-vtech_adverse", np.nan))
        target_mean = float(latest.get("&-vtech_adverse_mean", np.nan))
        target_std = float(latest.get("&-vtech_adverse_std", np.nan))
        if not np.isfinite(prediction + target_mean + target_std) or target_std <= 0.0:
            return proposed_stake

        risk_z = (prediction - target_mean) / target_std
        center = self.risk_z_center.value
        span = max(float(self.RISK_Z_SPAN), 1e-9)
        high_risk_weight = float(
            np.clip((risk_z - center + span / 2.0) / span, 0.0, 1.0)
        )
        stake_fraction = 1.0 - high_risk_weight * (1.0 - self.min_stake_fraction.value)
        return proposed_stake * stake_fraction
