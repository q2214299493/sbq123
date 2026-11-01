import copy

import pytest
import numpy as np

from archive.fe110_c2_16_19_gpu_20261102 import adapter
from archive.fe110_c2_16_19_gpu_20261102.prepare import copy as checked_copy
from archive.fe110_pair2_20261027.runtime import check_scope
from archive.fe110_pair2_20261027.review import post_relaxation_geometry
from scripts.adsorption.build_fe110_adsorption import Poscar


def fixture():
    request = {"document_kind": "fe110_c2_16_19_ft512_relaxation", "scope": {
        "models": {"finetune": {"sha256": adapter.MODEL_SHA}}, "cases": [{"name": n} for n in adapter.NAMES],
        "limits": {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2},
        "max_wall_seconds": 600, "CPU_count": 4, "memory_GB": 32, "allocator_limit_MiB": 16384,
        "gpu_index": 0, "gpu_uuid": "GPU-483c224e-cc19-13e2-24ad-c83efd14fa75",
        "gpu_sharing": {"mode": "resident_service_allowlist", "max_training_memory_MiB": 16384}},
        "boundaries": {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False},
        "execution_mode": "direct_no_scheduler", "scheduler_job_id": None,
        "domain": {"status": "out_of_calibrated_domain", "adsorbate_atoms": [7, 8],
                   "use": "candidate_pre_relaxation_only", "ranking_allowed": False}}
    auth = {"action": "RUN_PAIRED_ML_RELAXATION", "request_sha256": "a" * 64, "user_authorized": True, "user_request": "test only"}
    policy = {"scope": copy.deepcopy(request["scope"]), "authorizing_user_request": "test only"}
    return request, auth, policy


def test_exact_twelve_case_shared_gpu_scope():
    check_scope(*fixture(), "a" * 64)


@pytest.mark.parametrize("change", ["model", "case", "budget", "GPU", "allocator", "sharing", "VASP", "ranking", "auth", "scheduler"])
def test_expansion_is_rejected(change):
    request, auth, policy = fixture()
    if change == "model":
        request["scope"]["models"]["finetune"]["sha256"] = "b" * 64
    elif change == "case":
        request["scope"]["cases"].pop()
    elif change == "budget":
        request["scope"]["max_wall_seconds"] += 1
    elif change == "GPU":
        request["scope"]["gpu_index"] = 1
    elif change == "allocator":
        request["scope"]["allocator_limit_MiB"] += 1
    elif change == "sharing":
        del request["scope"]["gpu_sharing"]
    elif change == "VASP":
        request["boundaries"]["VASP"] = True
    elif change == "ranking":
        request["domain"]["ranking_allowed"] = True
    elif change == "auth":
        auth["user_authorized"] = False
    else:
        request["scheduler_job_id"] = "invented"
    policy["scope"] = copy.deepcopy(request["scope"])
    with pytest.raises(ValueError):
        check_scope(request, auth, policy, "a" * 64)


def test_partial_copy_never_overwrites_different_bytes(tmp_path):
    first, second = tmp_path / "source", tmp_path / "target"
    first.write_bytes(b"first")
    checked_copy(first, second)
    checked_copy(first, second)
    first.write_bytes(b"changed")
    with pytest.raises(ValueError, match="preserve differing"):
        checked_copy(first, second)
    assert second.read_bytes() == b"first"


def test_fragment_caption_does_not_misname_a_non_c3_target():
    cell = np.diag([100., 100., 20.])
    cart = np.array([[2 * i, 0, 5] for i in range(45)] + [[1, 0, 6.2]])
    pose = Poscar("synthetic_caption_fixture_not_physical_surface", cell, ["Fe", "C"], [45, 1],
                  cart @ np.linalg.inv(cell), [("F",) * 3] * 18 + [("T",) * 3] * 28)
    rules = {"contact_validation": {"hard_contact_distance_angstrom": .8},
             "surface_reconstruction": {"maximum_slab_displacement_angstrom": .5}}
    result = post_relaxation_geometry(pose, pose, {"final_graph": [], "final_graph_preserved": False}, rules)
    assert "C3" not in result["interpretation"]
    assert "not an intact-target success" in result["interpretation"]
