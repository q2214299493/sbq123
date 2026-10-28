"""New checkpoint comparison cannot reuse old budget or expand into DFT."""
import copy
import json
import subprocess

import pytest

from archive.fe110_pair2_20261027.runtime import check_scope
from archive.fe110_scratch512_20261028.relaxation_adapter import KIND, MODEL_SHA, PYTHONS, SEED_SHA


def scope_fixture():
    request = {"document_kind": KIND, "scope": {"models": {name: {"sha256": digest,
        "backend": "nequip" if name == "nequip" else "aqcat25"} for name, digest in MODEL_SHA.items()},
        "cases": [{"name": name, "seed_sha256": digest} for name, digest in SEED_SHA.items()],
        "limits": {"seed_max_steps": 80, "fmax_eV_per_A": .1, "LBFGS_maxstep_A": .2},
        "max_wall_seconds": 600, "CPU_count": 4, "memory_GB": 32, "allocator_limit_MiB": 16384,
        "model_pythons": copy.deepcopy(PYTHONS),
        "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da"},
        "boundaries": {"training": False, "model_reselection": False, "model_promotion": False, "VASP": False},
        "execution_mode": "direct_no_scheduler", "scheduler_job_id": None}
    auth = {"action": "RUN_PAIRED_ML_RELAXATION", "user_authorized": True, "request_sha256": "a"*64, "user_request": "fixture only"}
    exception = {"scope": copy.deepcopy(request["scope"]), "authorizing_user_request": "fixture only"}
    return request, auth, exception


def test_exact_two_model_two_origin_scope():
    request, auth, exception = scope_fixture()
    check_scope(request, auth, exception, "a"*64)


@pytest.mark.parametrize("change", ["checkpoint", "seed", "GPU", "sharing", "memory", "steps", "VASP", "budget", "authorization", "environment"])
def test_old_approval_or_expanded_scope_rejected_even_when_policy_matches(change):
    request, auth, exception = scope_fixture()
    scope = request["scope"]
    if change == "checkpoint":
        scope["models"]["finetune"]["sha256"] = "b"*64
    elif change == "seed":
        scope["cases"][1]["seed_sha256"] = "b"*64
    elif change == "GPU":
        scope["gpu_index"] = 0
    elif change == "sharing":
        scope["gpu_sharing"] = {"mode": "resident_service_allowlist"}
    elif change == "memory":
        scope["allocator_limit_MiB"] = 20000
    elif change == "steps":
        scope["limits"]["seed_max_steps"] = 81
    elif change == "VASP":
        request["boundaries"]["VASP"] = True
    elif change == "budget":
        scope["max_wall_seconds"] = 601
    elif change == "environment":
        scope["model_pythons"]["finetune"] = scope["model_pythons"]["nequip"]
    else:
        auth["user_authorized"] = False
    exception["scope"] = copy.deepcopy(scope)
    with pytest.raises(ValueError):
        check_scope(request, auth, exception, "a"*64)


@pytest.mark.parametrize("failed_first_model", [False, True])
def test_sequence_preserves_per_model_interpreter_and_does_not_retry(tmp_path, monkeypatch, failed_first_model):
    from archive.fe110_pair2_20261027 import runtime
    from archive.fe110_scratch512_20261028.relaxation_adapter import sequence
    request, _, _ = scope_fixture()
    path = tmp_path / "request.json"
    path.write_text("{}", encoding="utf-8")
    (tmp_path / "output").mkdir()
    monkeypatch.setattr(runtime, "verify", lambda path, remote: (request, tmp_path, request["scope"]))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert 0 < kwargs["timeout"] <= 600
        return subprocess.CompletedProcess(command, 1 if failed_first_model else 0)

    monkeypatch.setattr(subprocess, "run", run)
    if failed_first_model:
        with pytest.raises(RuntimeError, match="no retry"):
            sequence(path)
        assert len(calls) == 1
    else:
        sequence(path)
        assert [command[0] for command in calls] == list(PYTHONS.values())
        assert [command[-1] for command in calls] == list(MODEL_SHA)
    receipt = json.loads((tmp_path / "output/producer_exit_record.json").read_bytes())
    assert receipt["exit_code"] == (1 if failed_first_model else 0)
    assert receipt["training_performed"] is False and receipt["VASP_submitted"] is False
