"""Research runs without networking; backtest-only options retain trade settings."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def audit_research(tmp_path, name, arguments):
    report = tmp_path / f"{name}.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/audit_local_network.py"),
            "--policy",
            "deny-all",
            "--report",
            str(report),
            "research",
            *arguments,
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(report.read_text())
    assert evidence["http_requests"] == evidence["socket_events"] == []
    assert not evidence["freqtrade_imported"] and not evidence["ccxt_imported"]
    return evidence


def test_research_cli_dataset_training_cv_and_comparison_without_network(tmp_path, candles):
    source = tmp_path / "candles.feather"
    candles.to_feather(source)
    config = tmp_path / "research.json"
    config.write_text(json.dumps({"research": {"data": {"BTC": str(source)}}}))
    for command in ("validate", "dataset-build"):
        audit_research(tmp_path, command, [command, "-c", str(config)])
    output = tmp_path / "artifacts"
    audit_research(
        tmp_path,
        "training",
        ["run", "-c", str(config), "--output", str(output), "--experiment-id", "offline"],
    )
    audit_research(tmp_path, "comparison", ["compare", str(output / "offline")])
    manifest = json.loads((output / "offline/manifest.json").read_text())
    assert manifest["status"] == "complete"
    folds = json.loads((output / "offline/folds.json").read_text())
    assert len(folds) == 3


@pytest.mark.parametrize("format", ["feather", "parquet", "csv"])
def test_local_formats_do_not_make_network_calls(tmp_path, candles, format):
    source = tmp_path / f"candles.{format}"
    if format == "feather":
        candles.to_feather(source)
    elif format == "parquet":
        candles.to_parquet(source, index=False)
    else:
        candles.to_csv(source, index=False)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"research": {"data": {"BTC": str(source)}}}))
    audit_research(tmp_path, "dataset", ["dataset-build", "-c", str(config)])


def test_backtest_override_changes_only_market_loading_scope():
    from freqtrade.misc import deep_merge_dicts

    native = json.loads((ROOT / "config.json").read_text())
    overlay = json.loads((ROOT / "configs/backtest-local.json").read_text())
    overlay.pop("_comment")
    effective = deep_merge_dicts(overlay, deepcopy(native))
    assert effective["exchange"]["ccxt_config"]["options"]["fetchMarkets"]["types"] == ["linear"]
    effective["exchange"]["ccxt_config"].pop("options")
    assert effective == native


@pytest.mark.parametrize("mode", ["backtest", "dry_run", "live"])
def test_framework_download_gate_is_preserved(monkeypatch, mode):
    from freqtrade.enums import RunMode
    from freqtrade.freqai import utils
    from freqtrade.resolvers.freqaimodel_resolver import FreqaiModelResolver

    from MyStrategy import MyStrategy

    calls = []
    monkeypatch.setattr(FreqaiModelResolver, "load_freqaimodel", lambda config: SimpleNamespace())
    monkeypatch.setattr(
        utils, "download_all_data_for_training", lambda dp, config: calls.append(config["runmode"])
    )
    strategy = MyStrategy({"freqai": {"enabled": True}, "runmode": RunMode(mode)})
    strategy.dp = SimpleNamespace()
    strategy.load_freqAI_model()
    assert len(calls) == (0 if mode == "backtest" else 1)
