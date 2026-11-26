from __future__ import annotations

import copy
import json

import pytest

from scripts.artifact_io import sha256_file
from scripts.matris_training_exclusions import (
    assert_dataset_splits_disjoint, assert_training_samples_disjoint, geometry_fingerprint,
    load_heldout_exclusions, structure_equivalence_fingerprint, write_heldout_exclusion_manifest,
)
from scripts.matris_energy_force_finetune import validate_review_package
from scripts.matris_training_data import _hydrate_samples
from scripts.neb_agent.utils_structure import read_poscar
from scripts.registry_write import apply_registry_batch
from scripts.registry_schema import migrate_registry
from tests.test_matris_training_exclusions import _write_plan, _write_poscar
from tests.test_registry_write import _batch


def binding(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return binding(path)


def samples_fixture(tmp_path):
    rows, samples = [], []
    output = tmp_path / "synthetic-output.txt"
    output.write_text("Synthetic accepted output binding; not a production calculation")
    labels = tmp_path / "labels.json"
    for i, name in enumerate(("training", "validation", "test")):
        path = tmp_path / f"{name}.vasp"
        _write_poscar(path, movable_x=.3 + i * .07, comment=name)
        rows.append({"sample_id": name, "calculation_id": f"calc-{i}", "reaction_id": f"reaction-{i}",
                     "normal_completion": True, "ionic_converged": True, "structure_sha256": sha256_file(path),
                     "final_toten_eV": -10., "forces_eV_per_A": [[0., 0., 0.]] * 2,
                     "source_files": [binding(output)]})
        samples.append({"sample_id": name, "source_sample_id": name, "calculation_id": f"calc-{i}",
                        "reaction_id": f"reaction-{i}", "dataset_role": name,
                        "structure": {**binding(path), "atom_count": 2, "geometry_sha256": geometry_fingerprint(read_poscar(path))},
                        "vasp_label": {"energy_eV": -10.}, "fixed_atom_indices_zero_based": [0]})
    reference = write(labels, {"calibration_id": "synthetic", "samples": rows})
    for sample in samples:
        sample["label_source"] = reference
    return samples, labels


def test_complete_bound_dataset_is_validated_before_split_eligibility(tmp_path):
    samples, _ = samples_fixture(tmp_path)
    hydrated = _hydrate_samples(samples, label_cache={})
    assert {sample["data_state"] for sample in hydrated} == {"VALIDATED"}
    assert_dataset_splits_disjoint(dict(zip(("training", "validation", "test"), [[s] for s in hydrated])), structures_root=tmp_path)


@pytest.mark.parametrize("field", ["calculation_id", "source_sample_id", "sample_id"])
def test_training_identity_missing_rejected(tmp_path, field):
    samples, _ = samples_fixture(tmp_path)
    del samples[0][field]
    with pytest.raises(ValueError):
        _hydrate_samples(samples, label_cache={})


@pytest.mark.parametrize("change", ["nonfinite", "prediction", "missing_source", "unconverged", "duplicate"])
def test_training_eligibility_requires_current_validated_evidence(tmp_path, change):
    samples, labels = samples_fixture(tmp_path)
    payload = json.loads(labels.read_text())
    if change == "nonfinite":
        payload["samples"][0]["forces_eV_per_A"][0][0] = float("nan")
    elif change == "prediction":
        payload["samples"][0]["type"] = "model_prediction"
    elif change == "missing_source":
        payload["samples"][0]["source_files"] = []
    elif change == "unconverged":
        payload["samples"][0]["ionic_converged"] = False
    else:
        payload["samples"].append(payload["samples"][0])
    ref = write(labels, payload)
    for sample in samples:
        sample["data_state"] = "TRAINING_ELIGIBLE"
        sample["label_source"] = ref
    with pytest.raises(ValueError):
        _hydrate_samples(samples, label_cache={})


@pytest.mark.parametrize("pair", [("training", "validation"), ("training", "test"), ("validation", "test")])
def test_duplicate_reaction_across_any_split_rejected(tmp_path, pair):
    samples, _ = samples_fixture(tmp_path)
    samples[1]["reaction_id"] = samples[0]["reaction_id"]
    with pytest.raises(ValueError, match="reaction leakage"):
        assert_dataset_splits_disjoint({pair[0]: [samples[0]], pair[1]: [samples[1]]}, structures_root=tmp_path)


def test_reordered_equivalent_structure_has_same_split_identity(tmp_path):
    source = tmp_path / "source.vasp"
    _write_poscar(source, movable_x=.25, comment="original")
    original = read_poscar(source)
    reordered = copy.deepcopy(original)
    reordered.frac = original.frac[::-1] + .25
    reordered.symbols = original.symbols[::-1]
    reordered.counts = original.counts[::-1]
    reordered.flags = original.flags[::-1]
    assert geometry_fingerprint(original) != geometry_fingerprint(reordered)
    assert structure_equivalence_fingerprint(original) == structure_equivalence_fingerprint(reordered)
    rotated = copy.deepcopy(original)
    rotated.cell = original.cell[:, [2, 0, 1]]
    assert structure_equivalence_fingerprint(original) == structure_equivalence_fingerprint(rotated)


def test_reordered_heldout_cannot_enter_training(tmp_path):
    plan_path, heldout = _write_plan(tmp_path)
    manifest_path = tmp_path / "exclusion.json"
    write_heldout_exclusion_manifest(plan_path, manifest_path)
    manifest = load_heldout_exclusions(manifest_path, expected_sha256=sha256_file(manifest_path))
    renamed = tmp_path / "reordered.vasp"
    lines = heldout.read_text().splitlines()
    lines[5] = "H Fe"
    lines[-2:] = lines[-2:][::-1]
    renamed.write_text("\n".join(lines) + "\n")
    sample = {"sample_id": "changed-order", "structure": binding(renamed)}
    with pytest.raises(ValueError, match="overlaps held-out geometry"):
        assert_training_samples_disjoint([sample], structures_root=tmp_path, exclusion_manifest=manifest)


def review_fixture(tmp_path):
    samples, labels = samples_fixture(tmp_path)
    plan, heldout = _write_plan(tmp_path)
    # Bind the test split to the actual heldout source, not a claimed digest.
    samples[2]["structure"] = {**binding(heldout), "atom_count": 2, "geometry_sha256": geometry_fingerprint(read_poscar(heldout))}
    payload = json.loads(labels.read_text())
    payload["samples"][2]["structure_sha256"] = sha256_file(heldout)
    ref = write(labels, payload)
    for sample in samples:
        sample["label_source"] = ref
    exclusion = tmp_path / "exclusions.json"
    write_heldout_exclusion_manifest(plan, exclusion)
    manifest = {"document_kind": "matris_energy_force_replay_manifest", "execution_authorized": False,
                "base_checkpoint_sha256": "a" * 64, "training_samples": [samples[0]],
                "validation_only_samples": [samples[1]], "frozen_ts_heldout_validation_samples": [samples[2]],
                "counts": {"total_optimizer_samples": 1, "frozen_ts_heldout_validation": 1}}
    manifest_path = tmp_path / "manifest.json"
    review = {"document_kind": "matris_energy_force_replay_finetune_review_request",
              "status": "prepared_awaiting_separate_gpu_finetune_authorization", "base_checkpoint_sha256": "a" * 64,
              "replay_training_manifest": write(manifest_path, manifest), "heldout_exclusion_manifest": binding(exclusion)}
    review_path = tmp_path / "review.json"
    write(review_path, review)
    return review_path, manifest_path, labels


def test_formal_training_preflight_derives_eligibility_read_only(tmp_path):
    review, _, _ = review_fixture(tmp_path)
    before = {p: sha256_file(p) for p in tmp_path.rglob("*") if p.is_file()}
    result = validate_review_package(review)
    assert result["training_samples"][0]["data_state"] == "TRAINING_ELIGIBLE"
    assert result["heldout_validation_samples"][0]["data_state"] == "VALIDATED"
    assert before == {p: sha256_file(p) for p in before}


def test_formal_preflight_rejects_rehashed_reaction_leakage(tmp_path):
    review_path, manifest_path, labels = review_fixture(tmp_path)
    payload = json.loads(labels.read_text())
    payload["samples"][2]["reaction_id"] = payload["samples"][0]["reaction_id"]
    reference = write(labels, payload)
    manifest = json.loads(manifest_path.read_text())
    for key in ("training_samples", "validation_only_samples", "frozen_ts_heldout_validation_samples"):
        manifest[key][0]["label_source"] = reference
    manifest["frozen_ts_heldout_validation_samples"][0]["reaction_id"] = payload["samples"][0]["reaction_id"]
    review = json.loads(review_path.read_text())
    review["replay_training_manifest"] = write(manifest_path, manifest)
    write(review_path, review)
    with pytest.raises(ValueError, match="reaction leakage"):
        validate_review_package(review_path)


def test_prediction_rejected_before_registry_transaction(tmp_path):
    db = tmp_path / "registry.sqlite3"
    migrate_registry(db)
    before = sha256_file(db)
    batch = _batch()
    batch["result_provenance"] = {"fixture-energy": {"type": "model_prediction"}}
    with pytest.raises(ValueError, match="predictions"):
        apply_registry_batch(db, batch, confirmed_sha256="a" * 64)
    assert sha256_file(db) == before


def test_fake_dual_model_producer_emits_candidate_provenance(tmp_path):
    from tests.test_dual_model_ts_force_prediction_batch import _request, _FixedCalculator
    from scripts.dual_model_ts_force_prediction_batch import run_batch
    from scripts.prediction_provenance import validate_prediction

    request, primary, secondary = _request(tmp_path)
    result = run_batch(request, primary, secondary, tmp_path / "result.json", device="cpu",
                       calculator_loader=lambda *args: _FixedCalculator(1., .1))
    for row in result["predictions"]:
        for metadata in row["prediction_provenance"].values():
            validate_prediction(metadata)
            assert metadata["input_fingerprint"] == row["structure_sha256"]
            assert metadata["uncertainty"]["status"] == "unavailable"


def test_fake_aqcat_producer_emits_valid_metadata(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from scripts import aqcat25_ts_force_prediction as runner
    from scripts.prediction_provenance import validate_prediction
    from tests.test_dual_model_ts_force_prediction_batch import _request, _FixedCalculator

    request, checkpoint, _ = _request(tmp_path)
    structure = tmp_path / "00.vasp"
    request_data = {"structure": binding(structure), "checkpoint": binding(checkpoint),
                    "indexed_bond_changes": [{"atoms_1based": [3, 4], "change": "form"}], "adsorbate_indices_1based": [3, 4]}
    monkeypatch.setattr(runner, "load_document", lambda *a, **kw: request_data)
    monkeypatch.setitem(sys.modules, "fairchem.core.common.relaxation.ase_utils",
                        SimpleNamespace(patched_calc=lambda **kw: _FixedCalculator(-1., .1)))
    output = tmp_path / "prediction.json"
    monkeypatch.setattr(sys, "argv", ["prediction", "--request", str(request), "--output", str(output)])
    runner.main()
    record = json.loads(output.read_text())
    validate_prediction(record["prediction_provenance"])
    assert record["scientifically_validated_ts"] is False
    assert record["prediction_provenance"]["model_version"] == sha256_file(checkpoint)


def aq_manifest(tmp_path):
    samples, _ = samples_fixture(tmp_path)
    rows = [{**sample, "structure_path": sample["structure"]["path"], "structure_sha256": sample["structure"]["sha256"],
             "geometry_sha256": sample["structure"]["geometry_sha256"], "energy_eV_force_label_only": -10.,
             "forces_eV_per_A": [[0., 0., 0.]] * 2, "source_result_class": "vasp_completed_adsorption_calibration_force_label",
             "sample_role": "adsorption_regression_replay", "source_labels_sha256": sample["label_source"]["sha256"]}
            for sample in samples]
    path = tmp_path / "aq-manifest.json"
    payload = {"document_kind": "aqcat25_ts_force_only_training_manifest", "training_target": "forces_only",
               "energy_loss_coefficient": 0., "restrictions": {"reportable_final_energy": False},
               "training_samples": rows[:1], "validation_samples": rows[1:]}
    write(path, payload)
    return path, payload


def test_aq_database_validates_dataset_before_writing(tmp_path):
    from ase.db import connect
    from scripts.aqcat25_ts_training_data import build_database

    manifest, _ = aq_manifest(tmp_path)
    output = tmp_path / "train.db"
    assert build_database(manifest, output) == 1
    assert connect(output).get(1).data["data_state"] == "TRAINING_ELIGIBLE"


@pytest.mark.parametrize("damage", ["reaction", "source", "prediction", "energy"])
def test_aq_database_rejects_invalid_data_before_creation(tmp_path, damage):
    from scripts.aqcat25_ts_training_data import build_database

    manifest, payload = aq_manifest(tmp_path)
    train = payload["training_samples"][0]
    if damage == "reaction":
        payload["validation_samples"][0]["reaction_id"] = train["reaction_id"]
    elif damage == "source":
        train["label_source"]["path"] = str(tmp_path / "missing.json")
    elif damage == "prediction":
        train["source_result_class"] = "model_prediction"
    else:
        train["energy_eV_force_label_only"] = float("nan")
    write(manifest, payload)
    output = tmp_path / "train.db"
    with pytest.raises(ValueError):
        build_database(manifest, output)
    assert not output.exists()


@pytest.mark.parametrize("reaction", [None, "", "None", True, float("nan")])
def test_ts_label_source_requires_declared_reaction_identity(tmp_path, reaction):
    from scripts.matris_training_data import _validate_label_set

    path = tmp_path / "ts-labels.json"
    write(path, {"document_kind": "dual_model_ts_vasp_force_label_set", "reaction_id": reaction})
    with pytest.raises(ValueError, match="reaction identity"):
        _validate_label_set(path)
