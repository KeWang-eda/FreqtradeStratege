"""目标仓位轮动的纯逻辑测试。

决策函数不依赖 freqtrade 运行时，因此这里不需要 fake DataProvider。
"""

import numpy as np
import pandas as pd
import pytest

from model import (
    build_candidate,
    decide_position_action,
    resolve_label_threshold,
    resolve_target_position,
    set_regression_target,
    should_enter_long,
    should_enter_short,
)

ENTRY_VOLNORM = 0.4
EXIT_VOLNORM = 0.2


def _candidate(pair, raw, volatility):
    """构造候选的测试助手。"""
    return build_candidate(pair, raw, volatility, prediction_ready=True)


# ---------------- 漏洞 2：阈值与标签尺度绑定 ----------------

def test_threshold_is_bound_to_label_scale():
    """阈值必须按 label 解析，尺度不匹配直接报错，不静默失效。"""
    assert resolve_label_threshold("volnorm", "entry_threshold") == 0.4
    assert resolve_label_threshold("raw", "entry_threshold") == 0.005
    assert resolve_label_threshold("volnorm", "exit_threshold") == 0.2
    assert resolve_label_threshold("raw", "exit_threshold") == 0.0025

    # raw 配 volnorm 量级的阈值 → 要求 40% 收益，必须报错而不是默默不触发
    with pytest.raises(ValueError, match="尺度不匹配"):
        resolve_label_threshold("raw", "entry_threshold", 0.4)
    # volnorm 配 raw 量级的阈值 → 几乎必然触发，同样报错
    with pytest.raises(ValueError, match="尺度不匹配"):
        resolve_label_threshold("volnorm", "entry_threshold", 0.005)

    with pytest.raises(ValueError):
        resolve_label_threshold("three_class", "entry_threshold")


# ---------------- 漏洞 1：开仓阈值 vs 持仓阈值 ----------------

def test_hold_when_below_entry_but_above_exit():
    """幅度回落到开仓阈值下、但仍在持仓阈值上且方向一致 → 继续持有，不强平。"""
    held = _candidate("BTC", 0.3, 0.02)          # 0.3 < 0.4 但 > 0.2
    target = resolve_target_position([held], ENTRY_VOLNORM)
    assert target.pair is None                    # 不足以开新仓

    action, reason = decide_position_action(
        "BTC", "long", held, target, EXIT_VOLNORM
    )
    assert (action, reason) == ("hold", None)


def test_exit_when_below_exit_threshold():
    """幅度跌破持仓阈值 → 平仓。"""
    held = _candidate("BTC", 0.1, 0.02)           # 0.1 < 0.2
    target = resolve_target_position([held], ENTRY_VOLNORM)
    action, reason = decide_position_action(
        "BTC", "long", held, target, EXIT_VOLNORM
    )
    assert (action, reason) == ("exit", "no_eligible_target")


def test_exit_when_held_direction_flipped():
    """方向反转 → 即使幅度未达开仓阈值也应离场，不能因为阈值把方向信息丢掉。"""
    flipped = _candidate("BTC", -0.3, 0.02)       # 方向 short，幅度 -0.3
    target = resolve_target_position([flipped], ENTRY_VOLNORM)
    assert target.pair is None

    action, reason = decide_position_action(
        "BTC", "long", flipped, target, EXIT_VOLNORM
    )
    assert (action, reason) == ("exit", "no_eligible_target")


# ---------------- 漏洞 3：方向比较统一用 side ----------------

def test_reversal_uses_side_not_numeric_direction():
    """反转判定只比较 target.side 与 held_side，不引入数字方向。"""
    flipped_strong = _candidate("BTC", -0.9, 0.02)   # -45.0，强空
    target = resolve_target_position([flipped_strong], ENTRY_VOLNORM)

    assert target.pair == "BTC"
    assert target.side == "short"
    action, reason = decide_position_action(
        "BTC", "long", flipped_strong, target, EXIT_VOLNORM
    )
    assert (action, reason) == ("rotate", "rotate_to_opposite_side")


