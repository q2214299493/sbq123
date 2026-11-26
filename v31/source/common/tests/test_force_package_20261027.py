import copy

import pytest

from archive.fe110_force_package_20261027.prepare import verify_proof
from archive.fe110_force_package_20261027.verify import archive_chain, compare_source
from scripts.artifact_io import sha256_file, write_json_exclusive


def fixture_row():
    return {"sample_id": "same", "split": "development", "forces_eV_per_A": [[1., 2., 3.]],
            "source_job_id": "job", "magnetic_review_level": "LEGACY_TOTAL_MAGNETIZATION_ONLY",
            "proposed_per_atom_loss_weights": [1.], "proposed_source_stage_sampling_probability": None,
            "force_role_groups": {"adsorbate_C": [0]}}


@pytest.mark.parametrize("field,value", [("forces_eV_per_A", [[9., 2., 3.]]),
    ("source_job_id", "other"), ("split", "train"),
    ("magnetic_review_level", "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"),
    ("proposed_per_atom_loss_weights", [.5])])
def test_source_physics_partition_and_magnetic_tier_cannot_change(field, value):
    original = fixture_row()
    changed = copy.deepcopy(original)
    changed[field] = value
    with pytest.raises(ValueError):
        compare_source(changed, original)


def test_training_sampler_can_renormalize_without_changing_force_labels():
    original = fixture_row()
    original["split"] = "train"
    changed = copy.deepcopy(original)
    changed["proposed_source_stage_sampling_probability"] = 1/512
    compare_source(changed, original)


def test_isolation_proof_cannot_hide_a_conflict(tmp_path):
    path = tmp_path / "proof.json"
    write_json_exclusive(path, {"geometry_conflicts": [{"sample_id": "bad"}], "quarantined_sample_ids": [],
        "threshold_A": .2, "reserved_geometries": 513, "reserved_forces_or_energies_used": False})
    with pytest.raises(ValueError, match="isolation"):
        verify_proof(path)


def test_nested_archive_bytes_are_verified_after_relocation(tmp_path):
    archive = tmp_path / "original.json"
    write_json_exclusive(archive, {"samples": []})
    label = {"source_archive": {"path": "original.json", "sha256": sha256_file(archive)}}
    assert archive_chain(tmp_path, label) == {archive}
    archive.write_text("{}")
    with pytest.raises(ValueError, match="source bytes"):
        archive_chain(tmp_path, label)
