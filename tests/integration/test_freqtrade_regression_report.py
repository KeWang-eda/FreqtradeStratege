"""Regression reports must detect changed predictions even with equal trades."""

import io
import json
import zipfile

import joblib
import pandas as pd
import pytest

from tools.verify_freqtrade_regression import _equivalent, compare_runs, main


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
            "result_config.json",
            json.dumps(
                {
                    "freqai": {"train_period_days": 365},
                    "exchange": {"name": "binance"},
                    "config_files": ["config.json"],
                }
            ),
        )
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


def test_model_search_path_relocation_does_not_change_runtime_configuration(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old)
    make_run(new)

    def add_relocated_model_path(contents):
        value = json.loads(contents["result_config.json"])
        value["freqaimodel_path"] = "quant/models/freqai"
        contents["result_config.json"] = json.dumps(value)

    edit_archive(new, add_relocated_model_path)
    report = compare_runs(old, new)
    assert report["passed"]


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


def edit_archive(path, edit):
    with zipfile.ZipFile(path / "result.zip") as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    edit(contents)
    with zipfile.ZipFile(path / "result.zip", "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)


def edit_result(path, edit):
    def apply(contents):
        value = json.loads(contents["result.json"])
        edit(value["strategy"]["MyStrategy"])
        contents["result.json"] = json.dumps(value)

    edit_archive(path, apply)


@pytest.mark.parametrize(
    "field",
    [
        "pair",
        "is_short",
        "open_date",
        "close_date",
        "open_rate",
        "exit_reason",
        "missing",
        "extra",
        "order",
        "boolean",
    ],
)
def test_trade_and_nested_order_mutations_fail(tmp_path, field):
    old, new = tmp_path / "old", tmp_path / "new"
    for path in (old, new):
        make_run(path)
        edit_result(
            path, lambda r: r["trades"][0].update(orders=[{"amount": 1, "price": 100, "fee": 0.1}])
        )

    def mutate(result):
        trade = result["trades"][0]
        if field == "missing":
            del trade["orders"][0]["fee"]
        elif field == "extra":
            trade["unknown"] = None
        elif field == "order":
            trade["orders"][0]["fee"] = 0.2
        elif field == "boolean":
            trade["is_short"] = 0
        else:
            trade[field] = {
                "pair": "ETH",
                "is_short": True,
                "open_date": "2024-01-01 04:00",
                "close_date": "2024-01-02 04:00",
                "open_rate": 101,
                "exit_reason": "changed",
            }[field]

    edit_result(new, mutate)
    report = compare_runs(old, new)
    assert not report["passed"] and report["differences"]


@pytest.mark.parametrize("kind", ["signals", "rejected", "exited"])
def test_each_signal_export_mutation_fails(tmp_path, kind):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old)
    make_run(new)

    def mutate(contents):
        name = f"result_{kind}.pkl"
        data = joblib.load(io.BytesIO(contents[name]))
        data["MyStrategy"]["BTC"]["&-s_return"] = 999
        buffer = io.BytesIO()
        joblib.dump(data, buffer)
        contents[name] = buffer.getvalue()

    edit_archive(new, mutate)
    assert not compare_runs(old, new)["passed"]


@pytest.mark.parametrize(
    "mutation", ["feature_order", "label", "statistics", "extra", "missing", "other_metadata"]
)
def test_all_model_metadata_is_compared(tmp_path, mutation):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old)
    make_run(new)
    path = new / "btc_metadata.json"
    value = json.loads(path.read_text())
    if mutation == "feature_order":
        value["training_features_list"].insert(0, "%another_feature")
    elif mutation == "label":
        value["label_list"] = ["&different"]
        value["labels_mean"] = {"&different": 0.1}
        value["labels_std"] = {"&different": 0.2}
    elif mutation == "statistics":
        value["labels_std"]["&-s_return"] += 1e-13  # Preserve original exact metadata comparison.
    elif mutation == "extra":
        value["extra"] = None
    elif mutation == "missing":
        del value["labels_mean"]
    else:
        value["extra_returns_per_train"] = {"unexpected": 1}
    path.write_text(json.dumps(value))
    if mutation == "missing":
        with pytest.raises(ValueError, match="Incomplete model metadata"):
            compare_runs(old, new)
    else:
        assert not compare_runs(old, new)["passed"]


