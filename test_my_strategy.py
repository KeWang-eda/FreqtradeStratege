"""目标仓位极简逻辑测试。"""

import numpy as np
import pandas as pd

from model import (
    build_candidate,
    decide_position_action,
    resolve_target_position,
    set_regression_target,
    should_enter_long,
    should_enter_short,
)


def candidate(pair, raw_prediction):
    """构造有效候选。"""
    return build_candidate(pair, raw_prediction, prediction_ready=True)


def test_invalid_prediction_is_filtered():
    """只过滤框架标记无效、None、NaN、Inf 的预测。"""
    assert build_candidate("BTC", 0.9, prediction_ready=False) is None
    assert build_candidate("BTC", None, prediction_ready=True) is None
    assert build_candidate("BTC", float("nan"), prediction_ready=True) is None
    assert build_candidate("BTC", float("inf"), prediction_ready=True) is None


def test_every_valid_prediction_can_compete_without_threshold():
    """不设开仓阈值：任意可信预测都参与竞争。"""
    target = resolve_target_position([candidate("BTC", 0.001), candidate("ETH", -0.002)])
    assert target.pair == "ETH"
    assert target.side == "short"


def test_target_uses_absolute_raw_prediction():
    """目标是原始预测绝对值最大的交易对。"""
    target = resolve_target_position([candidate("BTC", 0.9), candidate("ETH", -1.5)])
    assert target.pair == "ETH"
    assert target.side == "short"


def test_empty_candidates_mean_empty_target():
    """全池无有效预测时保持空仓。"""
    target = resolve_target_position([])
    assert (target.pair, target.side) == (None, None)


def test_same_pair_and_side_holds():
    """当前仓位与目标一致时保持。"""
    target = resolve_target_position([candidate("BTC", 0.9)])
    assert decide_position_action("BTC", "long", target) == ("hold", None)


def test_different_pair_rotates():
    """目标交易对变化时换仓。"""
    target = resolve_target_position([candidate("ETH", 1.5), candidate("BTC", 0.9)])
    assert decide_position_action("BTC", "long", target) == (
        "rotate",
        "rotate_to_stronger_pair",
    )


def test_same_pair_opposite_side_rotates():
    """同一交易对方向反转时换仓。"""
    target = resolve_target_position([candidate("BTC", -1.5)])
    assert decide_position_action("BTC", "long", target) == (
        "rotate",
        "rotate_to_opposite_side",
    )


def test_no_target_exits_current_position():
    """全池无有效目标时平仓保持空仓。"""
    target = resolve_target_position([])
    assert decide_position_action("BTC", "long", target) == (
        "exit",
        "no_eligible_target",
    )


def test_entry_signal_uses_only_prediction_sign():
    """入场只看可信预测的符号，不看幅度阈值。"""
    ready = pd.Series([True, True, True, False])
    prediction = pd.Series([0.001, -0.001, 0.0, 2.0])
    assert list(should_enter_long(prediction, ready)) == [True, False, False, False]
    assert list(should_enter_short(prediction, ready)) == [False, True, False, False]


def test_regression_target_rejects_bad_horizon_and_cleans_nonfinite_values():
    """标签生成拒绝非法 horizon，并清理无穷标签。"""
    dataframe = pd.DataFrame({"close": [100.0, 0.0, 101.0, 102.0, 103.0]})
    try:
        set_regression_target(dataframe.copy(), 0, "raw")
    except ValueError:
        pass
    else:
        raise AssertionError("prediction_horizon=0 应该报错")

    target_frame = set_regression_target(dataframe.copy(), 1, "raw")
    assert not np.isinf(target_frame["&-s_return"].to_numpy()).any()
    assert target_frame["&-s_return"].isna().any()


def test_strategy_class_contract():
    """策略必须保留 custom_exit 所需的类级配置。"""
    from MyStrategy import MyStrategy

    assert MyStrategy.use_exit_signal is True
    assert MyStrategy.minimal_roi == {"0": 999.0}
    assert MyStrategy.stoploss == -1.0
    assert MyStrategy.trailing_stop is False
    assert MyStrategy.can_short is True
    assert MyStrategy.timeframe == "4h"
