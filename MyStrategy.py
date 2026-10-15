"""4h 回归策略：预测未来 3 根 4h 收益率，在全池中择优，只开 1 仓。

极简持仓逻辑：每根 K 线取「预测值绝对值最大」的交易对作为目标仓位，
与当前持仓比较后调仓（一致则保持，不一致则换）。
退出统一由「目标仓位 vs 当前持仓」比较得出：没有独立的反转退出分支。

实验通过 config["my_experiment"] 切换标签与特征。

my_experiment:
  label: "raw" | "volnorm"（决定回归标签的量纲）
  features: ["laguerre", "vwmacd", "tke", "vfi", "rmi"]
  probe: bool（记录跨 pair 时间对齐）

纯工具函数（数据校验、时间切片、审计日志）在 util.py。
"""

import json
import math

from pandas import DataFrame, concat

from feature import add_baseline_features, add_basic_price_features, add_period_expanded_features
from model import (
    PoolCandidate, TargetPosition, build_candidate, decide_position_action,
    read_model_prediction, resolve_target_position, set_regression_target,
    should_enter_long, should_enter_short,
)
from freqtrade.exchange import timeframe_to_prev_date
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from util import ALIGN_AUDIT_LOG


class MyStrategy(IStrategy):
    """全池择优、只持 1 仓：每根 K 线取预测绝对值最大者为目标仓位，与持仓比较后调仓。"""

    MAX_LIVE_SNAPSHOT_ROWS = 500
    timeframe = "4h"
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True

    def leverage(self, pair: str, current_time, current_rate: float, proposed_leverage: float,
                 max_leverage: float, entry_tag: str | None, side: str, **kwargs) -> float:
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
    def _label_scaling_mode(self) -> str:
        """返回标签尺度模式，决定回归标签的量纲。"""
        return str(self._experiment_config.get("label", "raw"))

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, metadata: dict, **kwargs) -> DataFrame:
        """为每个配置周期添加 RSI、均线乖离、ATR 比率、相对成交量和累计动量。"""
        return add_period_expanded_features(dataframe, period)

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """添加收益率、振幅、实体和成交量变化等基础价量特征。"""
        return add_basic_price_features(dataframe)

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """添加标准波动/时间特征，并按配置追加 technical 候选指标。"""
        return add_baseline_features(dataframe, self._experiment_config.get("features", []))

    # ---------------- 回归标签 ----------------
    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """写入回归标签；训练由 config 的原生 XGBoostRegressor 负责。"""
        prediction_horizon = int(self.freqai_info["feature_parameters"].get("label_period_candles", 1))
        return set_regression_target(dataframe, prediction_horizon, self._label_scaling_mode)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """交给 FreqAI 训练/加载模型，并返回带预测列的分析数据。"""
        dataframe = self.freqai.start(dataframe, metadata, self)
        self._remember_prediction_snapshot(metadata.get("pair"), dataframe)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
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

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """出场信号恒为空：退出统一走 custom_exit（若在此输出会触发 EXIT_SIGNAL 而跳过 custom_exit）。"""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    # ---------------- 目标仓位轮动（核心） ----------------
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """开仓把关：只放行目标仓位本身（逐 pair 信号在此收敛为唯一目标）。"""
        candidates = self._pool_candidates(current_time)
        if candidates is None:
            return False
        target = resolve_target_position(candidates)
        return target.pair == pair and target.side == side

    def custom_exit(self, pair: str, trade: Trade, current_time, current_rate: float,
                    current_profit: float, **kwargs):
        """唯一退出路径：比较当前持仓与目标仓位，决定持有/换仓/离场。"""
        held_side = "short" if trade.is_short else "long"
        candidates = self._pool_candidates(current_time)
        if candidates is None:
            return None
        target = resolve_target_position(candidates)
        action, reason = decide_position_action(held_pair=pair, held_side=held_side, target=target)
        return None if action == "hold" else reason

    def _target_position(self, evaluation_time) -> TargetPosition | None:
        """每根 K 线重算目标仓位：取全池预测绝对值最大者，符号定方向。"""
        candidates = self._pool_candidates(evaluation_time)
        return None if candidates is None else resolve_target_position(candidates)

    def _pool_candidates(self, evaluation_time) -> tuple[PoolCandidate, ...] | None:
        """全池候选快照，按 K 线时间戳缓存（同一根 K 线内只算一次）。

        不完整的实时快照返回 None 且不能缓存。这样如果某个 pair 晚一点才完成
        同一根 K 线，后续调用仍会重新检查，而不会把暂时缺数据误当成空目标。
        """
        candle_timestamp = timeframe_to_prev_date(self.timeframe, evaluation_time)
        if getattr(self, "_pool_cache_timestamp", None) == candle_timestamp:
            return self._pool_cache_value

        candidates = self._compute_candidates(candle_timestamp)
        if candidates is None:
            return None

        self._pool_cache_timestamp = candle_timestamp
        self._pool_cache_value = candidates
        return candidates

    def _compute_candidates(self, candle_timestamp) -> tuple[PoolCandidate, ...] | None:
        """只在全池都有同一根 K 线时构造候选，否则返回不完整标记。"""
        pairs = tuple(self.dp.current_whitelist())
        if not pairs:
            return None

        # 先检查完整性，再构造任何候选，避免把不同时间的预测放进同一排名。
        snapshot_rows = {
            pair: self._snapshot_row(pair, candle_timestamp) for pair in pairs
        }
        if any(row is None for row in snapshot_rows.values()):
            if self._experiment_config.get("probe"):
                for pair, row_data in snapshot_rows.items():
                    row, row_count = row_data or (None, 0)
                    self._record_alignment_probe(
                        pair=pair,
                        candle_timestamp=candle_timestamp,
                        last_candle_date=None if row is None else row["date"],
                        row_count=row_count,
                        raw_prediction=None if row is None else row["&-s_return"],
                        complete=False,
                    )
            return None

        return tuple(
            candidate for candidate in (
                self._pair_candidate(pair, candle_timestamp)
                for pair in pairs
            ) if candidate is not None
        )

    def _pair_candidate(self, pair: str, candle_timestamp) -> PoolCandidate | None:
        """从统一时间快照读取单 pair 预测；无效预测返回 None。"""
        row_data = self._snapshot_row(pair, candle_timestamp)
        if row_data is None:
            return None
        latest_row, row_count = row_data

        candidate = build_candidate(pair=pair, raw_prediction=latest_row["&-s_return"],
                                    prediction_ready=latest_row["do_predict"] == 1)
        if self._experiment_config.get("probe"):
            self._record_alignment_probe(
                pair=pair,
                candle_timestamp=candle_timestamp,
                last_candle_date=latest_row["date"],
                row_count=row_count,
                raw_prediction=None if candidate is None else candidate.raw_prediction,
                complete=True,
            )
        return candidate

    def _remember_prediction_snapshot(self, pair: str | None, dataframe: DataFrame) -> None:
        """保存带日期的预测，避免依赖回测引擎当前 pair 的可见行。"""
        if not pair or dataframe is None:
            return
        required = {"date", "&-s_return", "do_predict"}
        if not required.issubset(dataframe.columns):
            return

        current = dataframe[["date", "&-s_return", "do_predict"]].copy()
        current = current.dropna(subset=["date"]).sort_values("date")
        if not self._keep_full_snapshot_history():
            current = current.tail(self.MAX_LIVE_SNAPSHOT_ROWS)
        previous = getattr(self, "_prediction_snapshots", {}).get(pair)
        if previous is not None:
            current = concat([previous, current], ignore_index=True)
        current = current.drop_duplicates(subset=["date"], keep="last").sort_values("date")
        if not self._keep_full_snapshot_history():
            current = current.tail(self.MAX_LIVE_SNAPSHOT_ROWS)
        self._prediction_snapshots = getattr(self, "_prediction_snapshots", {})
        self._prediction_snapshots[pair] = current.reset_index(drop=True)

    def _keep_full_snapshot_history(self) -> bool:
        """回测需覆盖整个历史；实盘只保留最近窗口，避免重复合并无限增长。"""
        runmode = self.config.get("runmode")
        runmode_value = getattr(runmode, "value", runmode)
        return runmode_value in {"backtest", "hyperopt"}

    def _snapshot_row(self, pair: str, candle_timestamp):
        """返回指定 candle 的精确预测行和截至该 candle 的行数。"""
        snapshot = getattr(self, "_prediction_snapshots", {}).get(pair)
        if snapshot is None or snapshot.empty:
            return None
        matched = snapshot.loc[snapshot["date"] == candle_timestamp]
        if matched.empty:
            return None
        row_count = int((snapshot["date"] <= candle_timestamp).sum())
        return matched.iloc[-1], row_count

    @staticmethod
    def _write_alignment_probe(
        pair: str,
        candle_timestamp,
        last_candle_date,
        row_count: int,
        raw_prediction,
        complete: bool,
    ) -> None:
        """写入带目标 candle 的对齐审计记录。"""
        ALIGN_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        try:
            score = None if raw_prediction is None else float(raw_prediction)
        except (TypeError, ValueError):
            score = None
        if score is not None and not math.isfinite(score):
            score = None

        record = {
            "kind": "align",
            "candle_timestamp": str(candle_timestamp),
            "pair": pair,
            "last_date": None if last_candle_date is None else str(last_candle_date),
            "rows": row_count,
            "score": score,
            "complete": complete,
        }
        with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str, allow_nan=False) + "\n")

    def _record_alignment_probe(self, **kwargs) -> None:
        """同一 candle/pair 只记录一次；状态变化时允许追加一条新记录。"""
        if not self._experiment_config.get("probe"):
            return

        candle_timestamp = kwargs["candle_timestamp"]
        pair = kwargs["pair"]
        state = (
            kwargs["complete"],
            None if kwargs["last_candle_date"] is None else str(kwargs["last_candle_date"]),
        )
        if getattr(self, "_probe_candle_timestamp", None) != candle_timestamp:
            self._probe_candle_timestamp = candle_timestamp
            self._probe_states = {}
        if getattr(self, "_probe_states", {}).get(pair) == state:
            return
        self._probe_states[pair] = state
        self._write_alignment_probe(**kwargs)
