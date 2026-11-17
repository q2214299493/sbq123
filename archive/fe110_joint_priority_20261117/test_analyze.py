"""Scientific bookkeeping guards; no force-model, GPU, or DFT execution."""
from copy import deepcopy

import pytest

from archive.fe110_joint_priority_20261117.analyze import (
    BLOCKED,
    candidate_rows,
    environment_groups,
    join_frames,
    reference_context,
    symbolic_rows,
)


def pair():
    metadata = {"sample_id": "same", "partition": "train", "composition": "C2HO", "qualification_scope": "force-only",
                "structure_sha256": "coordinate", "physical_label_key": "raw:1", "joint_signature": "env",
                "DFT_fmax_eV_A": .2, "source_root": "source", "graph_signature": "graph", "force_bin": "high",
                "joint_by_scale": {"1.2": "seen", "1.25": "seen", "1.3": "seen"}}
    error = {**metadata, "same_coordinate_DFT_label_exists": True, "new_DFT_for_this_coordinate_needed": False,
             "ML_fmax_eV_A": .01, "ML_le0p05_DFT_gt0p10": True, "near_duplicate_representative": "same",
             "groups": {"adsorbate_C": {"atom_observations": 2, "vector_RMSE_eV_A": .3, "vector_MAE_eV_A": .2, "sum_squared_vector_error": .18}}}
    return metadata, error


def test_reject_same_id_other_coordinates_and_wrong_partition():
    metadata, error = pair()
    for field, value in [("structure_sha256", "other"), ("partition", "development"), ("physical_label_key", "raw:2")]:
        changed = {**error, field: value}
        with pytest.raises(ValueError, match="binding mismatch"):
            join_frames([metadata], [changed])


def test_neighbor_error_is_not_candidate_error():
    metadata, error = pair()
    joined = join_frames([metadata], [error])[0]
    candidate = {"isolation": {"train536": {"reference_id": "same", "full_RMSD_A": .15}},
                 "geometry": {"environment": {"graph_signature": "graph"}}}
    result = reference_context(candidate, {"same": joined})
    assert result["reference_actual_critical_RMSE_eV_A"] == .3
    assert result["candidate_actual_ML_DFT_error_eV_A"] is None
    joined["partition"] = "development"
    with pytest.raises(ValueError, match="training prediction"):
        reference_context(candidate, {"same": joined})


def test_source_balancing_does_not_count_repeated_frames_as_new_sources():
    metadata, error = pair()
    first = join_frames([metadata], [error])[0]
    second = deepcopy(first)
    second.update(sample_id="second", source_root="other_source")
    second["actual_error"]["groups"]["adsorbate_C"].update(vector_MAE_eV_A=.8, vector_RMSE_eV_A=.8, sum_squared_vector_error=1.28)
    rows = [first] * 10 + [second]
    result = environment_groups(rows)[0]["role_metrics"]["adsorbate_C"]
    assert result["source_balanced_frame_MAE_eV_A"] == pytest.approx(.5)
    assert result["vector_MAE_eV_A"] == pytest.approx(2.8 / 11)


def test_existing_failed_label_is_not_called_absent_or_recalculated():
    metadata, error = pair()
    frames = join_frames([metadata], [error])
    candidate = {"isolation": {"train536": {"reference_id": "same", "full_RMSD_A": .15}},
                 "geometry": {"environment": {"graph_signature": "graph"}}, "joint_by_scale": {"1.2": "new", "1.25": "new", "1.3": "new"},
                 "composition": "C2HO", "new_SP_review_blockers": ["existing_label_review"]}
    result = candidate_rows([candidate], frames, [metadata])[0]
    assert result["category"] == BLOCKED
    assert result["new_DFT_budget_allocated"] == 0
    assert result["candidate_actual_ML_DFT_error_eV_A"] is None


def test_path_target_c4_does_not_turn_c1_precursor_into_c4_geometry():
    base = {"target_carbon_groups": [2, 3, 4], "reaction": "symbolic", "geometry_path": None}
    result = symbolic_rows({"records": [{**base, "total_C_each_side": 1}, {**base, "total_C_each_side": 3}]})
    assert len(result) == 1
    assert result[0]["total_C_each_side"] == 3
    assert result[0]["actual_ML_DFT_error_eV_A"] is None
    assert result[0]["category"] != "确实缺少标注"
