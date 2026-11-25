"""Regression guards for admission scope and source-preserving materialization."""
import copy

import pytest

from archive.fe110_force_package_20261113.prepare import (
    check_preserved, inventory_entries, require_admission,
)
from scripts.artifact_io import sha256_file, write_json_exclusive


def admission_fixture():
    base = {"split": "train", "partition": "train", "calculation_group": "reico_family_0099",
            "electronic_converged": True, "geometry_review_pass": True, "magnetic_review_flags": [],
            "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE",
            "forces_eV_per_A": [[0., 0., 0.]] * 50 + [[.03, 0., 0.]], "movable_fmax_eV_A": .03}
    rows = [{**copy.deepcopy(base), "sample_id": str(i), "ionic_step": i} for i in range(1, 25)]
    decision = {"dataset_admission_approved": True, "decision": "include_all_24_in_next_training_partition",
                "approved_candidate_manifest_sha256": "digest", "training_authorized": False,
                "formal_adsorption_acceptance": False, "approved_sample_ids": [r["sample_id"] for r in rows],
                "approved_ionic_steps": list(range(1, 25)),
                "prospective_counts": {"train": 536, "development": 78, "heldout": 53,
                                       "observed_heldout_quarantined": 16}}
    return decision, rows


def test_admitted_labels_do_not_imply_training_or_scheduler_done():
    decision, rows = admission_fixture()
    require_admission(decision, "digest", rows)


@pytest.mark.parametrize("field,value", [("dataset_admission_approved", False),
    ("training_authorized", True), ("formal_adsorption_acceptance", True),
    ("approved_candidate_manifest_sha256", "other"), ("approved_sample_ids", []),
    ("approved_ionic_steps", [])])
def test_changed_admission_is_rejected(field, value):
    decision, rows = admission_fixture()
    decision[field] = value
    with pytest.raises(ValueError):
        require_admission(decision, "digest", rows)


def test_extra_candidate_cannot_be_assembled():
    decision, rows = admission_fixture()
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError):
        require_admission(decision, "digest", rows)


@pytest.mark.parametrize("field,value", [("forces_eV_per_A", [[2., 0., 0.]]),
    ("magnetic_review_level", "upgraded"), ("proposed_per_atom_loss_weights", [.5]),
    ("split", "train"), ("proposed_source_stage_sampling_probability", .5)])
def test_protected_development_fields_cannot_change(field, value):
    old = {"split": "development", "forces_eV_per_A": [[1., 0., 0.]],
           "magnetic_review_level": "legacy", "proposed_per_atom_loss_weights": [1.],
           "proposed_source_stage_sampling_probability": None}
    new = copy.deepcopy(old)
    new[field] = value
    with pytest.raises(ValueError):
        check_preserved(new, old)


def test_training_sampler_only_renormalizes():
    old = {"split": "train", "forces_eV_per_A": [[1., 0., 0.]],
           "proposed_source_stage_sampling_probability": 1 / 512}
    check_preserved({**old, "proposed_source_stage_sampling_probability": 1 / 536}, old)


def test_inventory_rejects_modified_or_unlisted_file(tmp_path):
    target = tmp_path / "source.json"
    target.write_bytes(b"400.0\n")
    write_json_exclusive(tmp_path / "package_inventory.json", {"files": [
        {"path": target.name, "sha256": sha256_file(target), "bytes": target.stat().st_size}]})
    assert len(inventory_entries(tmp_path)) == 2
    target.write_bytes(b"400\n")
    with pytest.raises(ValueError, match="bytes changed"):
        inventory_entries(tmp_path)
    (tmp_path / "unexpected.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="membership changed"):
        inventory_entries(tmp_path)
