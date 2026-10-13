"""4h 回归策略：预测未来 3 根 4h 收益率，在全池中择优，只开 1 仓。

极简持仓逻辑：每根 K 线取「预测值绝对值最大」的交易对作为目标仓位，
与当前持仓比较后调仓（一致则保持，不一致则换）。
退出统一由「目标仓位 vs 当前持仓」比较得出：没有独立的反转退出分支。

实验通过 config["my_experiment"] 切换标签与特征。

my_experiment:
  label: "raw" | "volnorm"（决定回归标签的量纲）
  features: ["laguerre", "vwmacd", "tke", "vfi", "rmi"]
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


class MyStrategy(IStrategy):
    """全池择优、只持 1 仓：每根 K 线取预测绝对值最大者为目标仓位，与持仓比较后调仓。"""

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
        """返回标签尺度模式，决定回归标签的量纲。"""
        return str(self._experiment_config.get("label", "raw"))

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """为每个配置周期添加 RSI、均线乖离、ATR 比率、相对成交量和累计动量。"""
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
        """入场信号：预测为正标做多、为负标做空；不设幅度阈值，是否最强由 confirm_trade_entry 把关。"""
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        prediction_ready = dataframe["do_predict"] == 1
        model_prediction = read_model_prediction(dataframe)

        long_mask = should_enter_long(model_prediction, prediction_ready)
        short_mask = should_enter_short(model_prediction, prediction_ready)
        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = "reg_up"
        dataframe.loc[short_mask, "enter_short"] = 1
        dataframe.loc[short_mask, "enter_tag"] = "reg_down"
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """出场信号恒为空：退出统一走 custom_exit（若在此输出会触发 EXIT_SIGNAL 而跳过 custom_exit）。"""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    # ---------------- 目标仓位轮动（核心） ----------------
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
        """开仓把关：只放行目标仓位本身（逐 pair 信号在此收敛为唯一目标）。"""
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
        """唯一退出路径：比较当前持仓与目标仓位，决定持有/换仓/离场。"""
        held_side = "short" if trade.is_short else "long"
        target = resolve_target_position(self._pool_candidates(current_time))
        action, reason = decide_position_action(
            held_pair=pair,
            held_side=held_side,
            target=target,
        )
        return None if action == "hold" else reason

    def _target_position(self, evaluation_time) -> TargetPosition:
        """每根 K 线重算目标仓位：取全池预测绝对值最大者，符号定方向。"""
        return resolve_target_position(self._pool_candidates(evaluation_time))

    def _pool_candidates(self, evaluation_time) -> tuple[PoolCandidate, ...]:
        """全池候选快照，按 K 线时间戳缓存（同一根 K 线内只算一次）。"""
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
        """读取单 pair 预测并构造候选；无效预测（do_predict != 1 / 非有限值）返回 None。"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty:
            return None
        required_columns = {"date", "close", "&-s_return", "do_predict"}
        if not required_columns.issubset(dataframe.columns):
            return None

        # 显式按 K 线时间戳设上界，避免读到未来 K 线。
        dataframe = dataframe[dataframe["date"] <= candle_timestamp]
        if dataframe.empty:
            return None

        latest_row = dataframe.iloc[-1]
        candidate = build_candidate(
            pair=pair,
            raw_prediction=latest_row["&-s_return"],
            prediction_ready=latest_row["do_predict"] == 1,
        )
        if candidate is not None and self._experiment_config.get("probe"):
            self._write_alignment_audit(
                pair, latest_row["date"], len(dataframe), candidate.raw_prediction
            )
        return candidate

    @staticmethod
    def _write_alignment_audit(pair, last_candle_date, row_count, raw_prediction) -> None:
        """写入 pair 预测时间对齐审计记录。"""
        with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "align", "pair": pair, "last_date": str(last_candle_date),
                "rows": row_count, "score": raw_prediction,
            }) + "\n")
