"""Real three-pair native samples from an early prefix, without OOS research."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

from quant_strategy.config import ValidationConfig
from quant_strategy.errors import DataContractError
from quant_strategy.infrastructure.experiment_store import file_hash
from quant_strategy.research.splits import (
    DevelopmentAccess,
    build_split_plan,
    verify_split_plan,
)
from quant_strategy.validation.native_features import populate_native_features


def test_real_three_pair_native_prefix_plan_and_preprocessing_isolation(tmp_path):
    """No mock candles, target formula, feature expansion or preprocessing fit."""
    config = json.loads(Path("config.json").read_text())
    pairs = ["BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT"]
    sources = {
        pair: Path("data/futures")
        / f"{pair.replace('/', '_').replace(':', '_')}-4h-futures.feather"
        for pair in pairs
    }
    # Absence is a genuine failed integration prerequisite, never a passing skip.
    hashes = {pair: file_hash(path) for pair, path in sources.items()}
    raw = {pair: pd.read_feather(path) for pair, path in sources.items()}
    start = max(frame.date.min() for frame in raw.values())
    frames = {pair: frame.loc[frame.date >= start].iloc[:360].copy() for pair, frame in raw.items()}
    assert all(len(frame) == 360 for frame in frames.values())
    assert max(frame.date.max() for frame in frames.values()) < min(
        frame.date.iloc[int(len(frame) * 0.85)] for frame in raw.values()
    )
    panels, feature_tables = [], {}
    step = pd.Timedelta(hours=4)
    horizon = config["freqai"]["feature_parameters"]["label_period_candles"]
    assert horizon == 3 and config["timeframe"] == "4h"
    for pair in pairs:
        populated = populate_native_features(config, frames, pair)
        features = [column for column in populated if column.startswith("%")]
        keep = np.isfinite(populated[features + ["&-s_return"]].to_numpy()).all(axis=1)
        selected = populated.loc[keep]
        panel = pd.DataFrame(
            {
                "sample_id": [
                    hashlib.sha256(
                        f"{pair}:{stamp.isoformat()}:{hashes[pair]}".encode()
                    ).hexdigest()
                    for stamp in selected.date
                ],
                "pair": pair,
                "candle_timestamp": selected.date,
                "available_at": selected.date + step,
                "label_start_time": selected.date + step,
                "label_end_time": selected.date + (horizon + 1) * step,
                "data_version": hashes[pair],
            }
        )
        panels.append(panel)
        table = selected[features].copy()
        table.index = panel.sample_id
        feature_tables[pair] = table
    metadata = (
        pd.concat(panels)
        .sort_values(["available_at", "pair"], kind="stable")
        .set_index("sample_id", drop=False)
    )
    validation = asdict(ValidationConfig())
    plan = build_split_plan(metadata, validation)
    check = verify_split_plan(metadata, validation, plan)
    assert check["status"] == "PASS" and check["formal_admission"] == "BLOCKED"
    assert check["fold_count"] == 3
    access = DevelopmentAccess(metadata, plan, tmp_path / "access.jsonl")
    seen = []
    for fold in plan["folds"]:
        for pair in pairs:
            table = feature_tables[pair]
            train = [sample for sample in fold["train_ids"] if sample in table.index]
            test = [sample for sample in fold["test_ids"] if sample in table.index]
            X_train = access.select(table, train, "fit")
            scaler = StandardScaler().fit(X_train)
            np.testing.assert_allclose(
                scaler.mean_, X_train.mean().to_numpy(), rtol=1e-14, atol=1e-14
            )
            transformed = scaler.transform(access.select(table, test, "transform"))
            assert np.isfinite(transformed).all()
            seen.extend(train)
    forbidden = set(plan["holdout"]["sample_ids"]) | set(
        plan["holdout"]["excluded_development_ids"]
    )
    assert not set(seen) & forbidden
    first_pair = pairs[0]
    attempted = [
        sample
        for sample in plan["holdout"]["sample_ids"]
        if sample in feature_tables[first_pair].index
    ]
    with pytest.raises(DataContractError, match="Holdout"):
        access.select(feature_tables[first_pair], attempted, "metrics")
    assert access.events[-1]["status"] == "denied"
    assert {pair: file_hash(path) for pair, path in sources.items()} == hashes
    (tmp_path / "plan.json").write_text(json.dumps(plan, sort_keys=True))
