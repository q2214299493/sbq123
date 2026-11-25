import pytest

from archive.fe110_joint_update512_20261027.run import classify_current_gaps


def gap(members, selected=()):
    return {"sample_ids": members, "original_selected_labels_not_in_package": list(selected)}


def test_failed_new_target_is_not_called_an_unreviewed_original_label():
    result = classify_current_gaps([gap(["failed_target"])], {"old_quarantine"}, "failed_target")[0]
    assert result["gap_category"] == "EXCLUDED_TARGET_LABEL_PRESENT"
    assert result["excluded_completed_target_label_ids"] == ["failed_target"]
    assert result["unreviewed_selected_input_ids"] == []
    assert result["raw_force_imputed_from_geometry_or_neighbors"] is False


def test_original_magnetic_or_scf_quarantine_stays_separate():
    result = classify_current_gaps([gap(["old_quarantine"], ["old_quarantine"])], {"old_quarantine"}, "failed_target")[0]
    assert result["gap_category"] == "ONLY_QUARANTINED_SELECTED_LABELS"
    assert result["excluded_completed_target_label_ids"] == []


@pytest.mark.parametrize("members", [["a"], ["a", "b"]])
def test_unlabelled_environment_never_gets_a_neighbour_force(members):
    result = classify_current_gaps([gap(members)], set(), "failed_target")[0]
    assert result["gap_category"] == "UNSELECTED_LOCAL_ENVIRONMENT"
    assert result["qualified_DFT_forces_for_missing_geometries"] == "UNKNOWN_NOT_IMPUTED"
