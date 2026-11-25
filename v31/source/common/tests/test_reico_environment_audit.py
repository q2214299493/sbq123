"""Coverage diagnostics must preserve provenance and reserved-data isolation."""
from __future__ import annotations

import json

import numpy as np
import pytest
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write

from scripts.adsorption.reico_dataset_audit import audit_labels, choose_anchors, reserved_geometries
from scripts.adsorption.reico_environment_audit import (
    calibrate, describe, nearest, propose_additions, read_geometry, stack, train_inventory,
)
from scripts.artifact_io import sha256_file


def slab():
    positions = [[2.5 * x, 2.5 * y, 2 * z] for z in range(5) for x in range(3) for y in range(3)]
    atoms = Atoms(["Fe"] * 45 + ["C", "C", "O", "H"],
                  positions=positions + [[1, 1, 10], [2.3, 1, 10.1], [1, 1, 11.3], [.2, 1, 10.5]],
                  cell=[7.5, 7.5, 23], pbc=[True, True, False])
    atoms.set_constraint(FixAtoms(indices=range(18)))
    return atoms


def geometry_row(tmp_path, sid="one", family="family1", partition="train", atoms=None):
    path = tmp_path / (sid + ".vasp")
    write(path, slab() if atoms is None else atoms, format="vasp")
    return {"sample_id": sid, "family_id": family, "partition": partition, "composition": "C2HO",
            "structure_path": str(path), "structure_sha256": sha256_file(path), "geometry_guard_failures": []}


def vector_row(sid, family, vector):
    vector = np.asarray(vector, dtype=float)
    return {"sample_id": sid, "family_id": family, "composition": "C2HO", "roles": np.array(["C"]),
            "vectors": (vector / np.linalg.norm(vector))[None, :]}


def test_partition_and_binding_validation(tmp_path):
    row = geometry_row(tmp_path)
    reserved = {**row, "sample_id": "reserved", "family_id": "family2", "partition": "final_test",
                "frame_metadata_path": "MUST_NOT_OPEN"}
    train, selected = train_inventory({"frames": [row, reserved]}, {"selected": [row, reserved]})
    assert train == selected == [row]
    with pytest.raises(ValueError, match="family split"):
        train_inventory({"frames": [row, {**reserved, "family_id": row["family_id"]}]}, {"selected": []})
    with pytest.raises(ValueError, match="binding"):
        train_inventory({"frames": [row]}, {"selected": [{**row, "structure_sha256": "0" * 64}]})


def test_changed_source_bytes_rejected(tmp_path):
    row = geometry_row(tmp_path)
    with open(row["structure_path"], "a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_geometry(row)


def test_leave_family_out_and_greedy_proposal():
    records = [vector_row("a", "f1", [1, 0]), vector_row("b", "f2", [1, .1]),
               vector_row("c", "f3", [0, 1]), vector_row("d", "f3", [.1, 1])]
    pool, refs = stack(records), stack(records[:2])
    thresholds, _ = calibrate(refs, .95)
    assert thresholds["C"] > 0.001
    distances = nearest(pool, refs)
    chosen, after = propose_additions(records, {"a", "b"}, pool, distances, thresholds, 8)
    assert [r["sample_id"] for r in chosen] == ["c"]
    assert np.max(after["C"]) < np.max(distances["C"])
    assert np.all(after["C"] <= distances["C"])
    blocked, _ = propose_additions(records, {"a", "b"}, pool, distances, thresholds, 8,
                                  eligible=lambda row, proposed: False)
    assert blocked == []


def test_one_family_cannot_calibrate():
    refs = stack([vector_row("a", "same", [1, 0]), vector_row("b", "same", [1, .1])])
    with pytest.raises(ValueError, match="two families"):
        calibrate(refs, .95)


def test_soap_pbc_translation_and_cache(tmp_path):
    SOAP = pytest.importorskip("dscribe.descriptors").SOAP
    soap = SOAP(species=["Fe", "C", "H", "O"], r_cut=5., n_max=4, l_max=3, sigma=.5, periodic=True)
    row = geometry_row(tmp_path)
    original = read_geometry(row)
    first = describe(row, original, soap, tmp_path / "cache", 3.)
    translated = original.copy()
    translated.positions[:, 0] += original.cell[0, 0]
    shifted = geometry_row(tmp_path, "shifted", atoms=translated)
    second = describe(shifted, read_geometry(shifted), soap, tmp_path / "cache", 3.)
    np.testing.assert_allclose(first["vectors"], second["vectors"], atol=1e-10, rtol=0)
    cached = describe(row, original, soap, tmp_path / "cache", 3.)
    np.testing.assert_array_equal(first["vectors"], cached["vectors"])
    assert len(first["vectors"]) < len(original)


def label_manifest(tmp_path):
    row = geometry_row(tmp_path)
    atoms = read_geometry(row)
    force = np.zeros((len(atoms), 3))
    force[45, 0] = .01
    row.update(structure_path="one.vasp", symbols=atoms.get_chemical_symbols(), fixed_atom_indices_0based=list(range(18)),
               forces_eV_per_A=force.tolist(), energy_eV_force_label_only=0., source_OUTCAR_sha256="a" * 64,
               electronic_converged=True, geometry_review_pass=True, stage="last2", parent_ionic_converged=True,
               movable_fmax_eV_A=.01, calculation_group="job1", toten_eV_force_label_only=0.)
    source = tmp_path / "labels.json"
    source.write_text(json.dumps({"samples": [row]}), encoding="utf-8")
    row["label_source"] = {"path": source.name, "sha256": sha256_file(source), "sample_id": "one"}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"splits": {"train": [row], "development": [
        {"calculation_group": "reserved", "forces_eV_per_A": "MUST_NOT_USE"}], "heldout": []}}), encoding="utf-8")
    return path, row


