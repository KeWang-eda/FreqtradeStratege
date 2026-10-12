"""模型 I/O 层。

只负责 FreqAI 回归 target、预测读取、阈值解析和目标仓位决策；
不计算技术特征、不访问 DataProvider、不直接训练 XGBoost。

目标仓位决策是纯函数，不依赖 freqtrade 运行时，可直接单测。
"""

from dataclasses import dataclass

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

FREQAI_RETURN_TARGET = "&-s_return"

# 阈值必须与标签尺度绑定：raw 是原始收益率，volnorm 是「收益率 / ATR 比率」。
# 用错尺度会让阈值形同虚设（raw 配 0.4 = 要求 40% 收益，永不触发）。
LABEL_THRESHOLD_DEFAULTS = {
    "raw": {"entry_threshold": 0.005, "exit_threshold": 0.0025},
    "volnorm": {"entry_threshold": 0.4, "exit_threshold": 0.2},
}
# 合理性区间（左开右闭）；超出即判定阈值与标签尺度不匹配。
LABEL_THRESHOLD_BOUNDS = {
    "raw": (0.0, 0.05),
    "volnorm": (0.05, 3.0),
}


def set_regression_target(
    dataframe: DataFrame,
    prediction_horizon: int,
    label_scaling_mode: str,
) -> DataFrame:
    """写入 FreqAI 回归标签，支持 raw 和 volnorm 两种尺度。"""
    future_close = dataframe["close"].shift(-prediction_horizon)
    future_return = future_close / dataframe["close"] - 1.0

    if label_scaling_mode == "volnorm":
        atr_ratio = ta.ATR(dataframe, timeperiod=14) / dataframe["close"]
        dataframe[FREQAI_RETURN_TARGET] = future_return / atr_ratio.replace(0.0, np.nan)
    elif label_scaling_mode == "raw":
        dataframe[FREQAI_RETURN_TARGET] = future_return
    else:
        raise ValueError(f"Unsupported regression label mode: {label_scaling_mode}")

    return dataframe


def read_model_prediction(dataframe: DataFrame):
    """读取 FreqAI 输出的回归预测列。"""
    return dataframe[FREQAI_RETURN_TARGET]


def should_enter_long(model_prediction, prediction_ready, entry_threshold: float):
    """返回做多入场条件：预测收益高于入场阈值。"""
    return prediction_ready & (model_prediction > entry_threshold)


def should_enter_short(model_prediction, prediction_ready, entry_threshold: float):
    """返回做空入场条件：预测收益低于负的入场阈值。"""
    return prediction_ready & (model_prediction < -entry_threshold)


def resolve_label_threshold(label: str, name: str, configured_value=None) -> float:
    """按标签尺度解析并校验阈值。

    name 取 entry_threshold 或 exit_threshold；configured_value 为 None 时用默认值。
    尺度不匹配直接抛错，避免「阈值永不触发」这类静默失效。
    """
    if label not in LABEL_THRESHOLD_DEFAULTS:
        raise ValueError(f"不支持的 label: {label}")
    defaults = LABEL_THRESHOLD_DEFAULTS[label]
    if name not in defaults:
        raise ValueError(f"不支持的阈值名: {name}")

    value = float(defaults[name] if configured_value is None else configured_value)
    low, high = LABEL_THRESHOLD_BOUNDS[label]
    if not low < value <= high:
        raise ValueError(
            f"{name}={value} 与 label={label} 的尺度不匹配，"
            f"应在 ({low}, {high}] 区间内（raw 是收益率，volnorm 是 ATR 倍数）"
        )
    return value


@dataclass(frozen=True)
class PoolCandidate:
    """单个 pair 的候选状态。

    阈值不在构造时施加：开仓阶段用 entry_threshold，持仓阶段用 exit_threshold，
    同一个候选在两个阶段都要能查。
    """

    pair: str
    raw_prediction: float
    normalized_score: float | None
    comparable: bool

    @property
    def direction(self) -> str:
        """方向只由原始预测的符号决定，与能否归一化无关。"""
        return "long" if self.raw_prediction > 0 else "short"

    def passes(self, threshold: float) -> bool:
        """预测幅度是否超过给定阈值。"""
        return abs(self.raw_prediction) > threshold


@dataclass(frozen=True)
class TargetPosition:
    """目标仓位；pair 为 None 表示全池无合格候选。"""

    pair: str | None
    side: str | None


def build_candidate(
    pair: str,
    raw_prediction,
    recent_volatility,
    prediction_ready: bool,
) -> PoolCandidate | None:
    """构造候选；只过滤 do_predict 与非有限值，阈值由调用方按阶段施加。

    波动率无效时仍返回候选：保留 raw_prediction 与 direction，
    但 comparable=False、normalized_score=None，不参与跨 pair 竞争。
    """
    if not prediction_ready or raw_prediction is None:
        return None
    raw = float(raw_prediction)
    if not np.isfinite(raw):
        return None

    comparable = (
        recent_volatility is not None
        and np.isfinite(recent_volatility)
        and float(recent_volatility) > 0
    )
    return PoolCandidate(
        pair=pair,
        raw_prediction=raw,
        normalized_score=raw / float(recent_volatility) if comparable else None,
        comparable=comparable,
    )


def resolve_target_position(candidates, entry_threshold: float) -> TargetPosition:
    """全池选目标：只有 comparable 且幅度超过开仓阈值的候选参与 abs 最大竞争。"""
    eligible = [c for c in candidates if c.comparable and c.passes(entry_threshold)]
    if not eligible:
        return TargetPosition(pair=None, side=None)
    best = max(eligible, key=lambda c: abs(c.normalized_score))
    return TargetPosition(pair=best.pair, side=best.direction)


def decide_position_action(
    held_pair: str | None,
    held_side: str | None,
    held_candidate: PoolCandidate | None,
    target: TargetPosition,
    exit_threshold: float,
) -> tuple[str, str | None]:
    """当前仓位 vs 目标仓位 → (action, reason)。

    反转、强弱、轮动共用这一条比较路径，没有独立的反转退出分支。
    action: hold / rotate / exit
    """
    if target.pair is not None:
        if target.pair == held_pair and target.side == held_side:
            return ("hold", None)
        if target.pair != held_pair:
            return ("rotate", "rotate_to_stronger_pair")
        return ("rotate", "rotate_to_opposite_side")

    # 无合格目标：仅当持仓自身仍满足持仓阈值且方向自洽时继续持有。
    # 持仓阈值低于开仓阈值，避免「幅度回落到阈值下就被强平」的过度交易。
    if (
        held_candidate is not None
        and held_candidate.passes(exit_threshold)
        and held_candidate.direction == held_side
    ):
        return ("hold", None)
    return ("exit", "no_eligible_target")
