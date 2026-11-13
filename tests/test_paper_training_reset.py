from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "archive/chco_paper_aqcat25_20261112/train_latest_label.py"
spec = importlib.util.spec_from_file_location("paper_training_runner", SOURCE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def request():
    label = {"normal_completion": True, "electronically_converged": True, "eligible_for_force_only_training": True,
             "structure": {"sha256": "a" * 64}, "fixed_atom_indices_zero_based": [0],
             "forces_eV_per_A": [[99.0, 0.0, 0.0], [0.2, 0.0, 0.0]], "dft_toten_eV_force_label_only": -10.0}
    raw = json.dumps(label, indent=3).encode()
    return {"document_kind": "paper_sequential_training_request", "protocol_sha256": "f" * 64,
            "checkpoint_selection": "final_epoch_only",
            **{key: True for key in ("reset_model_weights", "reset_optimizer_state", "reset_scheduler_state", "reset_amp_state", "reset_ema_state")},
            "training": {"epochs": 100, "initial_learning_rate": 1e-4, "scheduler": "cosine", "target": "forces_only",
                         "energy_loss_coefficient": 0.0, "train_on_all": False, "train_finetuned": False,
                         "replay": False, "validation_epoch_selection": False},
            "training_samples": [{"artifact_sha256": hashlib.sha256(raw).hexdigest(), "raw_label_base64": base64.b64encode(raw).decode(),
                                  "label": label, "raw_forces_eV_per_A": label["forces_eV_per_A"]}],
            "restrictions": {key: False for key in ("submission_allowed", "automatic_submission", "scientifically_validated_ts",
                                                    "reportable_barrier", "production_checkpoint_promotion")},
            "movable_atom_indices_zero_based": [1]}


def test_raw_label_and_all_atom_forces_preserved():
    label, forces, movable = runner.validated_label(request())
    assert forces[0] == [99.0, 0.0, 0.0] and forces == label["forces_eV_per_A"]
    assert movable == [1]


@pytest.mark.parametrize("change", ["raw_bytes", "force_copy", "second_label", "replay", "resume", "nonfinite"])
def test_invalid_training_request_rejected(change):
    value = request()
    if change == "raw_bytes":
        value["training_samples"][0]["raw_label_base64"] = base64.b64encode(b"{}").decode()
    elif change == "force_copy":
        value["training_samples"][0]["raw_forces_eV_per_A"] = [[0.0] * 3] * 2
    elif change == "second_label":
        value["training_samples"] *= 2
    elif change == "replay":
        value["training"]["replay"] = True
    elif change == "resume":
        value["reset_optimizer_state"] = False
    else:
        sample = value["training_samples"][0]
        sample["label"]["forces_eV_per_A"][0][0] = float("nan")
        raw = json.dumps(sample["label"]).encode()
        sample.update(raw_label_base64=base64.b64encode(raw).decode(), artifact_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):
        runner.validated_label(value)


def fresh_trainer(*, resumed=None):
    scheduler_state = {"last_epoch": 0, "lr": [1e-5]}
    trainer = SimpleNamespace(epoch=0, step=0, optimizer=SimpleNamespace(state={}),
                              scheduler=SimpleNamespace(scheduler=SimpleNamespace(state_dict=lambda: copy.deepcopy(scheduler_state))),
                              model=SimpleNamespace(parameters=lambda: ["loaded_weight"]), ema_decay=0.999,
                              cpu=False, ema="old_ema", scaler="old_scaler")

    def load_checkpoint(**kwargs):
        assert kwargs == {"checkpoint_path": "/frozen/FT512.pt", "inference_only": True}
        if resumed == "step":
            trainer.step = 512
        elif resumed == "optimizer":
            trainer.optimizer.state["moment"] = 1
        elif resumed == "scheduler":
            scheduler_state["last_epoch"] = 512

    trainer.load_checkpoint = load_checkpoint
    return trainer


def test_frozen_weights_reset_training_state_and_rebuild_ema_amp():
    trainer = fresh_trainer()
    runner.reset_from_base(trainer, "/frozen/FT512.pt", amp=True,
                           ema_factory=lambda params, decay: (list(params), decay), scaler_factory=lambda device: ("fresh", device))
    assert trainer.ema == (["loaded_weight"], 0.999)
    assert trainer.scaler == ("fresh", "cuda")
    assert trainer.epoch == trainer.step == 0 and trainer.optimizer.state == {}


@pytest.mark.parametrize("resumed", ["step", "optimizer", "scheduler"])
def test_any_restored_training_state_is_rejected(resumed):
    with pytest.raises(ValueError):
        runner.reset_from_base(fresh_trainer(resumed=resumed), "/frozen/FT512.pt", amp=True,
                               ema_factory=lambda *args: args, scaler_factory=lambda value: value)


def test_exit_success_and_epoch_fields_do_not_replace_observed_updates():
    trainer = SimpleNamespace(train_dataset=[1], train_loader=[1], val_loader=None, test_loader=None, epoch=100, step=100)
    saved = {"epoch": 100, "step": 100, "state_dict": {}, "config": {"optim": {"max_epochs": 100}}}
    with pytest.raises(ValueError, match="actual optimizer updates"):
        runner.completed_training(trainer, [], saved)
    updates = [{"step": i, "epoch": float(i)} for i in range(1, 101)]
    assert runner.completed_training(trainer, updates, saved)["observed_optimizer_updates"] == 100
    saved["epoch"] = 99
    with pytest.raises(ValueError, match="final checkpoint"):
        runner.completed_training(trainer, updates, saved)


def test_file_binding_uses_original_bytes(tmp_path):
    path = tmp_path / "owner.json"
    path.write_bytes(b'{"value": 400.0}\n')
    digest = runner.sha256_file(path)
    assert runner.bound_file(path, digest) == b'{"value": 400.0}\n'
    path.write_bytes(b'{"value":400}\n')
    with pytest.raises(ValueError, match="hash mismatch"):
        runner.bound_file(path, digest)


def test_isolated_config_retains_normalization_and_excludes_validation_without_mutating_template():
    template = {"trainer": "equiformerv2_forces", "checkpoint": "/old.pt",
                "optim": {"lr_initial": 1e-4, "batch_size": 1, "scheduler": "LambdaLR", "max_epochs": 2,
                          "optimizer": "AdamW", "scheduler_params": {"lambda_type": "cosine", "epochs": 2,
                                                                    "warmup_epochs": 1, "lr_min_factor": 0.01}},
                "loss_functions": [{"energy": {"coefficient": 0.0}}, {"forces": {"coefficient": 1, "fn": "l2mae"}}],
                "outputs": {"forces": {"train_on_free_atoms": True}},
                "dataset": {"train": {"format": "lmdb", "src": "/old.db",
                                      "a2g_args": {"r_energy": False, "r_forces": True},
                                      "transforms": {"normalizer": {"forces": {"stdev": 2.887317180633545}}}},
                            "val": {"src": "/heldout.db"}}}
    before = copy.deepcopy(template)
    result = runner.isolated_config(template, Path("training.db"))
    assert template == before
    assert set(result["dataset"]) == {"train"} and result["checkpoint"] is None
    assert result["dataset"]["train"]["transforms"] == before["dataset"]["train"]["transforms"]
    assert result["optim"]["max_epochs"] == result["optim"]["scheduler_params"]["epochs"] == 100
    assert result["optim"]["load_best"] is False and result["optim"]["checkpoint_every"] == -1
    assert result["optim"]["scheduler_params"]["warmup_epochs"] == 1
    assert result["dataset"]["train"]["metadata_path"] == str((Path("training.db").parent / "metadata.npz").resolve())


def test_single_label_metadata_is_integer_exact_length_and_never_overwrites(tmp_path):
    import numpy as np

    path = tmp_path / 'metadata.npz'
    result = runner.write_single_label_metadata(path, 49)
    with np.load(path, allow_pickle=False) as data:
        assert data.files == ['natoms'] and data['natoms'].tolist() == [49]
        assert data['natoms'].shape == (1,) and np.issubdtype(data['natoms'].dtype, np.integer)
    assert result['sha256'] == runner.sha256_file(path) and result['sample_count'] == 1
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        runner.write_single_label_metadata(path, 49)
    assert path.read_bytes() == before


@pytest.mark.parametrize('count', [0, -1, 49.0, True])
def test_invalid_atom_count_cannot_create_metadata(tmp_path, count):
    path = tmp_path / 'metadata.npz'
    with pytest.raises(ValueError, match='positive integer'):
        runner.write_single_label_metadata(path, count)
    assert not path.exists()


@pytest.mark.parametrize("escape", [False, True])
def test_output_alias_uses_canonical_boundary_and_rejects_child_escape(tmp_path, monkeypatch, escape):
    declared = tmp_path / "declared_alias"
    canonical = tmp_path / "physical_disk" / "sbq"
    output = declared / "round_001"
    actual = tmp_path / "outside" if escape else canonical / "round_001"
    original_resolve = Path.resolve

    def resolve(path, strict=False):
        if path == declared:
            assert strict is True
            return canonical
        if path == output:
            return actual
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(runner, "WRITE_ROOT", declared)
    monkeypatch.setattr(Path, "resolve", resolve)
    if escape:
        with pytest.raises(ValueError, match="canonical GPU write boundary"):
            runner.validate_output_root(output)
    else:
        runner.validate_output_root(output)
    with pytest.raises(ValueError, match="output declaration"):
        runner.validate_output_root(canonical / "round_001")


@pytest.mark.parametrize("available,count", [(False, 0), (True, 0), (True, 2)])
def test_no_cuda_or_multiple_visible_devices_are_rejected(available, count):
    runtime = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: available, device_count=lambda: count))
    with pytest.raises(ValueError):
        runner.require_single_cuda(runtime)