def test_label_reuse_does_not_read_reserved_forces(tmp_path):
    path, _ = label_manifest(tmp_path)
    config = {"reserved_geometry_isolation_A": .2, "geometry_duplicate_A": .1,
              "near_equilibrium_force_diagnostic_eV_A": .05, "anchor_force_candidate_eV_A": .02}
    report, reusable = audit_labels(path, [], config)
    assert report["verified_rows"] == 1 and not report["failures"]
    anchors = choose_anchors(reusable, config)
    assert len(anchors) == 1 and anchors[0]["movable_fmax_eV_A"] == .01
    atoms = read_geometry(geometry_row(tmp_path, "reserved"))
    _, isolated = audit_labels(path, [({"sample_id": "reserved"}, atoms)], config)
    assert isolated == []


def test_changed_raw_force_is_not_reused(tmp_path):
    path, _ = label_manifest(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["splits"]["train"][0]["forces_eV_per_A"][45][0] = .02
    path.write_text(json.dumps(data), encoding="utf-8")
    report, reusable = audit_labels(path, [], {"reserved_geometry_isolation_A": .2,
                                             "near_equilibrium_force_diagnostic_eV_A": .05})
    assert reusable == [] and "differ from source" in report["failures"][0]["error"]


def test_reserved_catalog_resolves_by_exact_geometry_hash(tmp_path):
    row = geometry_row(tmp_path, "original")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"splits": {"heldout": [{**row, "structure_path": "original.vasp"}]}}), encoding="utf-8")
    reserved = {**row, "sample_id": "renamed", "structure_path": "not_copied.vasp", "forces_eV_per_A": "MUST_NOT_USE"}
    manifest = {"splits": {"development": [], "heldout": []}, "quarantined_observed_heldout": [reserved]}
    values = reserved_geometries({"frames": []}, manifest, tmp_path, [catalog])
    assert values[0][0]["sample_id"] == "renamed"
    assert len(values[0][1]) == 49
    reserved["structure_sha256"] = "0" * 64
    with pytest.raises(FileNotFoundError):
        reserved_geometries({"frames": []}, manifest, tmp_path, [catalog])


def test_low_force_without_parent_convergence_is_not_anchor(tmp_path):
    row = {"sample_id": "low", "parent_ionic_converged": False, "movable_fmax_eV_A": .001,
           "calculation_group": "unfinished", "atoms": slab()}
    assert choose_anchors([row], {"anchor_force_candidate_eV_A": .02, "geometry_duplicate_A": .1}) == []
