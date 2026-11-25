"""Reused isolation evidence cannot admit duplicates or reserved labels."""
import copy

import pytest

from archive.fe110_joint_update_20261025.prepare import combine_candidates


def candidate(sid="new", partition="train"):
    return {"samples": [{"sample_id": sid, "partition": partition, "data_qc_status": "PASS",
        "magnetic_review_flags": [], "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"}]}


def isolation():
    return {"geometry_conflicts": [], "quarantined_sample_ids": [], "threshold_A": .20,
        "reserved_geometries": 513, "reserved_forces_or_energies_used": False}


def test_candidate_and_magnetic_grade_are_preserved_without_mutation():
    doc = candidate()
    original = copy.deepcopy(doc)
    assert combine_candidates([doc], [isolation()]) == original["samples"]
    assert doc == original


def test_reserved_candidate_rejected_before_any_descriptor_loading():
    with pytest.raises(ValueError, match="training records only"):
        combine_candidates([candidate(partition="final_test")], [isolation()])


def test_duplicate_candidate_across_review_batches_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        combine_candidates([candidate(), candidate()], [isolation(), isolation()])


@pytest.mark.parametrize("field,value", [("geometry_conflicts", ["conflict"]), ("threshold_A", .3)])
def test_conflicting_or_changed_isolation_protocol_cannot_be_reused(field, value):
    report = isolation()
    report[field] = value
    with pytest.raises(ValueError, match="isolation audit"):
        combine_candidates([candidate()], [report])
