from __future__ import annotations

import hashlib
import inspect
from types import SimpleNamespace

import numpy as np
import pytest

from archive.fe110_10b_lowforce_20261023 import legacy_helpers
from archive.fe110_10b_lowforce_20261023.collect import reader_source, selected_steps
from archive.fe110_10b_lowforce_20261023.review import magnetic_review, scf_for_frame
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries


def test_exact_owner_function_snapshots_and_bounded_reader_compile():
    for name, binding in legacy_helpers.FUNCTION_BINDINGS.items():
        assert hashlib.sha256(inspect.getsource(getattr(legacy_helpers, name)).encode()).hexdigest() == binding["function_sha256"]
    compile(reader_source({"name": "10_B", "remote_dir": "~/sbq/known", "atom_count": 50}), "<reader>", "exec")
    assert selected_steps(296) == [264, 272, 280, 288, 295, 296]
    with pytest.raises(ValueError, match="length changed"):
        selected_steps(297)


def scf_case():
    frame = {"ionic_step": 280, "electronic_iteration": 7, "EDIFF_marker_before_force": True}
    cycle = {"cycle": 280, "ionic_step": 280, "iteration": 7, "complete": True,
             "malformed": False, "delta_e_eV": -3e-6, "delta_eps_eV": -2e-6}
    return frame, cycle, {"NELM": "200", "EDIFF": "1e-5"}


def test_exact_ionic_cycle_passes_canonical_scf_interpreter():
    result = scf_for_frame(*scf_case())
    assert result["electronically_converged"]
    assert result["last_electronic_iteration"] == 7


@pytest.mark.parametrize("field,value", [("ionic_step", 279), ("iteration", 8), ("complete", False),
                                         ("malformed", True), ("iteration", 200)])
def test_wrong_or_incomplete_cycle_cannot_borrow_final_convergence(field, value):
    frame, cycle, values = scf_case()
    cycle[field] = value
    with pytest.raises(ValueError, match="association failed"):
        scf_for_frame(frame, cycle, values)


def test_no_explicit_ediff_marker_is_not_replaced_by_small_energy_delta():
    frame, cycle, values = scf_case()
    frame["EDIFF_marker_before_force"] = False
    with pytest.raises(ValueError, match="association failed"):
        scf_for_frame(frame, cycle, values)


def test_total_moment_review_cannot_claim_local_fe_or_ground_state_validation():
    result = magnetic_review([106.] * 296, 296, selected_steps(296), 0)
    assert result["level"] == "LEGACY_TOTAL_MAGNETIZATION_ONLY"
    assert result["strict_new_static_local_moment_QC_passed"] is False
    assert result["local_Fe_signs_verified"] is False
    assert result["global_magnetic_ground_state_verified"] is False


@pytest.mark.parametrize("moments", [[106.] * 295, [np.nan] * 296, [106.] * 295 + [-1.]])
def test_missing_nonfinite_or_reversed_late_total_moments_require_review(moments):
    with pytest.raises(ValueError):
        magnetic_review(moments, 296, selected_steps(296), 0)


def test_same_geometry_with_distinct_forces_is_kept_by_legacy_joint_rule():
    common = {"calculation_group": "current_vasp_job_9848812", "origin": "expanded_closed_trajectory"}
    rows = [{**common, "sample_id": "final", "forces_eV_per_A": np.zeros((50, 3)).tolist()},
            {**common, "sample_id": "same", "forces_eV_per_A": np.full((50, 3), .01).tolist()},
            {**common, "sample_id": "different", "forces_eV_per_A": np.full((50, 3), .1).tolist()}]
    kept, redundant = legacy_helpers.collapse_redundant(rows, lambda a, b: 0.)
    assert [r["sample_id"] for r in kept] == ["final", "different"]
    assert redundant[0]["sample_id"] == "same"


def test_surface_isolation_never_uses_a_face_flip_or_half_cell_z_translation(monkeypatch):
    import spglib

    identity = np.eye(3, dtype=int)
    monkeypatch.setattr(spglib, "get_symmetry", lambda cell, symprec: {
        "rotations": np.array([identity, np.diag([1, 1, -1]), identity]),
        "translations": np.array([[0., 0., 0.], [0., 0., 0.], [0., 0., .5]]),
    })
    slab = SimpleNamespace(symbols=["Fe"], counts=[45], cell=np.eye(3), frac=np.zeros((45, 3)))
    operations = surface_pose_symmetries(slab)
    assert len(operations) == 1
    assert np.array_equal(operations[0][0], identity)
    assert np.array_equal(operations[0][1], [0., 0., 0.])
