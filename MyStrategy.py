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
    make_next_direction_labels,
    read_prediction_return,
    set_return_target,
    short_signal,
)
from freqtrade.strategy import IStrategy

PROBE_OUT = Path("/tmp/reg_rank_probe.jsonl")


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
        return min(2.0, float(max_leverage))

    minimal_roi = {"0": 999.0}
    stoploss = -0.08
    use_exit_signal = True
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True

    # ---------------- 实验配置 ----------------
    @property
    def _exp(self) -> dict:
        return self.config.get("my_experiment", {}) or {}

    @property
    def _entry_threshold(self) -> float:
        return float(self._exp.get("entry_threshold", 0.005))

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        return add_expanded_all_features(dataframe, period)

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        return add_basic_features(dataframe)

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
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
        # ponytail: 白名单靠后的 pair 索引尚未推进，取双方最小日期做共同锚点，
        # 否则会拿当前 pair 的新 K 线去比对方的旧 K 线（非未来函数，但不公平）。
        my_last = self._last_available_date(pair)
        if my_last is None:
            return True
        others = [p for p in self.dp.current_whitelist() if p != pair]
        other_lasts = {p: self._last_available_date(p) for p in others}
        available = [d for d in other_lasts.values() if d is not None]
        anchor_date = min([my_last] + available) if available else my_last

        mine = self._rank_info(pair, anchor_date)
        if mine is None:
            return True
        my_date, my_score, my_dir = mine

        for other in others:
            info = self._rank_info(other, anchor_date)
            if info is None:
                continue
            other_date, other_score, other_dir = info
            # 全局比较：做多/做空一起按 abs(score) 排序，只留最大的那个。
            if abs(other_score) > abs(my_score):
                if self._exp.get("probe"):
                    self._probe(
                        current_time, pair, my_score, my_date,
                        other, other_score, other_date,
                    )
                return False
        return True

    def _last_available_date(self, pair: str):
        """该 pair 当前可读到的最后一根 K 线时间；不可用返回 None。"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty or "date" not in dataframe.columns:
            return None
        return dataframe["date"].iloc[-1]

    def _rank_info(self, pair: str, anchor_date=None):
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
        if anchor_date is not None:
            dataframe = dataframe[dataframe["date"] <= anchor_date]
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

        recent_vol = dataframe["close"].pct_change().rolling(30).std().iloc[-1]
        if pd_notna(recent_vol) and float(recent_vol) > 0:
            score = prediction_return / float(recent_vol)
        else:
            score = prediction_return

        direction = "long" if prediction_return > 0 else "short"
        if self._exp.get("probe"):
            self._probe_alignment(pair, row["date"], len(dataframe), score)
        return row["date"], score, direction

    @staticmethod
    def _probe(current_time, pair, my_score, my_date, other, other_score, other_date) -> None:
        with PROBE_OUT.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "reject", "time": str(current_time), "pair": pair,
                "my_score": my_score, "my_date": str(my_date),
                "other": other, "other_score": other_score,
                "other_date": str(other_date),
                "same_candle": str(my_date) == str(other_date),
            }) + "\n")

    @staticmethod
    def _probe_alignment(pair, last_date, rows, score) -> None:
        with PROBE_OUT.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "align", "pair": pair, "last_date": str(last_date),
                "rows": rows, "score": score,
            }) + "\n")


def pd_notna(value) -> bool:
    """pandas 无关的 NaN 检查，避免引入额外 import。"""
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False