def test_hold_when_target_matches_holding():
    """目标与持仓一致 → 不动。"""
    held = _candidate("BTC", 0.9, 0.02)
    target = resolve_target_position([held], ENTRY_VOLNORM)
    action, reason = decide_position_action("BTC", "long", held, target, EXIT_VOLNORM)
    assert (action, reason) == ("hold", None)


def test_rotate_to_stronger_pair():
    """出现更强候选 → 换仓。"""
    held = _candidate("BTC", 0.9, 0.02)              # 45.0
    stronger = _candidate("DOGE", -2.4, 0.03)        # -80.0
    target = resolve_target_position([held, stronger], ENTRY_VOLNORM)

    assert target.pair == "DOGE"
    action, reason = decide_position_action("BTC", "long", held, target, EXIT_VOLNORM)
    assert (action, reason) == ("rotate", "rotate_to_stronger_pair")


# ---------------- 不可比但有符号 ----------------

def test_uncomparable_candidate_keeps_direction_but_loses_ranking():
    """波动率无效：保留 raw 与 direction，但不参与竞争，也不能当目标。"""
    broken = build_candidate("BTC", -0.9, 0.0, prediction_ready=True)
    assert broken is not None
    assert broken.comparable is False
    assert broken.normalized_score is None
    assert broken.direction == "short"

    assert resolve_target_position([broken], ENTRY_VOLNORM).pair is None

    healthy = _candidate("ETH", 0.9, 0.02)
    target = resolve_target_position([broken, healthy], ENTRY_VOLNORM)
    assert target.pair == "ETH"


def test_uncomparable_candidate_never_outranks_healthy_one():
    """不可比候选即使 raw 极大也不能污染排名。"""
    huge_uncomparable = build_candidate("BTC", 99.0, float("nan"), prediction_ready=True)
    healthy = _candidate("ETH", 0.9, 0.02)
    assert resolve_target_position([huge_uncomparable, healthy], ENTRY_VOLNORM).pair == "ETH"


def test_nan_and_not_ready_are_dropped():
    """do_predict != 1 或预测非有限值 → 无候选。"""
    assert build_candidate("BTC", 0.9, 0.02, prediction_ready=False) is None
    assert build_candidate("BTC", float("nan"), 0.02, prediction_ready=True) is None
    assert build_candidate("BTC", None, 0.02, prediction_ready=True) is None


def test_strategy_class_contract():
    """策略类级契约：防止 use_exit_signal=False 让 custom_exit 永不执行。

    should_exit 里整个 custom_exit 调用块都在 `if self.use_exit_signal:` 内
    （interface.py:1462）。设为 False 时仓位永不轮动，回测只会有 1 笔交易。
    """
    from MyStrategy import MyStrategy

    assert MyStrategy.use_exit_signal is True
    assert MyStrategy.minimal_roi == {"0": 999.0}
    assert MyStrategy.stoploss == -1.0
    assert MyStrategy.trailing_stop is False
    assert MyStrategy.can_short is True
    assert MyStrategy.timeframe == "4h"


# ---------------- model 标签边界 ----------------

def test_regression_target_rejects_bad_horizon_and_cleans_nonfinite_values():
    """标签生成拒绝非法 horizon，并把零价格产生的无穷标签清成 NaN。"""
    dataframe = pd.DataFrame({"close": [100.0, 0.0, 101.0, 102.0, 103.0]})
    with pytest.raises(ValueError, match="prediction_horizon"):
        set_regression_target(dataframe.copy(), 0, "raw")

    target_frame = set_regression_target(dataframe.copy(), 1, "raw")
    assert not np.isinf(target_frame["&-s_return"].to_numpy()).any()
    assert target_frame["&-s_return"].isna().any()


# ---------------- populate_entry_trend 的向量化条件 ----------------

def test_entry_signals_respect_threshold():
    """入场信号是向量化的，且用开仓阈值。"""
    ready = pd.Series([True, True, True])
    prediction = pd.Series([0.9, -0.9, 0.3])

    assert list(should_enter_long(prediction, ready, ENTRY_VOLNORM)) == [True, False, False]
    assert list(should_enter_short(prediction, ready, ENTRY_VOLNORM)) == [False, True, False]
