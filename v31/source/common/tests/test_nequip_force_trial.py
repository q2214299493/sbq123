"""Force-mask,lossless export and bounded native-request regressions."""
import copy
import io
from pathlib import PurePosixPath

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.constraints import FixAtoms
from ase.io import read
import yaml

from scripts.adsorption.force_training_preflight import check_budget
from scripts.adsorption.nequip_force_data import write_frame
from scripts.adsorption.nequip_force_job import child, execute, verify
from scripts.artifact_io import sha256_file, write_json_exclusive
from archive.fe110_scratch512_20261028.prepare import config
from archive.fe110_scratch512_20261028.sequence_driver import arm_command, verify as verify_sequence


def test_export_preserves_printed_precision_raw_fixed_forces_and_dev_weights():
    atoms = Atoms("FeCHO", positions=[[0.12345678901234567, 0., 0.], [1., 2., 3.], [2., 3., 4.], [3., 4., 5.]],
        cell=[[8.123456789012345, 0., 0.], [2.123456789012345, 9., 0.], [0., 0., 20.]], pbc=[True, True, False])
    forces = np.arange(12, dtype=float).reshape(4, 3) / 7
    atoms.calc = SinglePointCalculator(atoms, energy=-123., forces=forces)
    atoms.set_constraint(FixAtoms(indices=[0]))
    weights = np.array([0., .2, .3, .5])
    output = io.StringIO()
    write_frame(output, atoms, weights, {"sample_id": "fixture", "magnetic_review_level": "unchanged"})
    result = read(io.StringIO(output.getvalue()), format="extxyz")
    for a, b in [(atoms.positions, result.positions), (atoms.cell.array, result.cell.array),
                 (forces, result.get_forces(apply_constraint=False)), (weights, result.arrays["force_loss_weights"])]:
        assert np.array_equal(a, b)
    assert "energy" not in result.calc.results
    assert np.any(result.get_forces(apply_constraint=False)[0] != 0)


@pytest.mark.parametrize("weights", [[.1, .9], [0., .5], [0., -1.], [0., float("nan")]])
def test_bad_fixed_mask_or_weight_normalization_rejected(weights):
    atoms = Atoms("FeC", positions=[[0, 0, 0], [0, 0, 2]], cell=[10, 10, 20], pbc=True)
    atoms.set_constraint(FixAtoms(indices=[0]))
    atoms.calc = SinglePointCalculator(atoms, forces=np.zeros((2, 3)))
    with pytest.raises(ValueError):
        write_frame(io.StringIO(), atoms, weights, {})


def budget_fixture(epochs, contract=None):
    request = {"training_limits": {"epochs": epochs, "learning_rate": 1e-5, "seed": 42, "batch_size": 1,
        "GPU_count": 1, "CPU_count": 4, "memory_GB": 32, "walltime_minutes": 30, "unattended_retries": 0,
        "max_optimizer_steps": 512 * epochs}, "split_counts": {"train": 512, "development": 78, "heldout": 53},
        "artifacts": [{"path": "training_manifest.json", "sha256": "ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee"}]}
    if contract:
        request["preparation_contract"] = contract
    cfg = {"optim": {"eval_every": 512, "checkpoint_every": 512, "scheduler_params": {"epochs": epochs}}, "dataset": {"train": {}, "val": {}}}
    return request, cfg


def test_original_two_epoch_gate_preserved():
    request, cfg = budget_fixture(2)
    check_budget(request, cfg)
    request, cfg = budget_fixture(20)
    with pytest.raises(ValueError, match="budget"):
        check_budget(request, cfg)


def test_twenty_epochs_require_the_exact_frozen_data_contract():
    request, cfg = budget_fixture(20, "fe110_scratch512_comparison_v1")
    check_budget(request, cfg)
    request["artifacts"][0]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="manifest"):
        check_budget(request, cfg)


@pytest.mark.parametrize("change", ["frames", "epochs", "heldout_loader"])
def test_expanded_comparison_scope_rejected(change):
    request, cfg = budget_fixture(20, "fe110_scratch512_comparison_v1")
    if change == "frames":
        request["split_counts"]["train"] = 513
    elif change == "epochs":
        request["training_limits"]["epochs"] = 21
    else:
        cfg["dataset"]["test"] = {}
    with pytest.raises(ValueError):
        check_budget(request, cfg)


def request_fixture(tmp_path):
    cfg = config(tmp_path / "data", tmp_path / "output", {"avg_num_neighbors": 40., "movable_force_component_rms_eV_A": 1.})
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    request = {"document_kind": "fe110_nequip_force_scratch_trial", "source_manifest_sha256": "ebf30df5cb009ac24293ca2b59e384b9158e796d4ec53301bf537b224dcfe4ee",
        "counts": {"train": 512, "development": 78}, "initialization": "random_no_checkpoint", "config_path": "config.yaml",
        "max_wall_seconds": 1800, "GPU_count": 1, "automatic_retries": 0,
        "artifacts": [{"path": "config.yaml", "sha256": sha256_file(tmp_path / "config.yaml")}]}
    write_json_exclusive(tmp_path / "request.json", request)
    return tmp_path / "request.json"


