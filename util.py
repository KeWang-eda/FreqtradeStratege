"""纯工具层：常量、数据校验、时间切片、审计日志写入。

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


def _latest_row_before(dataframe, candle_timestamp):
    """按 K 线时间戳截断，返回最新一行；截断后为空返回 None。

    显式设上界，避免读到未来 K 线。
    """
    dataframe = dataframe[dataframe["date"] <= candle_timestamp]
    if dataframe.empty:
        return None
    return dataframe.iloc[-1]


def _write_alignment_audit(pair, last_candle_date, row_count, raw_prediction) -> None:
    """写入 pair 预测时间对齐审计记录。"""
    with ALIGN_AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "kind": "align", "pair": pair, "last_date": str(last_candle_date),
            "rows": row_count, "score": raw_prediction,
        }) + "\n")
