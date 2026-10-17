"""Observe installed FreqAI boundaries without changing its trainer or defaults.

Uses FreqaiDataKitchen.filter_features/make_train_test_datasets, not a replica
splitter. Native source: freqtrade/freqai/data_kitchen.py and BaseRegressionModel.
The test set used by XGBoostRegressorES is an early-stopping validation set;
this audit does not mislabel it as an untouched outer backtest period.
"""

import inspect
from copy import deepcopy
from dataclasses import asdict

import pandas as pd

from quant_strategy.config import LabelConfig
from quant_strategy.features import build_features
from quant_strategy.labels import build_labels
from quant_strategy.market_data import validate_ohlcv
from quant_strategy.market_data.time_index import timeframe_delta


def audit_native_boundaries(config: dict, frame: pd.DataFrame) -> dict:
    """Measure actual native split indices against real label-completion times."""
    from freqtrade.configuration.config_validation import validate_config_schema
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

    current = deepcopy(config)
    validate_config_schema(current)
    settings = current["freqai"]
    params = settings["feature_parameters"]
    horizon = params["label_period_candles"]
    label = LabelConfig(current.get("my_experiment", {}).get("label", "raw"), horizon)
    raw = validate_ohlcv(frame)
    features = build_features(
        raw,
        params["indicator_periods_candles"],
        current.get("my_experiment", {}).get("features", []),
    )
    labels = build_labels(raw, label, current["timeframe"])
    populated = raw.join(features).assign(**{"&-s_return": labels.target})
    kitchen = FreqaiDataKitchen(current, live=True, pair="BTC/USDT:USDT")
    kitchen.find_features(populated)
    kitchen.find_labels(populated)
    filtered, targets = kitchen.filter_features(
        populated, kitchen.training_features_list, kitchen.label_list, training_filter=True
    )
    dictionary = kitchen.make_train_test_datasets(filtered, targets)
    train = dictionary["train_features"].index
    valid = dictionary["test_features"].index
    if not len(train) or not len(valid):
        return {"status": "BLOCKED", "reason": "Native split lacks a train/validation set"}
    delta = timeframe_delta(current["timeframe"])
    boundary = (raw.date.loc[valid] + delta).min()
    unsafe = train[(labels.label_end_time.loc[train] >= boundary).to_numpy()]
    reversed_time = raw.date.loc[train].max() >= raw.date.loc[valid].min()
    violations = [
        {
            "row": int(row),
            "candle_timestamp": raw.date.loc[row].isoformat(),
            "label_end_time": labels.label_end_time.loc[row].isoformat(),
            "validation_start": boundary.isoformat(),
        }
        for row in unsafe
    ]
    return {
        "status": "FAIL" if violations or reversed_time else "PASS",
        "label_contract": asdict(label),
        "timeframe": current["timeframe"],
        "train_indices": train.tolist(),
        "validation_indices": valid.tolist(),
        "label_boundary_violations": len(violations),
        "violations": violations,
        "reversed_or_shuffled_time": bool(reversed_time),
        "validation_start": boundary.isoformat(),
        "outer_label_tail_missing": int(labels.target.tail(horizon).isna().sum()),
        "outer_label_end_max": labels.label_end_time.max().isoformat(),
        "raw_last_available_at": (raw.date.iloc[-1] + delta).isoformat(),
        "native_method": f"{FreqaiDataKitchen.__module__}.make_train_test_datasets",
        "source_line": inspect.getsourcelines(FreqaiDataKitchen.make_train_test_datasets)[1],
        "feature_scope": "Native splitter on base features; full native feature expansion is not claimed here",
        "preprocessing_scope": "Native split before pipeline fitting; no trainer or dependency monkey patch",
    }
