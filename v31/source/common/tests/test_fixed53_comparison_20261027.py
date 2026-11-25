import copy

import pytest

from scripts.adsorption.fixed_force_comparison import validate_scope
from archive.fe110_fixed53_comparison_20261027 import transport


def scope():
    request = {"remote_root": "/home/sbq/sbq/test", "gpu_index": 0, "gpu_uuid": "GPU-test", "gpu_sharing": {"test": True},
        "max_wall_seconds": 600, "sample_ids": [f"heldout_{i}" for i in range(53)],
        "model_checkpoint_sha256": {"baseline": "a" * 64, "control": "b" * 64, "new512": "c" * 64},
        "models": {k: {"sha256": s * 64} for k, s in [("baseline", "a"), ("control", "b"), ("new512", "c")]},
        "execution_mode": "direct_no_scheduler", "scheduler_job_id": None, "prediction_count": 159,
        "scientific_boundaries": {"training": False, "relaxation": False, "model_reselection": False, "model_promotion": False}}
    policy = copy.deepcopy(request)
    policy["authorizing_user_request"] = "fixed comparison"
    approval = {"user_authorized": True, "request_sha256": "d" * 64, "action": "RUN_FROZEN_FORCE_COMPARISON", "user_request": "fixed comparison"}
    return request, approval, policy


def test_exact_three_frozen_models_and_reserved_set_allowed():
    request, approval, policy = scope()
    validate_scope(request, approval, policy, "d" * 64)


@pytest.mark.parametrize("damage", ["authorization", "checkpoint", "count", "sample_ids", "training", "reselection", "scheduler"])
def test_scope_expansion_or_checkpoint_change_rejected(damage):
    request, approval, policy = scope()
    if damage == "authorization":
        approval["request_sha256"] = "e" * 64
    elif damage == "checkpoint":
        request["models"]["new512"]["sha256"] = "e" * 64
    elif damage == "count":
        request["prediction_count"] = 160
    elif damage == "sample_ids":
        request["sample_ids"][0] = "development_frame"
    elif damage in ["training", "reselection"]:
        request["scientific_boundaries"]["training" if damage == "training" else "model_reselection"] = True
    else:
        request["scheduler_job_id"] = "fake123"
    with pytest.raises(ValueError):
        validate_scope(request, approval, policy, "d" * 64)


def test_native_launcher_binds_all_writable_cache_locations(monkeypatch, tmp_path):
    monkeypatch.setattr(transport, "verify", lambda _: None)
    commands = []
    monkeypatch.setattr(transport, "call", lambda command, *args, **kwargs: commands.append(command) or b"PASS")
    transport.module("preflight")
    assert "MPLCONFIGDIR=" + transport.REMOTE + "/cache/matplotlib" in commands[0]
    assert "TORCH_EXTENSIONS_DIR=" + transport.REMOTE + "/cache/torch_extensions" in commands[0]
