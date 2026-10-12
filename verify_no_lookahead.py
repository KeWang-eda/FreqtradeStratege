"""截断不变性门禁：验证决策路径没有使用未来数据。

做法：同一时段在两个不同结束日期的回测中必须给出完全一致的交易。
若代码偷看了未来数据（例如跨 pair 比较时取到更新的一根 K 线），
短区间的交易就会与长区间中同期交易不同。

用法（先用 freqtrade backtesting 导出两个 zip）：

    python verify_no_lookahead.py <短区间zip> <长区间zip>

长区间的结束日期必须晚于短区间，两者起点相同。
退出码 0 表示通过，1 表示存在差异。
"""

import json
import sys
import zipfile


def load_trades(zip_path: str) -> list[dict]:
    """从 freqtrade 导出的 backtest zip 中读取交易列表。"""
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".json"))
        data = json.loads(zf.read(name))
    strategy = next(iter(data["strategy"]))
    return data["strategy"][strategy]["trades"]


def trade_key(trade: dict) -> tuple:
    """交易身份键：pair + 开仓时间 + 方向 + 开仓价。"""
    return (
        trade["pair"],
        trade["open_date"],
        trade["is_short"],
        round(float(trade["open_rate"]), 10),
    )


def main(short_zip: str, long_zip: str) -> int:
    short_trades = {trade_key(t): t for t in load_trades(short_zip)}
    long_trades = {trade_key(t): t for t in load_trades(long_zip)}

    only_short = sorted(k for k in short_trades if k not in long_trades)
    common = [k for k in short_trades if k in long_trades]
    exit_diff = [
        k
        for k in common
        if str(short_trades[k]["close_date"]) != str(long_trades[k]["close_date"])
        or str(short_trades[k]["exit_reason"]) != str(long_trades[k]["exit_reason"])
    ]

    print(f"短区间交易数 : {len(short_trades)}")
    print(f"长区间交易数 : {len(long_trades)}")
    print(f"共同交易数   : {len(common)}")
    print(f"仅短区间有   : {len(only_short)}")
    print(f"平仓/退出原因不一致 : {len(exit_diff)}")

    for k in only_short[:10]:
        print("  仅短区间:", k)
    for k in exit_diff[:10]:
        print("  退出不一致:", k)

    if only_short or exit_diff:
        print("\n结果: FAIL - 存在差异，决策路径可能使用了未来数据")
        return 1
    print("\n结果: PASS - 短区间交易在长区间中完全复现，无未来函数")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