def test_native_run_refuses_missing_or_false_authorization(tmp_path):
    path = request_fixture(tmp_path)
    verify(path, sha256_file(path))
    write_json_exclusive(tmp_path / "authorization.json", {"user_authorized": False})
    with pytest.raises(ValueError, match="authorization"):
        execute(path, sha256_file(path))


def test_mutated_config_or_escaping_artifact_rejected(tmp_path):
    path = request_fixture(tmp_path)
    (tmp_path / "config.yaml").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact"):
        verify(path, sha256_file(path))
    with pytest.raises(ValueError, match="escapes"):
        child(tmp_path, "../escape")


def test_scratch_configuration_has_no_energy_target_or_test_loader(tmp_path):
    cfg = config(tmp_path, tmp_path / "run", {"avg_num_neighbors": 40., "movable_force_component_rms_eV_A": 1.})
    assert cfg["run"] == ["train"]
    assert "test_dataset" not in cfg["data"]
    assert cfg["training_module"]["model"]["_target_"] == "nequip.model.NequIPGNNModel"
    assert all(x == 0 for x in cfg["training_module"]["model"]["per_type_energy_shifts"].values())


def test_linux_paths_remain_posix_when_prepared_on_windows():
    root = PurePosixPath("/home/sbq/sbq/trial/nequip")
    cfg = config(root / "data", root / "output", {"avg_num_neighbors": 40., "movable_force_component_rms_eV_A": 1.})
    assert cfg["data"]["train_dataset"]["file_path"] == "/home/sbq/sbq/trial/nequip/data/train.xyz"
    assert cfg["trainer"]["default_root_dir"] == "/home/sbq/sbq/trial/nequip/output"


def test_native_masked_gradient_matches_existing_grouped_objective():
    torch = pytest.importorskip("torch")
    pytest.importorskip("nequip")
    from scripts.adsorption.nequip_force_runtime import MovableForceVectorMAE
    from scripts.adsorption.force_role_runtime import grouped_force_loss
    from nequip.data import AtomicDataDict
    prediction = torch.tensor([[999., 0., 0.], [3., 4., 0.], [100., 0., 0.], [0., 0., 2.], [0., 0., 4.]], requires_grad=True)
    reference = torch.zeros_like(prediction)
    weights = torch.tensor([0., 1., 0., .25, .75])
    target = {"forces": reference, "force_loss_weights": weights[:, None], "batch": torch.tensor([0, 0, 1, 1, 1]), AtomicDataDict.NUM_NODES_KEY: torch.tensor([2, 3])}
    metric = MovableForceVectorMAE()
    result = metric({"forces": prediction}, target)
    expected = grouped_force_loss(prediction, reference, weights, (weights == 0).long(), torch.tensor([2, 3]))
    assert torch.allclose(result, expected) and result.item() == pytest.approx(4.25)
    result.backward()
    assert torch.all(prediction.grad[[0, 2]] == 0)
    assert torch.isfinite(prediction.grad).all()
    broken = copy.deepcopy(target)
    broken["force_loss_weights"] = weights[:, None] * 2
    with pytest.raises(ValueError, match="normalized"):
        MovableForceVectorMAE()({"forces": prediction}, broken)


def sequence_fixture(tmp_path, authorized=True, change=None):
    request = {"per_arm_seconds": 1800, "total_GPU_seconds": 3600, "arms": ["nequip_scratch", "aqcat25_finetune"], "artifacts": []}
    if change == "per_arm_seconds":
        request[change] += 1
    elif change == "total_GPU_seconds":
        request[change] += 1
    elif change == "order":
        request["arms"].reverse()
    path = tmp_path / "sequence.json"
    write_json_exclusive(path, request)
    write_json_exclusive(tmp_path / "sequence_authorization.json", {"user_authorized": authorized,
        "action": "RUN_FE110_SCRATCH512_TWO_ARM_SEQUENCE", "request_sha256": sha256_file(path)})
    return path


@pytest.mark.parametrize("value", [False, "true", 1])
def test_sequence_requires_literal_current_human_authorization(tmp_path, value):
    path = sequence_fixture(tmp_path, authorized=value)
    with pytest.raises(ValueError, match="authorization"):
        verify_sequence(path, sha256_file(path))


@pytest.mark.parametrize("change", ["per_arm_seconds", "total_GPU_seconds", "order"])
def test_sequence_cannot_expand_budget_or_reverse_reviewed_order(tmp_path, change):
    path = sequence_fixture(tmp_path, change=change)
    with pytest.raises(ValueError, match="budget or scope"):
        verify_sequence(path, sha256_file(path))


def test_sequence_reuses_canonical_finetune_launch_and_bound_scratch_request():
    request = {"nequip_request_sha256": "a" * 64, "finetune_direct_request_sha256": "b" * 64}
    root = PurePosixPath("/home/sbq/sbq/trial")
    scratch = arm_command(root, request, "nequip_scratch", "run")
    finetune = arm_command(root, request, "aqcat25_finetune", "launch")
    assert scratch[2] == "scripts.adsorption.nequip_force_job" and scratch[-1] == "a" * 64
    assert finetune[2] == "scripts.adsorption.direct_force_training" and finetune[-1] == "b" * 64
    assert "launch" in finetune
