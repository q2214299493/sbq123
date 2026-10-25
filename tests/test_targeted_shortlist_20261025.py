"""Source proposals must not turn fragments, reserved data or magnetic failures into anchors."""
import pytest

from archive.fe110_targeted_shortlist_20261025.analyze import pick_labelled


def row(sid, force, **extra):
    return {"sample_id": sid, "partition": "train", "composition": "C3H2O", "data_qc_status": "PASS",
        "magnetic_review_flags": [], "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE",
        "adsorbate_component_count": 1, "graph_signature": "target", "source_group": sid,
        "movable_fmax_eV_A": force, **extra}


def test_lowest_force_fragment_or_wrong_graph_cannot_replace_intact_target():
    rows = [row("fragment", .01, adsorbate_component_count=4), row("ring", .02, graph_signature="other"),
            row("valid", 3.), row("valid_lower", 2.)]
    assert pick_labelled(rows, "C3H2O", "target")["sample_id"] == "valid_lower"


def test_existing_source_reserved_partition_and_magnetic_failure_are_excluded():
    rows = [row("same_source", .01, source_group="old_job"), row("heldout", .02, partition="final_test"),
            row("magnetic", .03, data_qc_status="MAGNETIC_REVIEW_REQUIRED"), row("valid", 2.)]
    assert pick_labelled(rows, "C3H2O", "target", "old_job")["sample_id"] == "valid"


def test_no_graph_match_does_not_invent_a_labelled_anchor():
    with pytest.raises(ValueError, match="no reviewed connected"):
        pick_labelled([row("other", .01, graph_signature="other")], "C3H2O", "target")
