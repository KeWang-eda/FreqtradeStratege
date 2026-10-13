"""模型 I/O 层：FreqAI 回归标签、预测读取、目标仓位决策（纯函数，可单测）。"""

from dataclasses import dataclass

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

FREQAI_RETURN_TARGET = "&-s_return"


def set_regression_target(
    dataframe: DataFrame,
    prediction_horizon: int,
    label_scaling_mode: str,
) -> DataFrame:
    """写入 FreqAI 回归标签（raw=原始收益率，volnorm=收益率/ATR）；清理零价与无穷值。"""
    if prediction_horizon < 1:
        raise ValueError("prediction_horizon must be at least 1")

    close_series = dataframe["close"].replace(0.0, np.nan)
    future_close = close_series.shift(-prediction_horizon)
    future_return = future_close / close_series - 1.0

    if label_scaling_mode == "volnorm":
        atr_ratio = ta.ATR(dataframe, timeperiod=14) / close_series
        target = future_return / atr_ratio.replace(0.0, np.nan)
    elif label_scaling_mode == "raw":
        target = future_return
    else:
        raise ValueError(f"Unsupported regression label mode: {label_scaling_mode}")

    dataframe[FREQAI_RETURN_TARGET] = target.replace([np.inf, -np.inf], np.nan)
    return dataframe


def read_model_prediction(dataframe: DataFrame):
    """读取 FreqAI 输出的回归预测列。"""
    return dataframe[FREQAI_RETURN_TARGET]


def should_enter_long(model_prediction, prediction_ready):
    """返回做多入场条件：预测收益为正（不做阈值过滤）。"""
    return prediction_ready & (model_prediction > 0)


def should_enter_short(model_prediction, prediction_ready):
    """返回做空入场条件：预测收益为负（不做阈值过滤）。"""
    return prediction_ready & (model_prediction < 0)


@dataclass(frozen=True)
class PoolCandidate:
    """单个 pair 的候选：只保留原始带符号预测值，方向由符号决定。"""

    pair: str
    raw_prediction: float

    @property
    def direction(self) -> str:
        """方向只由原始预测的符号决定。"""
        return "long" if self.raw_prediction > 0 else "short"


@dataclass(frozen=True)
class TargetPosition:
    """目标仓位；pair 为 None 表示全池无可用预测（预测缺失或非有限值）。"""

    pair: str | None
    side: str | None


def build_candidate(
    pair: str,
    raw_prediction,
    prediction_ready: bool,
) -> PoolCandidate | None:
    """构造候选；无效预测（do_predict != 1 / None / NaN / Inf）返回 None，不设幅度阈值。"""
    if not prediction_ready or raw_prediction is None:
        return None
    raw = float(raw_prediction)
    if not np.isfinite(raw):
        return None
    return PoolCandidate(pair=pair, raw_prediction=raw)


def resolve_target_position(candidates) -> TargetPosition:
    """全池择优：取预测值绝对值最大者为目标，符号定方向；无候选则空目标。"""
    if not candidates:
        return TargetPosition(pair=None, side=None)
    best = max(candidates, key=lambda c: abs(c.raw_prediction))
    return TargetPosition(pair=best.pair, side=best.direction)


def decide_position_action(
    held_pair: str | None,
    held_side: str | None,
    target: TargetPosition,
) -> tuple[str, str | None]:
    """调仓决策：持仓与目标一致则 hold，不一致则 rotate，无目标则 exit。"""
    if target.pair is not None:
        if target.pair == held_pair and target.side == held_side:
            return ("hold", None)
        if target.pair != held_pair:
            return ("rotate", "rotate_to_stronger_pair")
        return ("rotate", "rotate_to_opposite_side")

    # 无可用目标：平掉当前仓位，保持空仓。
    return ("exit", "no_eligible_target")
