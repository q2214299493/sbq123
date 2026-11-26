import copy
from dataclasses import replace
import importlib

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.constraints import FixAtoms

from archive.fe110_pair2_20261027.review import audit_frames, fragment_formulas, post_relaxation_geometry
from archive.fe110_pair2_20261027.runtime import check_scope
from scripts.adsorption.build_fe110_adsorption import Poscar


def fixture_scope():
    scope = {"models": {"control": {"sha256": "a" * 64}, "new512": {"sha256": "b" * 64}},
        "cases": [{"name": "10_A"}, {"name": "C3_05"}],
        "limits": {"seed_max_steps": 80, "fmax_eV_per_A": 0.1, "LBFGS_maxstep_A": 0.2},
        "max_wall_seconds": 600, "CPU_count": 4, "memory_GB": 32}
    request = {"scope": scope, "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "boundaries": {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False}}
    exception = {"scope": copy.deepcopy(scope), "authorizing_user_request": "same-start paired comparison"}
    auth = {"action": "RUN_PAIRED_ML_RELAXATION", "request_sha256": "c" * 64, "user_authorized": True, "user_request": exception["authorizing_user_request"]}
    return request, auth, exception


@pytest.mark.parametrize("module", ["runtime", "prepare", "transport", "review", "prepare_dft", "verify_results"])
def test_all_task_entrypoints_import_without_private_calculations_or_execution(module):
    assert importlib.import_module("archive.fe110_pair2_20261027." + module)


def test_two_frozen_models_on_preselected_same_starts_allowed():
    request, auth, policy = fixture_scope()
    check_scope(request, auth, policy, "c" * 64)


@pytest.mark.parametrize("change", ["hash", "steps", "fmax", "case", "model", "VASP", "training", "promotion", "scheduler"])
def test_expansion_reselection_or_unreviewed_submission_cannot_pass(change):
    request, auth, policy = fixture_scope()
    if change == "hash":
        auth["request_sha256"] = "d" * 64
    elif change in ["steps", "fmax"]:
        request["scope"]["limits"]["seed_max_steps" if change == "steps" else "fmax_eV_per_A"] = 999
    elif change == "case":
        request["scope"]["cases"][0]["name"] = "unreviewed"
    elif change == "model":
        request["scope"]["models"]["new512"]["sha256"] = "d" * 64
    elif change in ["VASP", "training", "promotion"]:
        request["boundaries"]["model_promotion" if change == "promotion" else change] = True
    else:
        request["scheduler_job_id"] = "fake"
    with pytest.raises(ValueError):
        check_scope(request, auth, policy, "c" * 64)


def test_disconnected_C3_graph_is_CO_and_C2H2_not_intact_C3():
    symbols = ["C", "C", "C", "O", "H", "H"]
    product = [[0, 1], [0, 4], [0, 5], [2, 3]]
    assert fragment_formulas(symbols, product) == ["C2H2", "CO"]
    assert fragment_formulas(symbols, product + [[0, 2]]) == ["C3H2O"]


def synthetic_pose():
    cart = np.array([[2 * i, 0, 5] for i in range(45)] + [[1, 0, 6.2]], dtype=float)
    cell = np.diag([100, 100, 20])
    flags = [("F",) * 3] * 18 + [("T",) * 3] * 28
    pose = Poscar("synthetic_audit_fixture_not_physical_surface", cell, ["Fe", "C"], [45, 1], cart @ np.linalg.inv(cell), flags)
    atoms = Atoms(["Fe"] * 45 + ["C"], positions=cart, cell=cell, pbc=[True, True, False])
    atoms.set_constraint(FixAtoms(indices=list(range(18))))
    atoms.calc = SinglePointCalculator(atoms, energy=0, forces=np.zeros((46, 3)))
    return pose, atoms


def test_trajectory_checks_actual_same_start_fixed_atoms_and_coordinate_force_data():
    pose, atoms = synthetic_pose()
    result = audit_frames(pose, [atoms], pose)
    assert result["frames"] == 1
    assert result["fixed_max_displacement_A"] == 0
    changed = pose.frac.copy()
    changed[0, 0] += 0.01
    with pytest.raises(ValueError, match="start"):
        audit_frames(replace(pose, frac=changed), [atoms], pose)


def test_post_relaxation_height_does_not_reuse_initial_rigid_placement_gate():
    pose, _ = synthetic_pose()
    rules = {"contact_validation": {"hard_contact_distance_angstrom": 0.8}, "surface_reconstruction": {"maximum_slab_displacement_angstrom": 0.5}}
    result = post_relaxation_geometry(pose, pose, {"final_graph": [], "final_graph_preserved": True}, rules)
    assert result["diagnostic_DFT_geometry_ready"]
    assert result["minimum_height_above_highest_relaxed_Fe_A"] == pytest.approx(1.2)
    assert not result["scientifically_accepted"]
    collided = pose.frac.copy()
    collided[-1] = collided[0]
    assert not post_relaxation_geometry(pose, replace(pose, frac=collided), {"final_graph": [], "final_graph_preserved": True}, rules)["diagnostic_DFT_geometry_ready"]
