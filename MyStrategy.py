"""4h 回归策略：预测未来 3 根 4h 收益率，5 pair 跨币择优，只开 abs(分数) 最大的 1 仓。

实验通过 config["my_experiment"] 切换标签与特征。

my_experiment:
  label: "raw" | "volnorm"
  features: ["laguerre", "vwmacd", "tke", "vfi", "rmi"]
  entry_threshold: float（与标签同尺度）
  probe: bool（记录跨 pair 时间对齐）
"""

import json
from pathlib import Path

import numpy as np
from pandas import DataFrame

from feature_engineering import (
    add_basic_features,
    add_expanded_all_features,
    add_standard_features,
)
from model_io import (
    exit_long_signal,
    exit_short_signal,
    long_signal,
    read_prediction_return,
    set_return_target,
    short_signal,
)
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

# 跨 pair 时间对齐审计日志（JSONL，追加写入）。
# 仅在 config.json 的 my_experiment.probe = true 时写入，生产保持 false。
ALIGN_AUDIT_LOG = Path(__file__).resolve().parent / "logs" / "align_audit.jsonl"


class MyStrategy(IStrategy):
    """Predict the 3-candle forward return and trade the non-flat predictions."""

    timeframe = "4h"
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True

    def leverage(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """返回当前交易使用的杠杆；策略上限固定为 2 倍。"""
        return min(2.0, float(max_leverage))

    minimal_roi = {"0": 999.0}
    stoploss = -1.0
    use_exit_signal = True
    trailing_stop = False

    # ---------------- 实验配置 ----------------
    @property
    def _exp(self) -> dict:
        """返回实验开关；来源是 config.json 的 my_experiment。"""
        return self.config.get("my_experiment", {}) or {}

    @property
    def _entry_threshold(self) -> float:
        """返回回归预测入场阈值；volnorm 标签时与归一化分数同尺度。"""
        return float(self._exp.get("entry_threshold", 0.005))

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """为每个配置周期添加 RSI、均线乖离、ATR 比率和相对成交量。"""
        return add_expanded_all_features(dataframe, period)

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """添加收益率、振幅、实体和成交量变化等基础价量特征。"""
        return add_basic_features(dataframe)

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """添加标准波动/时间特征，并按配置启用 technical 候选指标。"""
        return add_standard_features(dataframe, self._exp.get("features", []))

    # ---------------- 回归标签 ----------------
    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """写入回归标签；训练由 config 的原生 XGBoostRegressor 负责。"""
        horizon = int(self.freqai_info["feature_parameters"].get("label_period_candles", 1))
        return set_return_target(dataframe, horizon, self._exp.get("label", "raw"))

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """交给 FreqAI 训练/加载模型，并返回带预测列的分析数据。"""
        return self.freqai.start(dataframe, metadata, self)

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """预测收益超过阈值才入场。"""
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        ready = dataframe["do_predict"] == 1
        prediction_return = read_prediction_return(dataframe)
        threshold = self._entry_threshold

        long_mask = long_signal(prediction_return, ready, threshold)
        short_mask = short_signal(prediction_return, ready, threshold)
        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = "reg_up"
        dataframe.loc[short_mask, "enter_short"] = 1
        dataframe.loc[short_mask, "enter_tag"] = "reg_down"
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """预测收益反向即离场。"""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        ready = dataframe["do_predict"] == 1
        prediction_return = read_prediction_return(dataframe)

        dataframe.loc[exit_long_signal(prediction_return, ready), "exit_long"] = 1
        dataframe.loc[exit_short_signal(prediction_return, ready), "exit_short"] = 1
        return dataframe

    # ---------------- 跨 pair 择优（波动率归一化） ----------------
    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        """下单前比较所有 pair 的绝对归一化分数，只允许最强候选成交。"""
        # 以当前 K 线为锚点：切片由回测引擎按时刻限长，不会读到未来 K 线。
        mine = self._rank_info(pair, current_time)
        if mine is None:
            return True
        my_date, my_score, _ = mine
        return self._find_stronger_pair(pair, my_date, my_score, current_time) is None

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        """持仓不再是最强候选、或自身预测跌破阈值时退出；不使用止盈止损退出。"""
        mine = self._rank_info(pair, current_time)
        if mine is None:
            return "prediction_below_entry_threshold"

        my_date, my_score, _ = mine
        if self._find_stronger_pair(pair, my_date, my_score, current_time) is not None:
            return "weaker_pair_rotation"
        return None

    def _find_stronger_pair(self, pair: str, my_date, my_score: float, cutoff):
        """在共同锚点上寻找绝对分数更高的 pair；没有更强的返回 None。"""
        for other in self.dp.current_whitelist():
            if other == pair:
                continue
            info = self._rank_info(other, cutoff)
            if info is None:
                continue
            other_date, other_score, _ = info
            if abs(other_score) > abs(my_score):
                if self._exp.get("probe"):
                    self._probe(
                        cutoff, pair, my_score, my_date,
                        other, other_score, other_date,
                    )
                return other, other_score, other_date
        return None

    def _rank_info(self, pair: str, cutoff=None) -> tuple | None:
        """返回 (date, 波动率归一化分数, 方向)；不可比较时返回 None。"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty:
            return None
        needed = {"date", "close", "&-s_return", "do_predict"}
        if not needed.issubset(dataframe.columns):
            return None
        if cutoff is not None:
            dataframe = dataframe[dataframe["date"] <= cutoff]
            if dataframe.empty:
                return None

        row = dataframe.iloc[-1]
        if row["do_predict"] != 1:
            return None
        prediction_return = float(row["&-s_return"])
        if not np.isfinite(prediction_return):
            return None
        # 自己都不会入场的候选不参与比较
        if abs(prediction_return) <= self._entry_threshold:
            return None

        recent_vol = float(dataframe["close"].pct_change().rolling(30).std().iloc[-1])
        if np.isfinite(recent_vol) and recent_vol > 0:
            score = prediction_return / recent_vol
        else:
            score = prediction_return

        direction = "long" if prediction_return > 0 else "short"
        if self._exp.get("probe"):
            self._probe_alignment(pair, row["date"], len(dataframe), score)
        return row["date"], score, direction

    @staticmethod
    def _probe(current_time, pair, my_score, my_date, other, other_score, other_date) -> None:
        """写入被更强 pair 拒绝的审计记录，不参与交易决策。"""
        with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "reject", "time": str(current_time), "pair": pair,
                "my_score": my_score, "my_date": str(my_date),
                "other": other, "other_score": other_score,
                "other_date": str(other_date),
                "same_candle": str(my_date) == str(other_date),
            }) + "\n")

    @staticmethod
    def _probe_alignment(pair, last_date, rows, score) -> None:
        """写入 pair 预测时间对齐审计记录。"""
        with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "align", "pair": pair, "last_date": str(last_date),
                "rows": rows, "score": score,
            }) + "\n")

