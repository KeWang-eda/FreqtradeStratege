"""纯工具层：常量、数据校验、时间切片、审计日志写入、按 K 线缓存。

从 MyStrategy.py 原样搬出，函数名与行为保持不变；不含任何交易逻辑，
不读取 config、不训练模型、不下单。
"""

import json
from pathlib import Path

# 跨 pair 时间对齐审计日志（JSONL，追加写入）。
# 仅在 config.json 的 my_experiment.probe = true 时写入，生产保持 false。
ALIGN_AUDIT_LOG = Path(__file__).resolve().parent / "logs" / "align_audit.jsonl"

# 构造候选前，预测 dataframe 必须齐备的列。
REQUIRED_COLUMNS = {"date", "close", "&-s_return", "do_predict"}


class CandleCache:
    """按 K 线时间戳缓存一个值；时间戳不变则复用，变了才重算。

    等价于原先手工维护的元组缓存 `(candle_timestamp, value)`，
    但把「比较时间戳 / 重算 / 回写」收进类里，调用方不再关心存储细节。
    """

    def __init__(self):
        self._timestamp = None
        self._value = None

    def get_or_compute(self, candle_timestamp, compute):
        """命中则返回缓存值；未命中则调用 compute() 并缓存其结果。"""
        if self._timestamp == candle_timestamp:
            return self._value
        value = compute()
        self._timestamp = candle_timestamp
        self._value = value
        return value


def _load_valid_dataframe(pair, timeframe, dp):
    """读取并校验单 pair 的分析数据；不可用时返回 None。

    等价于原先内联在 _pair_candidate 里的检查：
    读取抛异常 / 返回 None / 空表 / 缺少 REQUIRED_COLUMNS 任一列 → None。
    """
    try:
        dataframe, _ = dp.get_analyzed_dataframe(pair, timeframe)
    except Exception:
        return None
    if dataframe is None or dataframe.empty:
        return None
    if not REQUIRED_COLUMNS.issubset(dataframe.columns):
        return None
    return dataframe


def _slice_until(dataframe, candle_timestamp):
    """按 K 线时间戳截断，返回切片后的 DataFrame（显式设上界，避免读到未来 K 线）。"""
    return dataframe[dataframe["date"] <= candle_timestamp]


def _latest_row_before(dataframe, candle_timestamp):
    """按 K 线时间戳截断，返回最新一行；截断后为空返回 None。"""
    sliced = _slice_until(dataframe, candle_timestamp)
    if sliced.empty:
        return None
    return sliced.iloc[-1]


def _latest_row_and_count_before(dataframe, candle_timestamp):
    """返回 (最新行, 截断后行数)；无数据返回 (None, 0)。

    只切片一次，行数与最新行同源，避免切片与计数各算一遍。
    """
    sliced = _slice_until(dataframe, candle_timestamp)
    if sliced.empty:
        return None, 0
    return sliced.iloc[-1], len(sliced)


def _write_alignment_audit(pair, last_candle_date, row_count, raw_prediction) -> None:
    """写入 pair 预测时间对齐审计记录。"""
    with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "kind": "align", "pair": pair, "last_date": str(last_candle_date),
            "rows": row_count, "score": raw_prediction,
        }) + "\n")
