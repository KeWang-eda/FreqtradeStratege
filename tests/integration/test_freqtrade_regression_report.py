"""Regression reports must detect changed predictions even with equal trades."""

import io
import json
import zipfile

import joblib
import pandas as pd

from tools.verify_freqtrade_regression import compare_runs


def make_run(path, prediction=1.0, profit=1.0):
    path.mkdir()
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=1, tz="UTC"),
            "&-s_return": [prediction],
            "do_predict": [1],
        }
    )
    trade = {
        "pair": "BTC",
        "open_date": "2024-01-01",
        "close_date": "2024-01-02",
        "is_short": False,
        "open_rate": 100,
        "exit_reason": "rotate_to_stronger_pair",
    }
    with zipfile.ZipFile(path / "result.zip", "w") as archive:
        archive.writestr(
            "result.json",
            json.dumps(
                {
                    "strategy": {
                        "MyStrategy": {
                            "backtest_start": "2024-01-01",
                            "backtest_end": "2024-01-03",
                            "trades": [trade],
                            "profit_total_abs": profit,
                        }
                    }
                }
            ),
        )
        for kind in ("signals", "rejected", "exited"):
            buffer = io.BytesIO()
            joblib.dump({"MyStrategy": {"BTC": frame}}, buffer)
            archive.writestr(f"result_{kind}.pkl", buffer.getvalue())
    frame.to_feather(path / "btc_prediction.feather")
    (path / "btc_metadata.json").write_text(
        json.dumps(
            {
                "training_features_list": ["%x"],
                "label_list": ["&-s_return"],
                "labels_mean": {"&-s_return": 0.1},
                "labels_std": {"&-s_return": 0.2},
            }
        )
    )


def test_equivalent_native_runs_pass(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old)
    make_run(new)
    report = compare_runs(old, new)
    assert report["passed"] and not report["differences"]
    assert report["trade_count"] == {"old": 1, "new": 1}


def test_prediction_difference_fails_even_when_trades_match(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old)
    make_run(new, prediction=2.0)
    report = compare_runs(old, new)
    assert not report["passed"]
    assert report["trade_count"] == {"old": 1, "new": 1}
    assert any("prediction.feather" in difference for difference in report["differences"])


def test_metric_difference_fails_even_when_trades_and_predictions_match(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old)
    make_run(new, profit=2.0)
    report = compare_runs(old, new)
    assert not report["passed"]
    assert "metric/profit_total_abs: differs or missing" in report["differences"]
