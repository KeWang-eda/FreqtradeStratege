"""4h 回归策略：预测未来 3 根 4h 收益率，在全池中择优，只开 abs(分数) 最大的 1 仓。

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
    add_baseline_features,
    add_basic_price_features,
    add_period_expanded_features,
)
# 【评论 1】原问：exit_long* 和 long* 有什么区别？read_prediction_return、set_return_target 命名奇怪。
# 已处理：全部改名。区别在于阈值不同——入场要求 |预测| > entry_threshold，
# 退出只要求预测反向（阈值 0），所以两者不对称、不能合并。
#   set_return_target      → set_regression_target
#   read_prediction_return → read_model_prediction
#   long_signal            → should_enter_long
#   short_signal           → should_enter_short
#   exit_long_signal       → should_exit_long
#   exit_short_signal      → should_exit_short
from model_io import (
    read_model_prediction,
    set_regression_target,
    should_enter_long,
    should_enter_short,
    should_exit_long,
    should_exit_short,
)
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

# 跨 pair 时间对齐审计日志（JSONL，追加写入）。
# 仅在 config.json 的 my_experiment.probe = true 时写入，生产保持 false。
ALIGN_AUDIT_LOG = Path(__file__).resolve().parent / "logs" / "align_audit.jsonl"


class MyStrategy(IStrategy):
    """预测未来 3 根 4h K 线收益率，并在全池中只持有一个最强的仓位。"""

    timeframe = "4h"
    startup_candle_count = 100
        # 【评论 2】原问：这个参数干什么的？
        # 已答：同一根 K 线不重复计算指标，只有出现新 K 线才跑 populate_*。
        # 对 FreqAI 是硬性要求，改成 False 会被 freqai_interface.py:447 直接拒绝启动。
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
    def _experiment_config(self) -> dict:
        """返回实验开关；来源是 config.json 的 my_experiment。"""
        return self.config.get("my_experiment", {}) or {}

    @property
    def _min_prediction_to_enter(self) -> float:
        """返回入场所需的最小预测幅度；volnorm 标签时与归一化分数同尺度。"""
        return float(self._experiment_config.get("entry_threshold", 0.005))

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """为每个配置周期添加 RSI、均线乖离、ATR 比率和相对成交量。"""
        return add_period_expanded_features(dataframe, period)

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """添加收益率、振幅、实体和成交量变化等基础价量特征。"""
        return add_basic_price_features(dataframe)

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """添加标准波动/时间特征，并按配置追加 technical 候选指标。"""
        return add_baseline_features(
            dataframe, self._experiment_config.get("features", [])
        )

    # ---------------- 回归标签 ----------------
    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """写入回归标签；训练由 config 的原生 XGBoostRegressor 负责。"""
        prediction_horizon = int(
            self.freqai_info["feature_parameters"].get("label_period_candles", 1)
        )
        return set_regression_target(
            dataframe,
            prediction_horizon,
            self._experiment_config.get("label", "raw"),
        )

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """交给 FreqAI 训练/加载模型，并返回带预测列的分析数据。"""
        return self.freqai.start(dataframe, metadata, self)

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """预测幅度超过入场阈值才产生入场信号。"""
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        prediction_ready = dataframe["do_predict"] == 1
        model_prediction = read_model_prediction(dataframe)
        entry_threshold = self._min_prediction_to_enter

        long_mask = should_enter_long(model_prediction, prediction_ready, entry_threshold)
        short_mask = should_enter_short(model_prediction, prediction_ready, entry_threshold)
        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = "reg_up"
        dataframe.loc[short_mask, "enter_short"] = 1
        dataframe.loc[short_mask, "enter_tag"] = "reg_down"
        return dataframe

        # 【评论 3】原问：怎么还有反向离场，是否冗余。
        # 已答：不冗余，且是唯一生效的反向离场。custom_exit 里那份重复判断才是死代码，已删。
        # 依据 interface.py:1462-1473：exit_ and not enter 时 custom_exit 不被调用，
        # 走 EXIT_SIGNAL。实测 prediction_reversal 命中 0 次。
        # 见 test_exit_trend_is_the_only_reversal_exit。
    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """预测反向即离场（阈值 0，不要求超过入场阈值）。"""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        prediction_ready = dataframe["do_predict"] == 1
        model_prediction = read_model_prediction(dataframe)

        dataframe.loc[should_exit_long(model_prediction, prediction_ready), "exit_long"] = 1
        dataframe.loc[should_exit_short(model_prediction, prediction_ready), "exit_short"] = 1
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
        current_pair_rank = self._pair_score_and_direction(pair, current_time)
        if current_pair_rank is None:
            return True
        current_pair_date, current_pair_score, _ = current_pair_rank
        return (
            self._find_stronger_pair(
                pair, current_pair_date, current_pair_score, current_time
            )
            is None
        )

        # 【评论 4】原问：_find_stronger_pair 命名不规范，给候选。
        # 已给候选（试卷第 5 题）并采用 B：_find_stronger_pair。
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
        current_pair_rank = self._pair_score_and_direction(pair, current_time)
        if current_pair_rank is None:
                    # 【评论 5】原问：return 后面的命名不规范。
                    # 已改：prediction_below_entry_threshold → prediction_weakened
                    #       weaker_pair_rotation            → rotated_to_stronger_pair
            return "prediction_weakened"

        current_pair_date, current_pair_score, _ = current_pair_rank
        if (
            self._find_stronger_pair(
                pair, current_pair_date, current_pair_score, current_time
            )
            is not None
        ):
            return "rotated_to_stronger_pair"
        return None

    def _find_stronger_pair(
        self, pair: str, current_pair_date, current_pair_score: float, evaluation_time
    ):
        """在共同时间锚点上寻找绝对分数更高的 pair；没有更强的返回 None。"""
        for other_pair in self.dp.current_whitelist():
            if other_pair == pair:
                continue
            candidate_rank = self._pair_score_and_direction(other_pair, evaluation_time)
            if candidate_rank is None:
                continue
            other_pair_date, other_pair_score, _ = candidate_rank
            if abs(other_pair_score) > abs(current_pair_score):
                if self._experiment_config.get("probe"):
                    self._record_rejection(
                        evaluation_time, pair, current_pair_score, current_pair_date,
                        other_pair, other_pair_score, other_pair_date,
                    )
                return other_pair, other_pair_score, other_pair_date
        return None

    def _pair_score_and_direction(self, pair: str, evaluation_time=None) -> tuple | None:
        """返回 (时间戳, 波动率归一化分数, 方向)；不可比较时返回 None。"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty:
            return None
        required_columns = {"date", "close", "&-s_return", "do_predict"}
        if not required_columns.issubset(dataframe.columns):
            return None
        if evaluation_time is not None:
            dataframe = dataframe[dataframe["date"] <= evaluation_time]
            if dataframe.empty:
                return None

        latest_row = dataframe.iloc[-1]
        if latest_row["do_predict"] != 1:
            return None
        model_prediction = float(latest_row["&-s_return"])
        if not np.isfinite(model_prediction):
            return None
        # 自己都不会入场的候选不参与比较
        if abs(model_prediction) <= self._min_prediction_to_enter:
            return None

        recent_volatility = float(dataframe["close"].pct_change().rolling(30).std().iloc[-1])
        if np.isfinite(recent_volatility) and recent_volatility > 0:
            normalized_score = model_prediction / recent_volatility
        else:
            normalized_score = model_prediction

        signal_direction = "long" if model_prediction > 0 else "short"
        if self._experiment_config.get("probe"):
            self._write_alignment_audit(
                pair, latest_row["date"], len(dataframe), normalized_score
            )
        return latest_row["date"], normalized_score, signal_direction

    @staticmethod
    def _record_rejection(
        evaluation_time, pair, current_pair_score, current_pair_date,
        other_pair, other_pair_score, other_pair_date,
    ) -> None:
        """写入被更强 pair 拒绝的审计记录，不参与交易决策。"""
        with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "reject", "time": str(evaluation_time), "pair": pair,
                "my_score": current_pair_score, "my_date": str(current_pair_date),
                "other": other_pair, "other_score": other_pair_score,
                "other_date": str(other_pair_date),
                "same_candle": str(current_pair_date) == str(other_pair_date),
            }) + "\n")

    @staticmethod
    def _write_alignment_audit(pair, last_candle_date, row_count, normalized_score) -> None:
        """写入 pair 预测时间对齐审计记录。"""
        with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "align", "pair": pair, "last_date": str(last_candle_date),
                "rows": row_count, "score": normalized_score,
            }) + "\n")
