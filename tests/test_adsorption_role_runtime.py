import copy
import json

import numpy as np
import pytest
from ase import Atoms
from ase.db import connect

torch = pytest.importorskip("torch")

from scripts.adsorption.force_finetune import build_database_metadata, validate_database_metadata  # noqa: E402
from scripts.adsorption.force_finetune import build_database, digest, verify_request  # noqa: E402
from scripts.adsorption.force_role_data import DATA_KEYS, ROLE_NAMES, TRAINER, role_metadata, validate_role_contract  # noqa: E402
from scripts.adsorption.force_role_runtime import RoleBatchSampler, graph_role_losses, grouped_force_loss  # noqa: E402
from archive.fe110_training512_20261027 import fixtures as legacy_fixtures  # noqa: E402
from archive.fe110_adsorption_pool_rebuild_20261019.roles import atom_weights, role_groups  # noqa: E402
from ase.io import read  # noqa: E402

fixture_manifest = legacy_fixtures.fixture_manifest
fixture_request = legacy_fixtures.fixture_request


def tensors():
    prediction = torch.ones((7, 3), dtype=torch.float64, requires_grad=True)
    reference = torch.zeros_like(prediction)
    weights = torch.tensor([0., .75, .25, 0., .2, .3, .5], dtype=torch.float64)
    fixed = torch.tensor([1, 0, 0, 1, 0, 0, 0])
    natoms = torch.tensor([3, 4])
    return prediction, reference, weights, fixed, natoms


def test_loss_is_per_graph_not_atom_count_weighted():
    prediction, reference, weights, fixed, natoms = tensors()
    with torch.no_grad():
        prediction[:3] *= 2
        prediction[fixed != 0] = 100000
    values = graph_role_losses(prediction, reference, weights, fixed, natoms)
    np.testing.assert_allclose(values.detach(), [2*np.sqrt(3), np.sqrt(3)])
    loss = grouped_force_loss(prediction, reference, weights, fixed, natoms)
    assert loss.item() == pytest.approx(1.5*np.sqrt(3))
    loss.backward()
    assert torch.all(prediction.grad[fixed != 0] == 0)
    assert torch.isfinite(prediction.grad).all()
    assert prediction.grad[1, 0] / prediction.grad[2, 0] == pytest.approx(3.)


def test_loss_autograd_finite_difference_and_exact_zero():
    prediction, reference, weights, fixed, natoms = tensors()
    assert torch.autograd.gradcheck(lambda x: grouped_force_loss(x, reference, weights, fixed, natoms), (prediction,))
    loss = grouped_force_loss(prediction, prediction.detach(), weights, fixed, natoms)
    loss.backward()
    assert loss.item() == 0 and torch.all(prediction.grad == 0)


@pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16])
def test_amp_force_tensors_keep_metadata_and_loss_at_safe_precision(dtype):
    p, r, w, f, n = tensors()
    p = p.detach().to(dtype).requires_grad_()
    r = r.float()
    with torch.autocast("cpu", dtype=torch.bfloat16):
        loss = grouped_force_loss(p, r, w, f, n)
    assert loss.dtype == torch.float32
    assert loss.item() == pytest.approx(np.sqrt(3), rel=1e-6)
    loss.backward()
    assert torch.isfinite(p.grad).all()
    assert torch.all(p.grad[f != 0] == 0)


@pytest.mark.parametrize("problem,message", [("nan", "nonfinite"), ("fixed", "fixed mask"),
    ("normalization", "normalized"), ("counts", "counts"), ("negative", "fixed mask"), ("shape", "shape")])
def test_loss_rejects_invalid_metadata(problem, message):
    p, r, w, f, n = tensors()
    if problem == "nan":
        r[1, 0] = float("nan")
    elif problem == "fixed":
        w[0] = .1
    elif problem == "normalization":
        w[1] = .5
    elif problem == "counts":
        n = torch.tensor([3, 5])
    elif problem == "negative":
        w[1] = -.1
    else:
        w = w[:-1]
    with pytest.raises(ValueError, match=message):
        grouped_force_loss(p, r, w, f, n)


def test_sampler_reproducibility_epoch_resume_and_loader():
    probabilities = np.array([.4, .2, .1, .1, .1, .1])
    sampler = RoleBatchSampler(probabilities, batch_size=2, seed=42)
    expected = list(sampler)
    assert expected == list(RoleBatchSampler(probabilities, 2, 42))
    sampler.set_epoch_and_start_iteration(0, 1)
    assert len(sampler) == 3 and list(sampler) == expected[1:]
    sampler.set_epoch(1)
    assert list(sampler) != expected
    dataset = torch.arange(6)
    loader = torch.utils.data.DataLoader(dataset, batch_sampler=sampler)
    assert [x.tolist() for x in loader] == list(sampler)
    sampler.set_epoch_and_start_iteration(1, 3)
    assert list(sampler) == []


@pytest.mark.parametrize("p", [[0., 1.], [-.1, 1.1], [.2, .2], [float("nan"), 1.], [[1.]], []])
def test_sampler_invalid_probabilities(p):
    with pytest.raises(ValueError, match="probabilities"):
        RoleBatchSampler(p, 1, 42)


def test_sampler_distribution_is_used_not_uniform():
    sampler = RoleBatchSampler([.9, .05, .05], 1, 42)
    selected = []
    for epoch in range(1000):
        sampler.set_epoch(epoch)
        selected.extend(i for batch in sampler for i in batch)
    assert .85 < selected.count(0) / len(selected) < .95


