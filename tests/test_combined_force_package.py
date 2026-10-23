from __future__ import annotations

import copy
import hashlib

import numpy as np
import pytest
from ase.io import write

from archive.fe110_combined_force_package_20261023 import prepare as p
from tests.test_reico_environment_audit import slab


def group_row(split, job="1", family="family", group="group"):
    return {"split": split, "source_job_id": job, "family_id": family, "calculation_group": group}


@pytest.mark.parametrize("identity", ["family_id", "source_job_id", "calculation_group"])
def test_shared_lineage_never_crosses_partitions(identity):
    a, b = group_row("train"), group_row("heldout", "2", "other", "other")
    b[identity] = a[identity]
    with pytest.raises(ValueError, match="split leakage"):
        p.assert_group_isolation([a, b])


def test_original_replay_without_job_id_uses_its_verified_source_group():
    p.assert_group_isolation([{"split": "train", "calculation_group": "legacy_a"},
                             {"split": "observed_heldout", "calculation_group": "legacy_b"}])


def test_unknown_partition_is_not_silently_mapped_to_training():
    with pytest.raises(ValueError, match="unknown source partition"):
        p.assert_group_isolation([group_row("unknown")])


def static_fixture():
    source = {"sample_id": "one", "family_id": "family", "partition": "final_test", "structure_sha256": "same",
              "data_qc_status": "PASS", "magnetic_review_flags": [], "Fe_positive_moment_count": 45,
              "symbols": ["Fe"]*45+["C", "H"], "local_magnetization_muB": [2.2]*45+[0., 0.],
              "input_output_hashes": {"OUTCAR": "raw"}, "toten_eV_force_label_only": -100.,
              "forces_eV_per_A": [[0., 0., 0.]]*47}
    return source, {"one": {k: source[k] for k in ("partition", "family_id", "structure_sha256")}}


def test_static_normalization_preserves_reserved_partition_and_raw_arrays():
    source, selection = static_fixture()
    original = copy.deepcopy(source)
    row = p.static_row(source, selection)
    assert row["split"] == "heldout" and row["forces_eV_per_A"] == source["forces_eV_per_A"]
    assert row["magnetic_review_level"] == "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE"
    assert source == original


@pytest.mark.parametrize("key,value", [("Fe_positive_moment_count", 44), ("magnetic_review_flags", ["review"]),
                                       ("local_magnetization_muB", []), ("partition", "train"),
                                       ("structure_sha256", "changed")])
def test_bad_or_repartitioned_static_label_cannot_enter_package(key, value):
    source, selection = static_fixture()
    source[key] = value
    with pytest.raises(ValueError, match="binding"):
        p.static_row(source, selection)


def test_uniform_sampling_renormalizes_only_train_metadata():
    rows = [{"symbols": ["Fe"]*45+["C"], "fixed_atom_indices_0based": list(range(18)),
             "forces_eV_per_A": [[5., 0., 0.]]*46, "magnetic_review_level": level}
            for level in ("PRESERVED_LEGACY_SOURCE_REVIEW", "LEGACY_TOTAL_MAGNETIZATION_ONLY")]
    before = copy.deepcopy(rows)
    p.set_uniform_sampling(rows)
    assert sum(r["proposed_source_stage_sampling_probability"] for r in rows) == 1.
    for row, old in zip(rows, before, strict=True):
        assert row["forces_eV_per_A"] == old["forces_eV_per_A"]
        assert row["magnetic_review_level"] == old["magnetic_review_level"]
        assert row["proposed_per_atom_loss_weights"][:18] == [0.]*18
        assert np.isclose(sum(row["proposed_per_atom_loss_weights"]), 1.)


def test_legacy_coverage_uses_existing_group_without_forging_manifest_family():
    rows = [{"sample_id": "old", "calculation_group": "existing_vasp_job"},
            {"sample_id": "new", "family_id": "original_ml_family", "calculation_group": "new_group"}]
    grouped = p.coverage_groups(rows)
    assert grouped[0]["family_id"] == "existing_vasp_job"
    assert grouped[1]["family_id"] == "original_ml_family"
    assert "family_id" not in rows[0]


def test_verified_copy_resumes_without_overwriting_changed_evidence(tmp_path):
    source, target = tmp_path/"source", tmp_path/"target"
    source.write_bytes(b"original")
    digest = hashlib.sha256(b"original").hexdigest()
    p.copy_checked(source, target, digest)
    p.copy_checked(source, target, digest)
    target.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="preserve changed"):
        p.copy_checked(source, target, digest)
    assert target.read_bytes() == b"preserve"


@pytest.mark.parametrize("split,reserved_split,excluded", [("train", "final_test", True),
                                                           ("development", "development", False),
                                                           ("heldout", "observed_heldout", True)])
def test_geometry_conflict_quarantines_without_repartitioning_or_reading_forces(tmp_path, monkeypatch, split, reserved_split, excluded):
    atoms = slab()
    path = tmp_path/"one.vasp"
    write(path, atoms, format="vasp", direct=True, vasp5=True)
    monkeypatch.setattr(p, "surface_pose_symmetries", lambda slab: [(np.eye(3), np.zeros(3))])
    row = {"sample_id": "candidate", "split": split, "structure_path": path.name,
           "symbols": atoms.get_chemical_symbols()}
    reserved = [({"sample_id": "reserved", "partition": reserved_split, "structure_path": str(path),
                  "forces_eV_per_A": "MUST_NOT_BE_READ"}, atoms)]
    retained, report = p.isolate([row], tmp_path, reserved, None, .2)
    assert bool(report["quarantined_sample_ids"]) == excluded
    assert len(retained) == (0 if excluded else 1)
    assert row["split"] == split
    assert report["reserved_forces_or_energies_used"] is False
