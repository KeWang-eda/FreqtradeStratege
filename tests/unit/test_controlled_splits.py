"""Full identity/reference checks, including syntactically valid forged plans."""

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict

import pandas as pd
import pytest

from quant_strategy.config import ValidationConfig
from quant_strategy.errors import DataContractError
from quant_strategy.research.splits import (
    DevelopmentAccess,
    build_split_plan,
    verify_split_plan,
)


def make_metadata(count=120):
    rows = []
    step = pd.Timedelta(hours=4)
    for number, stamp in enumerate(pd.date_range("2024-01-01", periods=count, freq="4h", tz="UTC")):
        for pair in ("BNB/USDT:USDT", "BTC/USDT:USDT", "ETH/USDT:USDT"):
            rows.append(
                {
                    "sample_id": f"{pair}:{number}",
                    "pair": pair,
                    "candle_timestamp": stamp,
                    "available_at": stamp + step,
                    "label_start_time": stamp + step,
                    "label_end_time": stamp + 4 * step,
                    "data_version": hashlib.sha256(pair.encode()).hexdigest(),
                }
            )
    return pd.DataFrame(rows).set_index("sample_id", drop=False)


@pytest.fixture
def inputs():
    metadata = make_metadata()
    validation = asdict(ValidationConfig())
    return metadata, validation, build_split_plan(metadata, validation)


