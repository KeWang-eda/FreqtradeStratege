"""Real sample IDs obey all existing split modes; this is not OOS evaluation."""

import pytest

from tools.audit_split_foundations import audit


def test_three_real_data_split_protocols_have_disjoint_traceable_sample_ids():
    report = audit(["configs/base.yaml", "configs/environment/local.yaml"], bars=240)
    assert report["status"] == "PASS"
    assert report["models_trained"] == 0 and not report["final_holdout_unlocked"]
    for folds in report["methods"].values():
        for fold in folds:
            assert fold["passed"]
            assert set(fold["train_ids"]).isdisjoint(fold["test_ids"])
            assert set(fold["train_ids"]).isdisjoint(fold["purged_ids"])
            assert set(fold["train_ids"]).isdisjoint(fold["embargoed_ids"])
            assert fold["training_information_end"] < fold["test_information_start"]


def test_insufficient_real_history_cannot_shrink_requested_development_prefix():
    with pytest.raises(ValueError, match="unshortened"):
        audit(["configs/base.yaml", "configs/environment/local.yaml"], bars=1_000_000)
