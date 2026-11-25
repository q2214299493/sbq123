"""The new batch cannot inherit old scopes or expand its GPU/DFT authority."""
import copy

import pytest

from archive.fe110_11_15_gpu_20261029.adapter import MODEL_SHA, NAMES
from archive.fe110_pair2_20261027.runtime import check_scope


def fixture():
    request = {"document_kind": "fe110_c2_11_15_ft512_relaxation", "scope": {
        "models": {"finetune": {"sha256": MODEL_SHA}}, "cases": [{"name": n} for n in NAMES],
        "limits": {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2},
        "max_wall_seconds": 600, "CPU_count": 4, "memory_GB": 32, "allocator_limit_MiB": 16384,
        "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da"},
        "boundaries": {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False},
        "execution_mode": "direct_no_scheduler", "scheduler_job_id": None}
    auth = {"action": "RUN_PAIRED_ML_RELAXATION", "request_sha256": "a" * 64, "user_authorized": True, "user_request": "test only"}
    return request, auth, {"scope": copy.deepcopy(request["scope"]), "authorizing_user_request": "test only"}


def test_exact_single_checkpoint_fifteen_case_scope():
    check_scope(*fixture(), "a" * 64)


@pytest.mark.parametrize("change", ["model", "case", "budget", "GPU", "sharing", "VASP", "auth"])
def test_scope_expansion_rejected_even_with_matching_policy(change):
    request, auth, policy = fixture()
    if change == "model":
        request["scope"]["models"]["finetune"]["sha256"] = "b" * 64
    elif change == "case":
        request["scope"]["cases"].pop()
    elif change == "budget":
        request["scope"]["max_wall_seconds"] += 1
    elif change == "GPU":
        request["scope"]["gpu_index"] = 0
    elif change == "sharing":
        request["scope"]["gpu_sharing"] = {}
    elif change == "VASP":
        request["boundaries"]["VASP"] = True
    else:
        auth["user_authorized"] = False
    policy["scope"] = copy.deepcopy(request["scope"])
    with pytest.raises(ValueError):
        check_scope(request, auth, policy, "a" * 64)
