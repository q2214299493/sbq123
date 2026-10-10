import copy
import json

import numpy as np
import pytest
import yaml
from ase import Atoms
from ase.constraints import FixAtoms
from ase.db import connect
from ase.io import write

from archive.fe110_five_c2_adsorption_20261006.prepare_adsorption_finetune import expand_magmom, select_temporal_frames
from scripts.adsorption.force_finetune import build_database, build_database_metadata, digest, force_metrics, load_manifest, local_path, validate_database_metadata, validate_sampler_contract, verify_request, warm_start


@pytest.fixture
def fixture_manifest(tmp_path):
    splits = {}
    for i, split in enumerate(("train", "development", "heldout")):
        positions = np.zeros((47, 3))
        positions[:, 0] = np.arange(47) * 1.5
        positions[-1, 2] = 2 + i
        atoms = Atoms("Fe45CH", positions=positions, cell=[100, 20, 20], pbc=True)
        atoms.set_constraint(FixAtoms(indices=list(range(18))))
        path = tmp_path / (split + ".vasp")
        write(path, atoms, format="vasp", direct=True, vasp5=True)
        source = {"sample_id": split, "structure_sha256": digest(path), "symbols": atoms.get_chemical_symbols(),
                  "forces_eV_per_A": np.full((47, 3), .03).tolist(), "toten_eV_force_label_only": -100.,
                  "source_OUTCAR_sha256": str(i)*64}
        label_path = tmp_path / (split + "_source.json")
        label_path.write_text(json.dumps({"samples": [source]}))
        row = {**source, "structure_path": path.name, "energy_eV_force_label_only": -100.,
               "structure_equivalence_sha256": str(i)*64, "calculation_group": "job" + str(i),
               "fixed_atom_indices_0based": list(range(18)), "electronic_converged": True,
               "geometry_review_pass": True, "sample_role": "adsorption_trajectory_" + split, "ionic_step": 1,
               "label_source": {"path": label_path.name, "sha256": digest(label_path), "sample_id": split}}
        splits[split] = [row]
    manifest = {"document_kind": "aqcat25_adsorption_force_training_manifest", "training_target": "forces_only",
                "energy_loss_coefficient": 0, "reportable_final_energy": False, "splits": splits}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


def replace_manifest(path, payload):
    path.write_text(json.dumps(payload))


def test_accepted_source_and_raw_database_forces(fixture_manifest, tmp_path):
    path, _ = fixture_manifest
    assert len(load_manifest(path)["splits"]["train"]) == 1
    database = tmp_path / "train.db"
    assert build_database(path, database, "train") == 1
    row = connect(database).get(1)
    atoms = row.toatoms()
    assert np.allclose(atoms.get_forces(apply_constraint=False), .03)
    assert np.all(atoms.get_forces()[:18] == 0)
    assert list(atoms.constraints[0].get_indices()) == list(range(18))
    assert np.all(atoms.get_tags() == 0)
    assert row.data.reportable_final_energy is False
    with pytest.raises(FileExistsError):
        build_database(path, database, "train")


@pytest.mark.parametrize("field,value,message", [
    ("electronic_converged", False, "unreviewed"),
    ("geometry_review_pass", False, "unreviewed"),
    ("forces_eV_per_A", [[float("nan")]*3]*47, "invalid force"),
    ("fixed_atom_indices_0based", [], "fixed mask"),
    ("source_OUTCAR_sha256", "f"*64, "OUTCAR"),
    ("energy_eV_force_label_only", -99., "energy metadata"),
])
def test_reject_bad_label(fixture_manifest, field, value, message):
    path, payload = fixture_manifest
    payload["splits"]["train"][0][field] = value
    replace_manifest(path, payload)
    with pytest.raises(ValueError, match=message):
        load_manifest(path)


@pytest.mark.parametrize("key", ["calculation_group", "structure_equivalence_sha256"])
def test_reject_split_leakage(fixture_manifest, key):
    path, payload = fixture_manifest
    payload["splits"]["development"][0][key] = payload["splits"]["train"][0][key]
    replace_manifest(path, payload)
    with pytest.raises(ValueError, match="leakage"):
        load_manifest(path)


