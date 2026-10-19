import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.artifact_io import sha256_file
from scripts.adsorption import direct_force_training as runtime
from scripts.adsorption.direct_training_arm import install_cuda_guard


@pytest.fixture
def bound_request(tmp_path):
    policy = {"backends": {"aqcat_gpu": {"direct_execution_exceptions": {"test": {
        "remote_root": "/home/sbq/sbq/frozen", "gpu_index": 1, "gpu_uuid": "GPU-test", "max_wall_seconds": 3600,
        "per_arm_wall_seconds": 1800, "original_comparison_sha256": "", "arm_request_sha256": {}, "authorizing_user_request": "跑"}}}}}
    exception = policy["backends"]["aqcat_gpu"]["direct_execution_exceptions"]["test"]
    (tmp_path / "comparison_request.json").write_text("{}")
    exception["original_comparison_sha256"] = sha256_file(tmp_path / "comparison_request.json")
    for arm in ("control", "treatment"):
        (tmp_path / arm).mkdir()
        (tmp_path / arm / "training_request.json").write_text("{}")
        exception["arm_request_sha256"][arm] = sha256_file(tmp_path / arm / "training_request.json")
    (tmp_path / "policy.yml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    document = {"run_id": "direct-test", "remote_root": exception["remote_root"], "gpu_index": 1,
        "gpu_uuid": "GPU-test", "max_wall_seconds": 3600, "per_arm_wall_seconds": 1800,
        "execution_mode": "direct_no_scheduler", "scheduler_job_id": None, "arms": ["control", "treatment"],
        "original_comparison_sha256": exception["original_comparison_sha256"], "exception_id": "test",
        "policy": {"path": "policy.yml", "sha256": sha256_file(tmp_path / "policy.yml")}, "artifacts": []}
    path = tmp_path / "direct_request.json"
    path.write_text(json.dumps(document))
    approval = {"request_sha256": sha256_file(path), "user_authorized": True,
                "action": "RUN_GPU_ADSORPTION_TRAINING_COMPARISON_DIRECT", "user_request": "跑"}
    (tmp_path / "direct_authorization.json").write_text(json.dumps(approval), encoding="utf-8")
    return path, document, approval


def test_local_binding_and_no_scheduler(bound_request):
    path, _, _ = bound_request
    value, _, _ = runtime.verify(path, sha256_file(path))
    assert value["scheduler_job_id"] is None


@pytest.mark.parametrize("key,value", [("gpu_index", 2), ("max_wall_seconds", 3601),
    ("per_arm_wall_seconds", 1801), ("run_id", "2190"), ("scheduler_job_id", "2190"), ("arms", ["treatment", "control"])])
def test_reject_execution_scope_changes(bound_request, key, value):
    path, document, approval = bound_request
    document[key] = value
    path.write_text(json.dumps(document))
    approval["request_sha256"] = sha256_file(path)
    (path.parent / "direct_authorization.json").write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(ValueError):
        runtime.verify(path, sha256_file(path))


def test_reject_stale_authority_and_frozen_arm_tamper(bound_request):
    path, _, _ = bound_request
    (path.parent / "control/training_request.json").write_text("changed")
    with pytest.raises(ValueError, match="frozen arm"):
        runtime.verify(path, sha256_file(path))
    with pytest.raises(ValueError, match="direct request"):
        runtime.verify(path, "0"*64)


def test_escape_and_runtime_directories(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        runtime.inside(tmp_path, "../elsewhere")
    env = {key: str(tmp_path / key) for key in ("TMPDIR", "XDG_CACHE_HOME", "TORCH_HOME", "HF_HOME", "MPLCONFIGDIR", "TORCH_EXTENSIONS_DIR")}
    runtime.make_runtime_directories(tmp_path, env)
    assert all(Path(value).is_dir() for value in env.values())
    env["TMPDIR"] = str(tmp_path.parent / "outside")
    with pytest.raises(ValueError, match="escapes"):
        runtime.make_runtime_directories(tmp_path, env)


def test_no_signals_to_unowned_process_group(monkeypatch):
    child = SimpleNamespace(pid=123, poll=lambda: None)
    monkeypatch.setattr(runtime.os, "getpgid", lambda _: 999, raising=False)
    calls = []
    monkeypatch.setattr(runtime.os, "killpg", lambda *args: calls.append(args), raising=False)
    with pytest.raises(RuntimeError, match="unowned"):
        runtime.stop_owned_group(child)
    assert not calls


def test_timeout_and_memory_budget_do_not_touch_other_processes(monkeypatch):
    child = SimpleNamespace(pid=123, poll=lambda: None)
    with pytest.raises(TimeoutError):
        runtime.wait_bounded(child, -1, 32)
    monkeypatch.setattr(runtime, "tree_rss", lambda _: 33*1024**3)
    with pytest.raises(MemoryError):
        runtime.wait_bounded(child, 30, 32)


def test_producer_environment_strips_scheduler_and_pins_exact_gpu(tmp_path, monkeypatch):
    monkeypatch.setenv("SLURM_JOB_ID", "do-not-emulate")
    env = runtime.arm_environment(tmp_path, {"gpu_uuid": "GPU-test"}, "control")
    assert not any(key.startswith("SLURM_") for key in env)
    assert env["CUDA_VISIBLE_DEVICES"] == "GPU-test"
    assert env["PYTHONPATH"].startswith(str(tmp_path / "control/runtime") + ":")
    assert env["PYTHONUTF8"] == "1" and env["OMP_NUM_THREADS"] == "4"


@pytest.mark.parametrize("bad", [None, "cpu", "two_devices", "nonzero_step", "wrong_epoch", "wrong_steps"])
def test_actual_model_cuda_and_budget_guard(tmp_path, monkeypatch, bad):
    torch = pytest.importorskip("torch")
    class Device:
        type = "cpu" if bad == "cpu" else "cuda"
        index = 0
        def __str__(self): return "cuda:0"
    class Trainer:
        def train(self):
            self.step = 496
            return "native_called"
    fixture_module = SimpleNamespace(RoleForceTrainer=Trainer)
    monkeypatch.setitem(sys.modules, "scripts.adsorption.role_force_trainer", fixture_module)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 2 if bad == "two_devices" else 1)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-test")
    install_cuda_guard({"gpu_uuid": "GPU-test"}, tmp_path, {"max_epochs": 2, "max_optimizer_steps_per_arm": 496})
    instance = Trainer()
    instance.model = SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device=Device())]))
    instance.step = 1 if bad == "nonzero_step" else 0
    instance.config = {"optim": {"max_epochs": 3 if bad == "wrong_epoch" else 2}}
    instance.train_loader = range(249 if bad == "wrong_steps" else 248)
    if bad:
        with pytest.raises(RuntimeError):
            instance.train()
        assert not (tmp_path / "execution_device.json").exists()
    else:
        assert instance.train() == "native_called"
        assert json.loads((tmp_path / "execution_device.json").read_text())["model_device"] == "cuda:0"
        assert json.loads((tmp_path / "training_completed.json").read_text())["optimizer_steps"] == 496