@pytest.mark.parametrize(
    "failure",
    [
        "prediction_missing",
        "prediction_extra",
        "metadata_missing",
        "signals_missing",
        "archive_missing",
    ],
)
def test_missing_and_extra_artifacts_cannot_pass(tmp_path, failure):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old)
    make_run(new)
    if failure == "prediction_missing":
        (new / "btc_prediction.feather").unlink()
    elif failure == "prediction_extra":
        (new / "extra_prediction.feather").write_bytes(
            (new / "btc_prediction.feather").read_bytes()
        )
    elif failure == "metadata_missing":
        (new / "btc_metadata.json").unlink()
    elif failure == "signals_missing":
        edit_archive(new, lambda contents: contents.pop("result_signals.pkl"))
    else:
        (new / "result.zip").unlink()
    report = tmp_path / "report.json"
    assert main([str(old), str(new), "--report", str(report)]) != 0
    assert json.loads(report.read_text())["passed"] is False


def test_paired_frame_nan_masks_allowed_but_not_mask_mismatch(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old, prediction=float("nan"))
    make_run(new, prediction=float("nan"))
    assert compare_runs(old, new)["passed"]
    frame = pd.read_feather(new / "btc_prediction.feather")
    frame["&-s_return"] = 0
    frame.to_feather(new / "btc_prediction.feather")
    assert not compare_runs(old, new)["passed"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_json_metrics_rejected_even_if_equal(tmp_path, value):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old, profit=value)
    make_run(new, profit=value)
    with pytest.raises(ValueError, match="Non-finite JSON"):
        compare_runs(old, new)


def test_only_wall_clock_metric_fields_are_excluded(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    for path in (old, new):
        make_run(path)
    edit_result(old, lambda r: r.update(backtest_run_start_ts=1, backtest_run_end_ts=2))
    edit_result(new, lambda r: r.update(backtest_run_start_ts=3, backtest_run_end_ts=4))
    assert compare_runs(old, new)["passed"]
    edit_result(new, lambda r: r.update(extra_metric=1))
    assert not compare_runs(old, new)["passed"]


def test_userdir_root_normalization_retains_relative_model_path(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    for root in (old, new):
        make_run(root)
        path = root / "models/run/subtrain/btc_metadata.json"
        path.parent.mkdir(parents=True)
        value = json.loads((root / "btc_metadata.json").read_text())
        value["data_path"] = str(path.parent)
        path.write_text(json.dumps(value))
        (root / "btc_metadata.json").unlink()
    assert compare_runs(old, new)["passed"]
    path = new / "models/run/subtrain/btc_metadata.json"
    value = json.loads(path.read_text())
    value["data_path"] = "/tmp/wrong/model"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="artifact location"):
        compare_runs(old, new)


def test_boolean_is_not_numeric_equivalent():
    assert not _equivalent(True, 1) and not _equivalent(False, 0)


@pytest.mark.parametrize(
    "mutation",
    ["train_period", "model", "feature_order", "transport", "source_order", "missing_config"],
)
def test_all_exported_configuration_is_compared(tmp_path, mutation):
    old, new = tmp_path / "old", tmp_path / "new"
    make_run(old)
    make_run(new)

    def mutate(contents):
        if mutation == "missing_config":
            contents.pop("result_config.json")
            return
        value = json.loads(contents["result_config.json"])
        if mutation == "train_period":
            value["freqai"]["train_period_days"] = 1
        elif mutation == "model":
            value["freqaimodel"] = "different"
        elif mutation == "feature_order":
            value["freqai"]["feature_parameters"] = {"indicator_periods_candles": [14, 6]}
        elif mutation == "transport":
            value["exchange"]["ccxt_config"] = {"timeout": 123}
        else:
            value["config_files"] = ["configs/backtest-local.json", "config.json"]
        contents["result_config.json"] = json.dumps(value)

    edit_archive(new, mutate)
    if mutation == "missing_config":
        with pytest.raises(ValueError, match="exported configuration"):
            compare_runs(old, new)
    else:
        report = compare_runs(old, new)
        assert not report["passed"] and any("configuration/" in v for v in report["differences"])
