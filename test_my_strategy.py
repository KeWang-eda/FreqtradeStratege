import pandas as pd

from MyStrategy import MyStrategy
from model_io import (
    exit_long_signal,
    exit_short_signal,
    make_next_direction_labels,
)


def test_threshold_direction_labels_and_unfinished_tail():
    """验证兼容标签函数的上行、下行、flat 和尾部 NaN 行为。"""
    close = pd.Series([100.0, 100.3, 99.6, 99.5])
    labels = make_next_direction_labels(close, horizon=1, threshold=0.002)

    assert labels.iloc[0] == "up"
    assert labels.iloc[1] == "down"
    assert labels.iloc[2] == "flat"
    assert pd.isna(labels.iloc[3])


class _FakeDataProvider:
    """只实现择优逻辑需要的两个方法。"""

    def __init__(self, frames: dict, whitelist: list):
        self._frames = frames
        self._whitelist = whitelist

    def current_whitelist(self):
        """返回全部参与比较的 pair。"""
        return list(self._whitelist)

    def get_analyzed_dataframe(self, pair, timeframe):
        """返回该 pair 的固定分析数据；时间戳对测试无意义故返回 None。"""
        return self._frames[pair], None


class _FakeTrade:
    """custom_exit 已不再读取持仓方向，仅需一个占位对象。"""

    is_short = False


def _make_strategy(predictions: dict) -> MyStrategy:
    """构造只带择优所需属性的策略实例。

    收盘价恒定使近 30 根波动率为 0，分数退化为原始预测值，便于断言。
    """
    dates = pd.date_range("2025-01-01", periods=40, freq="4h", tz="UTC")
    frames = {
        pair: pd.DataFrame(
            {
                "date": dates,
                "close": [100.0] * 40,
                "&-s_return": [prediction] * 40,
                "do_predict": [1] * 40,
            }
        )
        for pair, prediction in predictions.items()
    }
    strategy = MyStrategy.__new__(MyStrategy)
    strategy.config = {"my_experiment": {"entry_threshold": 0.4}}
    strategy.timeframe = "4h"
    strategy.dp = _FakeDataProvider(frames, list(predictions))
    return strategy


def test_custom_exit_has_only_two_reasons():
    """custom_exit 只应有「跌破阈值」与「被更强 pair 取代」两种退出原因。"""
    current_time = pd.Timestamp("2025-01-07", tz="UTC")

    # 持仓 pair 自身预测跌破阈值 → 退出
    below = _make_strategy({"BTC/USDT:USDT": 0.1, "ETH/USDT:USDT": 0.2})
    assert (
        below.custom_exit("BTC/USDT:USDT", _FakeTrade(), current_time, 100.0, 0.0)
        == "prediction_below_entry_threshold"
    )

    # 存在绝对分数更高的 pair → 轮换
    rotated = _make_strategy({"BTC/USDT:USDT": 0.5, "ETH/USDT:USDT": 0.9})
    assert (
        rotated.custom_exit("BTC/USDT:USDT", _FakeTrade(), current_time, 100.0, 0.0)
        == "weaker_pair_rotation"
    )

    # 自己是全场最强 → 继续持有
    strongest = _make_strategy({"BTC/USDT:USDT": 0.9, "ETH/USDT:USDT": 0.5})
    assert (
        strongest.custom_exit("BTC/USDT:USDT", _FakeTrade(), current_time, 100.0, 0.0)
        is None
    )

    # 空头信号按绝对分数参与比较（方向无关）
    short_rival = _make_strategy({"BTC/USDT:USDT": 0.5, "ETH/USDT:USDT": -0.9})
    assert (
        short_rival.custom_exit("BTC/USDT:USDT", _FakeTrade(), current_time, 100.0, 0.0)
        == "weaker_pair_rotation"
    )


def test_confirm_trade_entry_allows_only_strongest():
    """下单把关：只放行全场绝对分数最高的候选。"""
    call = {
        "order_type": "limit",
        "amount": 1.0,
        "rate": 100.0,
        "time_in_force": "gtc",
        "current_time": pd.Timestamp("2025-01-07", tz="UTC"),
        "entry_tag": "reg_up",
        "side": "long",
    }

    strongest = _make_strategy({"BTC/USDT:USDT": 0.9, "ETH/USDT:USDT": 0.5})
    assert strongest.confirm_trade_entry("BTC/USDT:USDT", **call) is True

    weaker = _make_strategy({"BTC/USDT:USDT": 0.5, "ETH/USDT:USDT": 0.9})
    assert weaker.confirm_trade_entry("BTC/USDT:USDT", **call) is False


def test_prediction_reversal_exits_via_exit_signal():
    """回归门禁：预测翻负必须产生 exit_long，退出不再依赖 custom_exit。"""
    ready = pd.Series([True, True])
    prediction_return = pd.Series([-0.8, 0.8])

    assert list(exit_long_signal(prediction_return, ready)) == [True, False]
    assert list(exit_short_signal(prediction_return, ready)) == [False, True]
