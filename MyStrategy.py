"""4h 回归策略：预测未来 3 根 4h 收益率，在全池中择优，只开 abs(分数) 最大的 1 仓。

退出统一由「目标仓位 vs 当前持仓」比较得出：没有独立的反转退出分支。

实验通过 config["my_experiment"] 切换标签与特征。

my_experiment:
  label: "raw" | "volnorm"（决定阈值尺度）
  features: ["laguerre", "vwmacd", "tke", "vfi", "rmi"]
  entry_threshold: float（可省略，按 label 取默认值）
  exit_threshold: float（可省略，按 label 取默认值；应低于 entry_threshold）
  probe: bool（记录跨 pair 时间对齐）
"""

import json
from pathlib import Path

import numpy as np
from pandas import DataFrame

from feature import (
    add_baseline_features,
    add_basic_price_features,
    add_period_expanded_features,
)
from model import (
    PoolCandidate,
    TargetPosition,
    build_candidate,
    decide_position_action,
    read_model_prediction,
    resolve_label_threshold,
    resolve_target_position,
    set_regression_target,
    should_enter_long,
    should_enter_short,
)
from freqtrade.exchange import timeframe_to_prev_date
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

# 跨 pair 时间对齐审计日志（JSONL，追加写入）。
# 仅在 config.json 的 my_experiment.probe = true 时写入，生产保持 false。
ALIGN_AUDIT_LOG = Path(__file__).resolve().parent / "logs" / "align_audit.jsonl"

# 波动率归一化窗口，单位：K 线根数（4h × 30 = 5 天）。
VOLATILITY_WINDOW_CANDLES = 30