def rehash(plan):
    """Attacker can update every public digest; independent sets must still win."""
    for current in [*plan["folds"], plan]:
        current.pop("sha256", None)
        current["sha256"] = hashlib.sha256(
            json.dumps(current, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()


def test_complete_global_time_plan_and_each_sample_assignment(inputs):
    metadata, validation, plan = inputs
    report = verify_split_plan(metadata, validation, plan)
    assert report["status"] == "PASS" and report["formal_admission"] == "BLOCKED"
    assert report["holdout_count"] == 54 and report["guard_excluded_count"] == 9
    assert len(plan["records"]) == len(metadata)
    assert set(record["sample_id"] for record in plan["records"]) == set(metadata.index)
    boundary = pd.Timestamp(plan["holdout"]["start"])
    for fold in plan["folds"]:
        train = metadata.loc[fold["train_ids"]]
        test = metadata.loc[fold["test_ids"]]
        assert train.label_end_time.lt(test.available_at.min()).all()
        assert test.label_end_time.lt(boundary).all()
        assert set(train.available_at).isdisjoint(test.available_at)
        assert set(train.index).isdisjoint(test.index)
        assert fold["counts"]["raw_train"] == sum(
            fold["counts"][name] for name in ("train", "purged", "embargoed")
        )
        assert len(fold["assignments"]) == len(plan["development_ids"])
        for _, same_time in metadata.groupby("available_at"):
            assert not (
                set(same_time.index).intersection(train.index)
                and set(same_time.index).intersection(test.index)
            )


def test_strict_label_end_equality_and_excess_purged_safe_row_kept(inputs):
    metadata, _, plan = inputs
    fold = plan["folds"][0]
    start = pd.Timestamp(fold["test_start"])
    raw = metadata.loc[fold["raw_train_ids"]]
    equal = set(raw.loc[raw.label_end_time.eq(start)].index)
    greater = set(raw.loc[raw.label_end_time.gt(start)].index)
    less = set(raw.loc[raw.label_end_time.lt(start)].index)
    assert equal and greater and less
    assert equal | greater == set(fold["purged_ids"])
    assert less == set(fold["train_ids"])


def test_embargo_is_additional_and_cannot_replace_label_purge(inputs):
    metadata, validation, _ = inputs
    validation["embargo_candles"] = 5
    plan = build_split_plan(metadata, validation)
    assert verify_split_plan(metadata, validation, plan)["status"] == "PASS"
    for fold in plan["folds"]:
        assert len(fold["purged_ids"]) == 9
        assert len(fold["embargoed_ids"]) == 6
        assert set(fold["purged_ids"]).isdisjoint(fold["embargoed_ids"])


@pytest.mark.parametrize(
    "method", ["fixed_holdout", "expanding_window", "rolling_window", "purged_walk_forward"]
)
def test_supported_native_protocols_have_independent_reference_check(inputs, method):
    metadata, validation, _ = inputs
    validation["method"] = method
    validation["train_window_size"] = 20 if method == "rolling_window" else None
    plan = build_split_plan(metadata, validation)
    assert verify_split_plan(metadata, validation, plan)["status"] == "PASS"
    assert len(plan["folds"]) == (1 if method == "fixed_holdout" else 3)


def test_zero_label_span_still_obeys_embargo(inputs):
    metadata, validation, _ = inputs
    metadata["label_end_time"] = metadata.available_at
    plan = build_split_plan(metadata, validation)
    verify_split_plan(metadata, validation, plan)
    assert not plan["holdout"]["excluded_development_ids"]
    assert all(not fold["purged_ids"] and fold["embargoed_ids"] for fold in plan["folds"])


@pytest.mark.parametrize(
    "fault",
    [
        "naive",
        "nonutc",
        "missing_time",
        "offgrid",
        "duplicate_index",
        "duplicate_pair_candle",
        "index_identity_mismatch",
        "gap",
        "unsorted",
        "label_before_available",
        "wrong_availability",
        "empty",
    ],
)
def test_invalid_metadata_rejected_by_builder_and_independent_verifier(inputs, fault):
    metadata, validation, plan = inputs
    bad = metadata.copy()
    if fault == "naive":
        bad["available_at"] = bad.available_at.dt.tz_localize(None)
    elif fault == "nonutc":
        bad["available_at"] = bad.available_at.dt.tz_convert("Asia/Shanghai")
    elif fault == "missing_time":
        bad.loc[bad.index[5], "label_end_time"] = pd.NaT
    elif fault == "offgrid":
        bad.loc[bad.index[5], "label_end_time"] += pd.Timedelta(minutes=1)
    elif fault == "duplicate_index":
        bad = pd.concat([bad.iloc[:1], bad])
    elif fault == "duplicate_pair_candle":
        for column in ("candle_timestamp", "available_at", "label_start_time", "label_end_time"):
            bad.loc[bad.index[3], column] = bad.iloc[0][column]
    elif fault == "index_identity_mismatch":
        bad["sample_id"] = bad.sample_id.iloc[::-1].to_numpy()
    elif fault == "gap":
        bad = bad.drop(index=bad.index[30])
    elif fault == "unsorted":
        bad = bad.iloc[::-1]
    elif fault == "label_before_available":
        bad.loc[bad.index[5], "label_end_time"] = bad.iloc[5].candle_timestamp
    elif fault == "wrong_availability":
        bad["available_at"] += pd.Timedelta(hours=4)
    else:
        bad = bad.iloc[:0]
    with pytest.raises(DataContractError):
        build_split_plan(bad, validation)
    with pytest.raises(DataContractError):
        verify_split_plan(bad, validation, plan)


@pytest.mark.parametrize("count", [1, 4, 8])
def test_insufficient_history_cannot_be_silently_shortened(count):
    with pytest.raises(
        DataContractError, match="Insufficient|[Ee]mpty|no development|No independently"
    ):
        build_split_plan(make_metadata(count), asdict(ValidationConfig()))
    with pytest.raises(DataContractError):
        verify_split_plan(make_metadata(count), asdict(ValidationConfig()), {})


def test_requested_minimum_history_not_reduced(inputs):
    metadata, validation, _ = inputs
    validation["min_train_size"] = 1000
    with pytest.raises(DataContractError, match="min_train_size"):
        build_split_plan(metadata, validation)


@pytest.mark.parametrize(
    "fault",
    [
        "boundary",
        "test_deletion",
        "train_test_overlap",
        "drop_safe_train",
        "undo_purge",
        "undo_embargo",
        "train_into_holdout",
        "developer_label_into_holdout",
        "drop_holdout",
        "change_validation",
        "change_assignment",
        "formal_scope",
    ],
)
def test_independent_verifier_rejects_rehashed_self_consistent_looking_forgeries(inputs, fault):
    metadata, validation, original = inputs
    validation = {**validation, "embargo_candles": 5}
    plan = deepcopy(build_split_plan(metadata, validation))
    fold = plan["folds"][0]
    if fault == "boundary":
        fold["test_start"] = metadata.iloc[0].available_at.isoformat()
    elif fault == "test_deletion":
        removed = fold["test_ids"].pop()
        fold["raw_test_ids"].remove(removed)
        fold["counts"]["test"] -= 1
        fold["counts"]["raw_test"] -= 1
        fold["assignments"] = [x for x in fold["assignments"] if x["sample_id"] != removed]
    elif fault == "train_test_overlap":
        fold["train_ids"].append(fold["test_ids"][0])
    elif fault == "drop_safe_train":
        fold["train_ids"].pop()
        fold["counts"]["train"] -= 1
    elif fault in {"undo_purge", "undo_embargo"}:
        group = "purged_ids" if fault == "undo_purge" else "embargoed_ids"
        fold["train_ids"].append(fold[group].pop())
    elif fault == "train_into_holdout":
        fold["train_ids"].append(plan["holdout"]["sample_ids"][0])
    elif fault == "developer_label_into_holdout":
        plan["development_ids"].append(plan["holdout"]["excluded_development_ids"].pop())
    elif fault == "drop_holdout":
        plan["holdout"]["sample_ids"].pop()
    elif fault == "change_validation":
        plan["validation"]["final_holdout_fraction"] = 0.1
    elif fault == "change_assignment":
        fold["assignments"][0]["assignment"] = "test"
    else:
        plan["scope"] = "formal"
    rehash(plan)
    assert plan["sha256"] != original["sha256"]
    with pytest.raises(DataContractError, match="Independent split verification mismatch"):
        verify_split_plan(metadata, validation, plan)


def test_shortened_input_does_not_validate_the_frozen_complete_plan(inputs):
    metadata, validation, plan = inputs
    shortened = metadata.iloc[:300]
    with pytest.raises(DataContractError, match="metadata_sha256"):
        verify_split_plan(shortened, validation, plan)


def test_independent_verifier_does_not_call_builder_or_native_splitter(inputs, monkeypatch):
    from quant_strategy.research import splits

    metadata, validation, plan = inputs

    def forbidden(*args, **kwargs):
        raise AssertionError("independent check cannot trust builder or production splitter")

    monkeypatch.setattr(splits, "build_split_plan", forbidden)
    monkeypatch.setattr(splits.TimeSeriesSplitter, "split", forbidden)
    assert verify_split_plan(metadata, validation, plan)["status"] == "PASS"


@pytest.mark.parametrize("group", ["sample_ids", "excluded_development_ids"])
@pytest.mark.parametrize(
    "purpose", ["train", "fit", "transform", "tune", "predict", "metrics", "validation", "test"]
)
def test_holdout_and_guard_denied_for_every_computational_access_and_logged(
    inputs, tmp_path, group, purpose
):
    metadata, _, plan = inputs
    audit = tmp_path / "access.jsonl"
    access = DevelopmentAccess(metadata, plan, audit)
    frame = pd.DataFrame({"%feature": range(len(metadata))}, index=metadata.index)
    with pytest.raises(DataContractError, match="Holdout or label-boundary"):
        access.select(frame, plan["holdout"][group][:1], purpose)
    events = [json.loads(line) for line in audit.read_text().splitlines()]
    assert events[-1]["status"] == "denied" and events[-1]["purpose"] == purpose
    assert events[0]["purpose"] == "register_metadata"
    assert not any(event["status"] == "allowed" for event in events)


def test_allowed_selection_preserves_identity_and_supports_subset_frames(inputs, tmp_path):
    metadata, _, plan = inputs
    access = DevelopmentAccess(metadata, plan, tmp_path / "access.jsonl")
    ids = plan["folds"][0]["train_ids"]
    frame = metadata.loc[ids].copy()
    selected = access.select(frame, ids[::-1], "fit")
    assert selected.index.tolist() == ids[::-1]
    selected.loc[selected.index[0], "pair"] = "MUTATED"
    assert frame.loc[selected.index[0], "pair"] != "MUTATED"
    assert access.events[-1]["status"] == "allowed"


@pytest.mark.parametrize(
    "fault", ["unknown_id", "duplicate_id", "wrong_index", "wrong_purpose", "empty"]
)
def test_access_identity_errors_fail_closed_and_are_recorded(inputs, fault):
    metadata, _, plan = inputs
    access = DevelopmentAccess(metadata, plan)
    frame = metadata.copy()
    ids = plan["folds"][0]["train_ids"][:2]
    purpose = "fit"
    if fault == "unknown_id":
        ids = ["unknown"]
    elif fault == "duplicate_id":
        ids = ids * 2
    elif fault == "wrong_index":
        frame["sample_id"] = frame.sample_id.iloc[::-1].to_numpy()
    elif fault == "wrong_purpose":
        purpose = "formal_training"
    else:
        ids = []
    with pytest.raises(DataContractError):
        access.select(frame, ids, purpose)
    assert access.events[-1]["status"] == "denied"


def test_same_input_is_deterministic_and_no_source_metadata_is_modified(inputs):
    metadata, validation, plan = inputs
    before = metadata.copy(deep=True)
    assert build_split_plan(metadata, validation) == plan
    pd.testing.assert_frame_equal(metadata, before)