def test_reject_source_tamper(fixture_manifest):
    path, payload = fixture_manifest
    source = path.parent / payload["splits"]["train"][0]["label_source"]["path"]
    source.write_text("{}")
    with pytest.raises(ValueError, match="source hash"):
        load_manifest(path)


def test_no_package_path_escape(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        local_path(tmp_path, "../outside.json")


def test_force_groups_and_fixed_mask():
    reference = np.ones((4, 3))
    predicted = reference.copy()
    predicted[0] = 900  # ignored fixed Fe
    predicted[2] += 2
    metrics = force_metrics(reference, predicted, ["Fe", "Fe", "C", "H"], [0])
    assert metrics["Fe"]["vector_rmse_eV_A"] == 0
    assert metrics["C"]["vector_rmse_eV_A"] == pytest.approx(np.sqrt(12))
    assert metrics["O"]["atom_count"] == 0
    assert metrics["movable"]["atom_count"] == 3
    with pytest.raises(ValueError, match="nonfinite"):
        force_metrics(reference, np.full((4, 3), np.nan), ["Fe", "Fe", "C", "H"], [0])


def test_metadata_real_row_order_and_exclusive_output(tmp_path):
    database = tmp_path / "train.db"
    db = connect(database)
    db.write(Atoms("H"))
    db.write(Atoms("CH"))
    db.write(Atoms("C2H"))
    db.delete([2])  # gapped ids must not be interpreted as sequential indices
    output = tmp_path / "metadata.npz"
    assert build_database_metadata(database, output)["rows"] == 2
    with np.load(output, allow_pickle=False) as values:
        assert values["natoms"].tolist() == [1, 3]
        assert values["row_ids"].tolist() == [1, 3]
    with pytest.raises(FileExistsError):
        build_database_metadata(database, output)


@pytest.mark.parametrize("natoms", [[1.0, 2.0], [2, 1], [1]])
def test_metadata_reject_float_wrong_order_and_wrong_length(tmp_path, natoms):
    database = tmp_path / "train.db"
    db = connect(database)
    db.write(Atoms("H"))
    db.write(Atoms("CH"))
    metadata = tmp_path / "metadata.npz"
    np.savez(metadata, natoms=np.asarray(natoms), row_ids=np.asarray([1, 2]))
    with pytest.raises(ValueError, match="metadata mismatch"):
        validate_database_metadata(database, metadata)


def test_missing_database_not_created(tmp_path):
    missing = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        build_database_metadata(missing, tmp_path / "metadata.npz")
    assert not missing.exists()


@pytest.fixture
def sampler_contract(tmp_path):
    remote = "/home/sbq/sbq/package"
    request = {"runtime_contract_version": 2, "remote_package_root": remote,
               "training_limits": {"seed": 42, "batch_size": 1}, "artifacts": []}
    config = {"seed": 42, "optim": {"batch_size": 1}, "dataset": {}}
    for split, key in (("train", "train"), ("development", "val")):
        database = tmp_path / f"{split}.db"
        connect(database).write(Atoms("CH"))
        metadata = tmp_path / f"{split}_metadata.npz"
        build_database_metadata(database, metadata)
        config["dataset"][key] = {"metadata_path": remote + "/" + metadata.name}
        request["artifacts"] += [{"path": database.name}, {"path": metadata.name}]
    return tmp_path / "request.json", request, config


def test_sampler_contract_valid(sampler_contract):
    validate_sampler_contract(*sampler_contract)


@pytest.mark.parametrize("problem,message", [("seed", "seed mismatch"), ("batch", "batch size"),
                                            ("unbound", "not hash bound"), ("shared", "path mismatch")])
def test_sampler_contract_fail_closed(sampler_contract, problem, message):
    path, request, config = sampler_contract
    if problem == "seed":
        config["seed"] = 0
    elif problem == "batch":
        config["optim"]["batch_size"] = 2
    elif problem == "unbound":
        request["artifacts"].pop()
    else:
        config["dataset"]["val"]["metadata_path"] = config["dataset"]["train"]["metadata_path"]
    with pytest.raises(ValueError, match=message):
        validate_sampler_contract(path, request, config)


def test_temporal_dedup_preserves_high_force_and_frozen_heldout():
    def row(sid, step, force, split="train"):
        return {"sample_id": sid, "source_name": "jobA" if split == "train" else "jobB",
                "split": split, "ionic_step": step, "forces_eV_per_A": [[force]*3]*47}
    samples = [row("a", 1, .02), row("b", 2, .01), row("c", 3, .08), row("h1", 1, 0, "heldout"), row("h2", 2, 0, "heldout")]
    pairs = [{"first": x, "second": y, "adsorbate_symmetry_RMSD_A": .001} for x, y in (("a", "b"), ("a", "c"), ("b", "c"), ("h1", "h2"))]
    kept, exclusions = select_temporal_frames(samples, {"near_pairs": pairs, "excluded_from_fit_or_epoch_selection": {}})
    assert {r["sample_id"] for r in kept} == {"b", "c", "h1", "h2"}
    assert exclusions["a"]["representative"] == "b"
    original = copy.deepcopy(samples)
    select_temporal_frames(samples, {"near_pairs": pairs, "excluded_from_fit_or_epoch_selection": {"a": ["h1"]}})
    assert samples == original


def test_magmom_repetition():
    assert expand_magmom("2*2.2 0.0") == [2.2, 2.2, 0]


def test_invalid_request_blocks_before_checkpoint_loading(tmp_path):
    request = tmp_path / "bad_request.json"
    request.write_text("{}")
    with pytest.raises(ValueError, match="wrong request"):
        warm_start(request, tmp_path / "nonexistent_authorization.json", tmp_path / "model.pt")
    assert not (tmp_path / "model.pt").exists()


@pytest.fixture
def fixture_request(fixture_manifest):
    manifest_path, _ = fixture_manifest
    remote = "/home/sbq/sbq/test_package"
    dataset = {"atoms_transform_args": {"skip_always": True}}
    config = {"optim": {"max_epochs": 4, "lr_initial": 1e-5},
              "dataset": {"train": {**dataset, "src": remote + "/train.db"},
                          "val": {**dataset, "src": remote + "/development.db"}},
              "outputs": {"forces": {"train_on_free_atoms": True, "eval_on_free_atoms": True}},
              "loss_functions": [{"energy": {"coefficient": 0}}, {"forces": {"coefficient": 1}}]}
    config_path = manifest_path.parent / "config.yml"
    config_path.write_text(yaml.safe_dump(config))
    request = {"document_kind": "aqcat25_adsorption_small_finetune_request", "manifest_path": manifest_path.name,
               "config_path": config_path.name, "remote_package_root": remote,
               "training_limits": {"epochs": 4, "learning_rate": 1e-5},
               "split_counts": {s: 1 for s in ("train", "development", "heldout")},
               "training_authorized": False,
               "artifacts": [{"path": p.name, "sha256": digest(p)} for p in (manifest_path, config_path)]}
    request_path = manifest_path.parent / "request.json"
    request_path.write_text(json.dumps(request))
    return request_path, request, config


def test_request_verification_no_training(fixture_request):
    path, _, _ = fixture_request
    assert verify_request(path)["training_authorized"] is False
    assert verify_request(path)["model_run"] is False


def test_request_stale_artifact_rejected(fixture_request):
    path, request, _ = fixture_request
    (path.parent / request["manifest_path"]).write_text("{}")
    with pytest.raises(ValueError, match="artifact binding"):
        verify_request(path)


def test_heldout_in_epoch_selection_rejected(fixture_request):
    path, request, config = fixture_request
    config_path = path.parent / request["config_path"]
    config["dataset"]["val"]["src"] = request["remote_package_root"] + "/heldout.db"
    config_path.write_text(yaml.safe_dump(config))
    request["artifacts"][1]["sha256"] = digest(config_path)
    path.write_text(json.dumps(request))
    with pytest.raises(ValueError, match="split mismatch"):
        verify_request(path)


def test_stale_authorization_blocks_before_torch(fixture_request):
    path, _, _ = fixture_request
    authorization = path.parent / "authorization.json"
    authorization.write_text(json.dumps({"user_authorized": True, "request_sha256": "bad", "action": "RUN_GPU_ADSORPTION_SMALL_FINETUNE"}))
    with pytest.raises(ValueError, match="authorization"):
        warm_start(path, authorization, path.parent / "not_created.pt")
    assert not (path.parent / "not_created.pt").exists()
