import copy

import pytest

from archive.fe110_training536_execution_20261113.entry import gpu_snapshot, validate_contract
from archive.fe110_training536_execution_20261113.closeout import checkpoint_directories


def fixture():
    contract = {"user_instruction": "exact user instruction", "training_request_sha256": "bound",
                "scheduler_seconds": 1740, "scheduler_killwait_seconds": 30,
                "watchdog_seconds": 1700, "watchdog_kill_after_seconds": 10}
    request = {"split_counts": {"train": 536, "development": 78, "heldout": 53},
               "training_limits": {"epochs": 2, "learning_rate": 1e-5, "seed": 42, "batch_size": 1,
                                   "GPU_count": 1, "CPU_count": 4, "memory_GB": 32,
                                   "walltime_minutes": 30, "max_optimizer_steps": 1072, "unattended_retries": 0}}
    config = {"dataset": {"train": {}, "val": {}}, "optim": {"lr_initial": 1e-5, "max_epochs": 2, "batch_size": 1},
              "loss_functions": [{"energy": {"coefficient": 0}}, {"forces": {"coefficient": 1}}]}
    authorization = {"user_request": "exact user instruction", "user_authorized": True,
                     "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE", "request_sha256": "bound"}
    return contract, request, config, authorization


def test_exact_scope_accepts_without_gpu_or_model():
    validate_contract(*fixture())


def test_metadata_files_are_not_scheduler_checkpoint_directories(tmp_path):
    expected = tmp_path / "checkpoint_20261113T160516Z"
    expected.mkdir()
    (tmp_path / "checkpoint_metadata_inspection.stderr").write_text("")
    assert checkpoint_directories(tmp_path) == [expected]


@pytest.mark.parametrize("kind", ["old512", "twenty_epochs", "two_GPUs", "heldout_loader", "energy_loss", "unbound_authorization", "walltime"])
def test_scope_changes_fail_before_cuda(kind):
    contract, request, config, auth = copy.deepcopy(fixture())
    if kind == "old512":
        request["training_limits"]["max_optimizer_steps"] = 1024
    elif kind == "twenty_epochs":
        request["training_limits"]["epochs"] = 20
    elif kind == "two_GPUs":
        request["training_limits"]["GPU_count"] = 2
    elif kind == "heldout_loader":
        config["dataset"]["test"] = {}
    elif kind == "energy_loss":
        config["loss_functions"][0]["energy"]["coefficient"] = 1
    elif kind == "unbound_authorization":
        auth["request_sha256"] = "changed"
    else:
        contract["scheduler_seconds"] = 1800
    with pytest.raises(ValueError):
        validate_contract(contract, request, config, auth)


def test_single_visible_card_is_bound_by_uuid_after_namespace_remap(monkeypatch):
    calls = []

    def output(args, **kwargs):
        calls.append(args)
        return "0, GPU-allocated, RTX4090, 24564, 24100, 0\n" if "--query-gpu=index,uuid,name,memory.total,memory.free,utilization.gpu" in args else ""

    monkeypatch.setattr("archive.fe110_training536_execution_20261113.entry.subprocess.check_output", output)
    result = gpu_snapshot("3")
    assert result["uuid"] == "GPU-allocated"
    assert result["index"] == 0
    assert result["Slurm_global_assignment"] == "3"
    assert "-i" not in calls[0]
    assert calls[1][calls[1].index("-i") + 1] == "GPU-allocated"


def test_multicard_visibility_without_assigned_card_fails(monkeypatch):
    monkeypatch.setattr("archive.fe110_training536_execution_20261113.entry.subprocess.check_output",
                        lambda args, **kwargs: "0, GPU-A, RTX4090, 24564, 24100, 0\n1, GPU-B, RTX4090, 24564, 24100, 0\n")
    with pytest.raises(RuntimeError, match="exactly one"):
        gpu_snapshot("3")


def test_existing_compute_process_blocks_training(monkeypatch):
    monkeypatch.setattr("archive.fe110_training536_execution_20261113.entry.subprocess.check_output",
                        lambda args, **kwargs: "3, GPU-allocated, RTX4090, 24564, 24100, 0\n" if "--query-gpu=index,uuid,name,memory.total,memory.free,utilization.gpu" in args else "123, GPU-allocated")
    with pytest.raises(RuntimeError, match="occupied"):
        gpu_snapshot("3")


@pytest.mark.parametrize("assignment", ["", "0,1", "0-3"])
def test_ambiguous_or_multiple_gpu_assignment_is_rejected(assignment):
    with pytest.raises(ValueError, match="one explicit"):
        gpu_snapshot(assignment)
