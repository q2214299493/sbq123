from __future__ import annotations

import pytest

from archive.fe110_joint_update_20261024.run import checked_cache, classify_gaps, merge_training


def row(sid, partition="train", status="PASS"):
    return {"sample_id": sid, "partition": partition, "data_qc_status": status,
            "magnetic_review_flags": [], "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"}


@pytest.mark.parametrize("partition", ["development", "final_test"])
def test_reserved_additions_rejected_before_descriptor_loading(partition):
    with pytest.raises(ValueError, match="training records only"):
        merge_training([row("prior")], [row("new", partition)])


@pytest.mark.parametrize("status", ["MAGNETIC_REVIEW_REQUIRED", "REJECTED_OR_INCOMPLETE"])
def test_quarantined_label_cannot_enter_coverage(status):
    with pytest.raises(ValueError, match="magnetically reviewed PASS"):
        merge_training([row("prior")], [row("new", status=status)])


def test_duplicate_prior_addition_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        merge_training([row("same")], [row("same")])


def test_quarantined_selected_label_not_counted_as_pending_usable_label():
    groups = [{"original_selected_labels_not_in_package": ["bad"]},
              {"original_selected_labels_not_in_package": ["bad", "pending"]},
              {"original_selected_labels_not_in_package": []}]
    result = classify_gaps(groups, {"bad"})
    assert [r["gap_category"] for r in result] == ["ONLY_QUARANTINED_SELECTED_LABELS",
        "EXISTING_SELECTED_LABELS_AWAIT_QC", "UNSELECTED_LOCAL_ENVIRONMENT"]
    assert result[0]["unreviewed_selected_input_ids"] == []
    assert result[1]["unreviewed_selected_input_ids"] == ["pending"]


def test_cache_content_change_rejected(tmp_path):
    path = tmp_path / ("a" * 64 + ".npz")
    path.write_bytes(b"changed descriptor")
    with pytest.raises(ValueError, match="descriptor changed"):
        checked_cache([{"sample_id": "new", "structure_sha256": "a" * 64}],
                      {"files": [{"sample_id": "new", "path": str(path), "sha256": "0" * 64}]})
