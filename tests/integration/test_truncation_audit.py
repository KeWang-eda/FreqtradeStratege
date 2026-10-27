"""Archive selection, symmetric comparison and terminal-exit handling."""

import json
import zipfile

import pytest

from quant.errors import DataContractError
from quant.validation.truncation import compare_backtests, load_backtest, main


def trade(pair="BTC", opened="2024-01-02", closed="2024-01-03", reason="rotate_to_stronger_pair"):
    return {
        "pair": pair,
        "open_date": opened,
        "close_date": closed,
        "is_short": False,
        "open_rate": 100,
        "exit_reason": reason,
    }


def archive(path, trades, end="2024-02-01"):
    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr("metadata.json", json.dumps({"MyStrategy": {"run_id": "metadata-first"}}))
        handle.writestr("config.json", json.dumps({"strategy": "MyStrategy"}))
        handle.writestr(
            "result.json",
            json.dumps(
                {
                    "strategy": {
                        "MyStrategy": {
                            "trades": trades,
                            "backtest_start": "2024-01-01",
                            "backtest_end": end,
                        }
                    }
                }
            ),
        )


def test_extra_long_overlap_trade_is_detected(tmp_path):
    short, long = tmp_path / "short.zip", tmp_path / "long.zip"
    archive(short, [trade()])
    archive(long, [trade(), trade("ETH", "2024-01-05")], "2024-03-01")
    report = compare_backtests(load_backtest(short), load_backtest(long))
    assert not report["passed"] and len(report["only_long"]) == 1
    assert main([str(short), str(long), "--report", str(tmp_path / "report.json")]) == 1
    assert (tmp_path / "report.json").exists()


def test_forced_boundary_closure_and_post_overlap_trades_do_not_fail(tmp_path):
    short, long = tmp_path / "short.zip", tmp_path / "long.zip"
    archive(short, [trade(closed="2024-01-31 23:59:00", reason="force_exit")])
    archive(long, [trade(closed="2024-02-02"), trade("ETH", "2024-02-05")], "2024-03-01")
    assert main([str(short), str(long)]) == 0


def test_changed_exit_is_a_failure(tmp_path):
    short, long = tmp_path / "short.zip", tmp_path / "long.zip"
    archive(short, [trade()])
    archive(long, [trade(closed="2024-01-04")], "2024-03-01")
    assert main([str(short), str(long)]) == 1


def test_malformed_archive_explicitly_fails(tmp_path):
    invalid = tmp_path / "invalid.zip"
    with zipfile.ZipFile(invalid, "w") as handle:
        handle.writestr("meta.json", "{}")
    with pytest.raises(DataContractError):
        load_backtest(invalid)
    assert main([str(invalid), str(invalid)]) == 2