def test_single_cuda_record_and_cpu_parameter_fallback_detection():
    runtime = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1,
                                                 get_device_name=lambda index: "selected GPU" if index == 0 else "wrong"))
    assert runner.require_single_cuda(runtime) == {"visible_cuda_device_count": 1, "visible_cuda_device_name": "selected GPU"}

    class Device:
        def __init__(self, kind):
            self.type = kind

        def __str__(self):
            return self.type + ":0"

    parameters = [SimpleNamespace(device=Device("cuda"))]
    trainer = SimpleNamespace(cpu=False, model=SimpleNamespace(parameters=lambda: parameters))
    assert runner.require_cuda_model(trainer) == ["cuda:0"]
    parameters.append(SimpleNamespace(device=Device("cpu")))
    with pytest.raises(ValueError, match="every model parameter"):
        runner.require_cuda_model(trainer)
    trainer.cpu = True
    with pytest.raises(ValueError, match="trainer selected CPU"):
        runner.require_cuda_model(trainer)


def test_sigterm_handler_raises_a_recordable_timeout_without_sending_signal():
    with pytest.raises(TimeoutError, match="SIGTERM.*no automatic retry"):
        runner.handle_sigterm(runner.signal.SIGTERM, None)


def test_main_installs_timeout_handler_and_restores_it_on_failure(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", [str(SOURCE), "--request", "request.json", "--structure", "POSCAR",
                                     "--template", "config.yml", "--output-root", "/home/sbq/sbq/new-round",
                                     "--request-sha256", "a" * 64, "--template-sha256", "b" * 64,
                                     "--execute-authorized"])
    calls = []
    old_handler = object()

    def mocked_signal(signum, handler):
        calls.append((signum, handler))
        return old_handler

    monkeypatch.setattr(runner.signal, "signal", mocked_signal)
    monkeypatch.setattr(runner, "execute", lambda _args: runner.handle_sigterm(runner.signal.SIGTERM, None))
    with pytest.raises(TimeoutError):
        runner.main()
    assert calls == [(runner.signal.SIGTERM, runner.handle_sigterm), (runner.signal.SIGTERM, old_handler)]
