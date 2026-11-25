import numpy as np
import pytest

from archive.fe110_fixed53_comparison_20261027.analyze import force_bin, force_metrics, frame_records, role_indices, summarize


def test_vector_rmse_uses_xyz_sum_and_atom_mean_and_detects_opposition():
    ref = np.array([[1, 0, 0], [0, 2, 0]], dtype=float)
    pred = np.array([[-1, 0, 0], [0, 2, 3]], dtype=float)
    metrics = force_metrics(ref, pred)
    assert metrics["vector_rmse_eV_A"] == pytest.approx(np.sqrt(6.5))
    assert metrics["vector_mae_eV_A"] == 2.5
    assert metrics["component_mae_eV_A"] == pytest.approx(5 / 6)
    assert metrics["direction_eligible_count"] == 2
    assert metrics["opposed_direction_count"] == 1


def test_empty_and_near_zero_forces_do_not_become_zero_error_coverage():
    assert force_metrics(np.empty((0, 3)), np.empty((0, 3)))["vector_rmse_eV_A"] is None
    metrics = force_metrics([[0, 0, 0]], [[1, 0, 0]])
    assert metrics["vector_rmse_eV_A"] == 1
    assert metrics["mean_direction_cosine"] is None
    assert summarize([])["coverage"] == "NO_TEST_COVERAGE"


@pytest.mark.parametrize("ref,pred", [([[0, 0, 0]], [[0, 0]]), ([[0, 0, 0]], [[float("nan"), 0, 0]])])
def test_invalid_force_arrays_rejected(ref, pred):
    with pytest.raises(ValueError):
        force_metrics(ref, pred)


def test_force_bins_are_right_closed_and_include_zero():
    assert force_bin(0) == "[0,0.05]"
    assert force_bin(0.05) == "[0,0.05]"
    assert force_bin(0.0500001) == "(0.05,0.1]"
    assert force_bin(10) == "(5,10]"
    assert force_bin(10.1) == "(10,inf)"
    with pytest.raises(ValueError):
        force_bin(-1)


def test_fixed_atoms_excluded_and_inconsistent_local_Fe_partition_rejected():
    row = {"symbols": ["Fe"] * 45 + ["C", "C", "O"], "fixed_atom_indices_0based": list(range(18)),
        "force_role_groups": {"adsorbate_C": [45, 46], "adsorbate_O": [47], "adsorbate_H": [],
            "near_Fe": [44], "other_Fe": list(range(18, 44))}}
    assert role_indices(row)["movable"] == list(range(18, 48))
    row["force_role_groups"]["near_Fe"] = [43, 44]
    with pytest.raises(ValueError):
        role_indices(row)


@pytest.mark.parametrize("cached_field", ["movable_fmax_eV_A", "adsorbate_fmax_eV_A", None])
def test_reference_force_bins_recomputed_across_legacy_and_static_schemas(cached_field):
    row = {"sample_id": "test", "symbols": ["Fe"] * 45 + ["C"], "fixed_atom_indices_0based": list(range(18)),
        "force_role_groups": {"adsorbate_C": [45], "adsorbate_O": [], "adsorbate_H": [], "near_Fe": [44], "other_Fe": list(range(18, 44))},
        "forces_eV_per_A": [[0, 0, 0]] * 45 + [[0.03, 0.04, 0]], "structure_sha256": "a" * 64,
        "composition": "C", "source_collection": "test", "calculation_group": "test", "source_job_id": "test", "magnetic_review_level": "test"}
    if cached_field:
        row[cached_field] = 0.05
    pred = {model: {"test": {"structure_sha256": "a" * 64, "predicted_forces_eV_per_A": row["forces_eV_per_A"]}}
        for model in ["baseline", "control", "new512"]}
    assert frame_records([row], pred)[0]["frame"]["force_bin"] == "[0,0.05]"
    if cached_field:
        row[cached_field] = 0.5
        with pytest.raises(ValueError):
            frame_records([row], pred)