def role_row():
    return {"symbols": ["Fe", "Fe", "C", "O", "H"], "fixed_atom_indices_0based": [0],
        "force_role_groups": {"adsorbate_C": [2], "adsorbate_O": [3], "adsorbate_H": [4], "near_Fe": [1], "other_Fe": []},
        "proposed_per_atom_loss_weights": [0., 2/6, 2/6, 1/6, 1/6],
        "proposed_source_stage_sampling_probability": 1., "stage": "replay"}


def test_role_metadata_invariance_and_validation_only_no_sampler():
    row = role_row()
    original = copy.deepcopy(row)
    data = role_metadata(row, "train")
    assert data["adsorption_force_roles"] == [0, 4, 1, 2, 3]
    assert data["adsorption_replay"] == 1
    assert row == original
    assert "adsorption_sampling_probability" not in role_metadata(row, "development")
    row["symbols"][2] = "O"
    with pytest.raises(ValueError, match="element"):
        role_metadata(row, "train")


@pytest.mark.parametrize("problem", ["overlap", "fixed", "weights", "missing"])
def test_bad_role_metadata_rejected(problem):
    row = role_row()
    if problem == "overlap":
        row["force_role_groups"]["near_Fe"].append(2)
    elif problem == "fixed":
        row["proposed_per_atom_loss_weights"][0] = .1
    elif problem == "weights":
        row["proposed_per_atom_loss_weights"][1] = .1
    else:
        row["force_role_groups"]["near_Fe"] = []
    with pytest.raises(ValueError):
        role_metadata(row, "train")


def test_sampling_npz_database_order_and_tamper(tmp_path):
    database = tmp_path / "train.db"
    db = connect(database)
    db.write(Atoms("H"), data={"adsorption_sampling_probability": .75})
    db.write(Atoms("CH"), data={"adsorption_sampling_probability": .25})
    metadata = tmp_path / "metadata.npz"
    build_database_metadata(database, metadata)
    with np.load(metadata, allow_pickle=False) as values:
        np.testing.assert_array_equal(values["adsorption_sampling_probability"], [.75, .25])
        arrays = dict(values)
    arrays["adsorption_sampling_probability"] = arrays["adsorption_sampling_probability"][::-1]
    bad = tmp_path / "bad_metadata.npz"
    np.savez(bad, **arrays)
    with pytest.raises(ValueError, match="sampling metadata"):
        validate_database_metadata(database, bad)


def role_config():
    return {"trainer": TRAINER, "optim": {"grouped_force_objective": True},
        "evaluation_metrics": {"primary_metric": "forces_role_vector_mae"},
        "dataset": {k: {"a2g_args": {"r_data_keys": list(DATA_KEYS)}} for k in ("train", "val")}}


def role_request():
    return {"runtime_contract_version": 3, "artifacts": [{"path": "runtime/scripts/adsorption/" + name + ".py"}
        for name in ("force_role_data", "force_role_runtime", "role_force_trainer")]}


def test_role_contract_requires_runtime_and_data_consumption():
    config = role_config()
    validate_role_contract(role_request(), config)
    with pytest.raises(ValueError, match="contract v3"):
        validate_role_contract({"runtime_contract_version": 2}, config)
    config["trainer"] = "equiformerv2_forces"
    with pytest.raises(ValueError, match="RoleForceTrainer"):
        validate_role_contract(role_request(), config)


@pytest.mark.parametrize("problem,message", [("enable", "not enabled"), ("keys", "graph conversion"),
    ("metric", "selection metric"), ("sources", "hash bound")])
def test_role_contract_rejects_unused_fields(problem, message):
    config, request = role_config(), role_request()
    if problem == "enable":
        config["optim"]["grouped_force_objective"] = False
    elif problem == "keys":
        config["dataset"]["val"]["a2g_args"]["r_data_keys"] = []
    elif problem == "metric":
        config["evaluation_metrics"]["primary_metric"] = "forces_mae"
    else:
        request["artifacts"] = []
    with pytest.raises(ValueError, match=message):
        validate_role_contract(request, config)


def test_all_roles_have_stable_metric_names():
    assert set(ROLE_NAMES) == set(role_row()["force_role_groups"])


def add_proposed_roles(path):
    manifest = json.loads(path.read_text())
    for split, rows in manifest["splits"].items():
        for row in rows:
            atoms = read(path.parent / row["structure_path"], format="vasp")
            groups = role_groups(atoms)
            row["force_role_groups"] = groups
            row["proposed_per_atom_loss_weights"] = atom_weights(groups, len(atoms)).tolist()
            row["stage"] = "early"
            row.pop("sample_role")
            if split == "train":
                row["proposed_source_stage_sampling_probability"] = 1.
    path.write_text(json.dumps(manifest))


def test_canonical_builder_carries_role_metadata_and_legacy_role_fallback(fixture_manifest, tmp_path):
    path, _ = fixture_manifest
    add_proposed_roles(path)
    database = tmp_path / "new_train.db"
    build_database(path, database, "train")
    actual = connect(database).get(1)
    assert actual.data.sample_role == "adsorption_trajectory_early"
    assert actual.data.adsorption_sampling_probability == 1.
    assert actual.data.adsorption_force_roles[45:] == [1, 3]
    assert sum(actual.data.adsorption_force_weights) == pytest.approx(1.)
    assert actual.data.adsorption_force_weights[:18] == [0.]*18


def test_canonical_verifier_cannot_ignore_proposed_weights(fixture_request):
    path, request, _ = fixture_request
    manifest_path = path.parent / request["manifest_path"]
    add_proposed_roles(manifest_path)
    request["artifacts"][0]["sha256"] = digest(manifest_path)
    path.write_text(json.dumps(request))
    with pytest.raises(ValueError, match="runtime contract v3"):
        verify_request(path)