class MyStrategy(IStrategy):
    """预测未来 3 根 4h K 线收益率，并在全池中只持有一个最强的仓位。"""

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
    # 必须为 True：should_exit 里整个 custom_exit 调用块都在 `if self.use_exit_signal:` 内
    # （interface.py:1462），设为 False 会让 custom_exit 从不被调用、仓位永不轮动。
    # 退出统一走 custom_exit：populate_exit_trend 恒输出 0，使 exit_ 恒为 False，
    # 从而绕过 `exit_ and not enter → EXIT_SIGNAL` 这条会跳过 custom_exit 的分支。
    use_exit_signal = True
    trailing_stop = False

    # ---------------- 实验配置 ----------------
    @property
    def _experiment_config(self) -> dict:
        """返回实验开关；来源是 config.json 的 my_experiment。"""
        return self.config.get("my_experiment", {}) or {}

    @property
    def _label_scaling_mode(self) -> str:
        """返回标签尺度模式，决定阈值的量纲。"""
        return str(self._experiment_config.get("label", "raw"))

    @property
    def _entry_threshold(self) -> float:
        """开仓阈值：低于它的候选不参与择优。"""
        return resolve_label_threshold(
            self._label_scaling_mode,
            "entry_threshold",
            self._experiment_config.get("entry_threshold"),
        )

    @property
    def _exit_threshold(self) -> float:
        """持仓阈值：低于它且方向不再自洽才平仓；低于开仓阈值以减少过度交易。"""
        return resolve_label_threshold(
            self._label_scaling_mode,
            "exit_threshold",
            self._experiment_config.get("exit_threshold"),
        )

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """为每个配置周期添加 RSI、均线乖离、ATR 比率、相对成交量和累计动量。

        刻意保持低维：337 特征版本（含高阶矩/MAX/非流动性）实测把截面 top-1 的
        t 值从 +2.53 打到 -0.01，特征数 337 对训练样本 641 严重过拟合。
        低维特征集在同一窗口反而更稳。
        """
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
            self._label_scaling_mode,
        )

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """交给 FreqAI 训练/加载模型，并返回带预测列的分析数据。"""
        return self.freqai.start(dataframe, metadata, self)

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """逐 pair 产生入场资格；是否最强由 confirm_trade_entry 把关。"""
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        prediction_ready = dataframe["do_predict"] == 1
        model_prediction = read_model_prediction(dataframe)
        entry_threshold = self._entry_threshold

        long_mask = should_enter_long(model_prediction, prediction_ready, entry_threshold)
        short_mask = should_enter_short(model_prediction, prediction_ready, entry_threshold)
        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = "reg_up"
        dataframe.loc[short_mask, "enter_short"] = 1
        dataframe.loc[short_mask, "enter_tag"] = "reg_down"
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """留空：退出统一走 custom_exit 的目标仓位比较。

        若这里输出 exit_long/exit_short，框架在 `exit_ and not enter` 时会走
        EXIT_SIGNAL 而跳过 custom_exit（interface.py:1462），等于同时存在两套
        退出逻辑，与「统一由目标仓位轮动决定退出」冲突。
        """
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    # ---------------- 目标仓位轮动 ----------------
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
        """只放行目标仓位本身的开仓；其余候选等目标变化后再说。"""
        target = self._target_position(current_time)
        return target.pair == pair and target.side == side

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        """目标仓位轮动的唯一退出路径：反转、强弱、轮动共用同一段比较。"""
        held_side = "short" if trade.is_short else "long"
        candidates = self._pool_candidates(current_time)
        target = resolve_target_position(candidates, self._entry_threshold)

        held_candidate = next(
            (c for c in candidates if c.pair == pair and c.passes(self._exit_threshold)),
            None,
        )
        action, reason = decide_position_action(
            held_pair=pair,
            held_side=held_side,
            held_candidate=held_candidate,
            target=target,
            exit_threshold=self._exit_threshold,
        )
        return None if action == "hold" else reason

    def _target_position(self, evaluation_time) -> TargetPosition:
        """全池择优得到目标仓位。"""
        return resolve_target_position(
            self._pool_candidates(evaluation_time), self._entry_threshold
        )

    def _pool_candidates(self, evaluation_time) -> tuple[PoolCandidate, ...]:
        """全池候选快照，按 K 线时间戳缓存，同一根 K 线内只算一次。"""
        candle_timestamp = timeframe_to_prev_date(self.timeframe, evaluation_time)
        cached = getattr(self, "_pool_cache", None)
        if cached is not None and cached[0] == candle_timestamp:
            return cached[1]

        candidates = tuple(
            candidate
            for candidate in (
                self._pair_candidate(pair, candle_timestamp)
                for pair in self.dp.current_whitelist()
            )
            if candidate is not None
        )
        self._pool_cache = (candle_timestamp, candidates)
        return candidates

    def _pair_candidate(self, pair: str, candle_timestamp) -> PoolCandidate | None:
        """读取单个 pair 在指定 K 线上的候选；数据不足或不可用时返回 None。"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty:
            return None
        required_columns = {"date", "close", "&-s_return", "do_predict"}
        if not required_columns.issubset(dataframe.columns):
            return None

        # 显式按 K 线时间戳设上界：不依赖框架切片是否已推进，避免读到未来 K 线。
        dataframe = dataframe[dataframe["date"] <= candle_timestamp]
        if dataframe.empty:
            return None

        latest_row = dataframe.iloc[-1]
        recent_volatility = (
            dataframe["close"].pct_change().rolling(VOLATILITY_WINDOW_CANDLES).std().iloc[-1]
        )
        candidate = build_candidate(
            pair=pair,
            raw_prediction=latest_row["&-s_return"],
            recent_volatility=recent_volatility,
            prediction_ready=latest_row["do_predict"] == 1,
        )
        if candidate is not None and self._experiment_config.get("probe"):
            self._write_alignment_audit(
                pair, latest_row["date"], len(dataframe), candidate.normalized_score
            )
        return candidate

    @staticmethod
    def _write_alignment_audit(pair, last_candle_date, row_count, normalized_score) -> None:
        """写入 pair 预测时间对齐审计记录。"""
        with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "align", "pair": pair, "last_date": str(last_candle_date),
                "rows": row_count, "score": normalized_score,
            }) + "\n")
