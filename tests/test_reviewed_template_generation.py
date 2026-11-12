from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsmind_lite import candidate_generation as builder
from scripts.adsmind_lite.core import detect_surface_sites, load_yaml, read_json, write_json
from scripts.adsmind_lite.evidence_gate import resolve_external_evidence
from scripts.adsmind_lite.prescreen import load_prescreen_rules, plan_species
from scripts.artifact_io import sha256_file
from tests.evidence_fixtures import bound_evidence
from tests.test_adsmind_lite import CONFIG, SLAB, write_site_plan


def template(tmp_path, *, mode="Cartesian", vector=(0.7, 0.2, 1.1)):
    path = tmp_path / "molecule.vasp"
    cart = np.array([[2.1, 2.0, 2.5], np.array([2.1, 2.0, 2.5]) + vector])
    # Positive scale 2: the physical cell is 10 Å, Cartesian input is scaled.
    raw = cart / (10.0 if mode.lower().startswith("d") else 2.0)
    text = "Reviewed synthetic CO\n2\n5 0 0\n0 5 0\n0 0 5\nC O\n1 1\n" + mode + "\n"
    text += "\n".join(" ".join(str(value) for value in row) for row in raw) + "\n"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "sha256": sha256_file(path)}


def bundle(tmp_path, descriptor):
    sites = detect_surface_sites(SLAB, "Fe110", "metallic_fe", CONFIG / "surfaces.yaml", CONFIG / "site_rules.yaml")
    sites_path = tmp_path / "sites.json"
    write_json(sites_path, sites)
    plan_path = write_site_plan(tmp_path / "plan.json", ["CO"], sites)
    plan = read_json(plan_path)
    for motif in plan["species_plans"][0]["candidates"]:
        motif.update(reviewed_structure_template=descriptor, orientation_degrees=90.0)
    write_json(plan_path, plan)
    return sites, sites_path, plan_path


def generate(tmp_path, sites_path, plan_path):
    return builder.generate_candidates(
        SLAB, sites_path, ["CO"], CONFIG / "adsorbate_rules.yaml", tmp_path / "output", plan_path,
    )


def adsorbate_vector(structure, indices):
    delta = structure.frac[indices[1]] - structure.frac[indices[0]]
    delta[:2] -= np.rint(delta[:2])
    return delta @ structure.cell


@pytest.mark.parametrize("mode", ["Cartesian", "Direct", "C", "D"])
def test_reviewed_coordinates_drive_poscar_and_metadata_without_changing_slab(tmp_path, mode):
    descriptor = template(tmp_path, mode=mode)
    _, sites_path, plan_path = bundle(tmp_path, descriptor)
    records = generate(tmp_path, sites_path, plan_path)
    slab = read_poscar(SLAB)
    assert len(records) == 4
    for record in records:
        output = read_poscar(Path(record["initial_structure"]))
        vector = adsorbate_vector(output, record["adsorbate_indices_structure_0based"])
        assert np.allclose(vector, [-0.2, 0.7, 1.1], atol=1e-12)
        assert not np.allclose(vector, [0.0, 0.0, 1.15])
        assert np.array_equal(output.cell, slab.cell)
        for original, target in record["slab_original_to_structure_0based"].items():
            assert np.allclose(output.frac[target], slab.frac[int(original)], atol=1e-14)
            assert output.flags[target] == slab.flags[int(original)]
        provenance = record["geometry_source"]
        assert provenance == {"type": "reviewed_structure_template", **descriptor,
                              "format": "adsorbate_only_POSCAR", "coordinate_units": "angstrom"}
        assert read_json(Path(record["initial_structure"]).with_name("metadata.json"))["geometry_source"] == provenance


@pytest.mark.parametrize("damage", [
    "hash", "missing", "malformed", "nonfinite", "slab", "order", "fixed_atoms", "descriptor", "coordinate_mode",
])
def test_bad_late_template_blocks_entire_batch_without_default_geometry(tmp_path, damage):
    descriptor = template(tmp_path)
    _, sites_path, plan_path = bundle(tmp_path, descriptor)
    bad = deepcopy(descriptor)
    path = tmp_path / "bad.vasp"
    path.write_bytes(Path(descriptor["path"]).read_bytes())
    if damage == "missing":
        bad["path"] = str(tmp_path / "missing.vasp")
    elif damage == "descriptor":
        bad["unreviewed_atom_mapping"] = [0, 1]
    else:
        if damage == "malformed":
            path.write_text("not a POSCAR", encoding="utf-8")
        elif damage == "nonfinite":
            path.write_text(path.read_text().replace("1.05", "nan", 1), encoding="utf-8")
        elif damage == "slab":
            path.write_bytes(SLAB.read_bytes())
        elif damage == "order":
            path.write_text(path.read_text().replace("C O\n", "O C\n"), encoding="utf-8")
        elif damage == "fixed_atoms":
            path.write_text(path.read_text().replace("Cartesian\n", "Selective Dynamics\nCartesian\n")
                            .replace("1.05 1.0 1.25", "1.05 1.0 1.25 F F F")
                            .replace("1.4 1.1 1.8", "1.4 1.1 1.8 T T T"), encoding="utf-8")
        elif damage == "coordinate_mode":
            path.write_text(path.read_text().replace("Cartesian\n", "Unknown\n"), encoding="utf-8")
        bad.update(path=str(path), sha256="0" * 64 if damage == "hash" else sha256_file(path))
    plan = read_json(plan_path)
    plan["species_plans"][0]["candidates"][-1]["reviewed_structure_template"] = bad
    write_json(plan_path, plan)
    with pytest.raises(ValueError, match="reviewed_template"):
        generate(tmp_path, sites_path, plan_path)
    assert not (tmp_path / "output").exists()


def test_template_required_flag_cannot_be_satisfied_by_available_motif_id(tmp_path):
    _, sites_path, plan_path = bundle(tmp_path, template(tmp_path))
    plan = read_json(plan_path)
    motif = plan["species_plans"][0]["candidates"][-1]
    del motif["reviewed_structure_template"]
    motif.update(build_ready=True, template_required=True)
    write_json(plan_path, plan)
    with pytest.raises(ValueError, match="reviewed_structure_template_required"):
        generate(tmp_path, sites_path, plan_path)
    assert not (tmp_path / "output").exists()


def test_unconstrained_selective_dynamics_template_is_supported(tmp_path):
    descriptor = template(tmp_path, mode="D")
    path = Path(descriptor["path"])
    lines = path.read_text().splitlines()
    lines.insert(7, "Selective Dynamics")
    lines[9:] = [line + " t T t" for line in lines[9:]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    descriptor["sha256"] = sha256_file(path)
    _, sites_path, plan_path = bundle(tmp_path, descriptor)
    assert len(generate(tmp_path, sites_path, plan_path)) == 4


def test_external_gate_template_is_consumed_by_real_generator(tmp_path):
    descriptor = template(tmp_path)
    _, sites_path, plan_path = bundle(tmp_path, descriptor)
    motifs = [
        {"motif_id": "CO_" + site, "site_pattern": site, "binding_mode": "monodentate", "binding_atoms": ["C"],
         "geometry_summary": "Synthetic molecular template", "stability_rank": rank,
         "stability_evidence": "compared_relaxed_adsorption_energies", "reviewed_structure_template": descriptor}
        for rank, site in enumerate(("top", "short_bridge", "long_bridge"), 1)
    ]
    record = {"id": "template-fixture", "record_id": "template-fixture", "source_id": "catalysis-hub",
              "source_url": "https://api.catalysis-hub.org/graphql", "source_access_verified": True,
              "retrieved_at": "2026-09-09T00:00:00Z", "title": "Synthetic template integration",
              "summary": "Toy template test without physical minimum claims", "data_types": ["structure"],
              "exact_surface_match": True, "exact_adsorbate_match": True, "stable_motifs": motifs}
    record["evidence"] = bound_evidence(record, compatibility={"species": "CO", "surface": "Fe110"})
    external = resolve_external_evidence(
        {"species": "CO", "surface": "Fe110", "whitelist": {"status": "MATCH", "records": [record]}},
        load_yaml(CONFIG / "evidence_gate.yaml"),
    )
    planned = plan_species("CO", load_prescreen_rules(str(CONFIG / "prescreen_rules.yaml")), external_plans={"CO": external})
    write_json(plan_path, {"species_plans": [planned]})
    records = generate(tmp_path, sites_path, plan_path)
    assert len(records) == 3
    for record in records:
        structure = read_poscar(Path(record["initial_structure"]))
        assert np.allclose(adsorbate_vector(structure, record["adsorbate_indices_structure_0based"]), [0.7, 0.2, 1.1])
        assert record["geometry_source"]["sha256"] == descriptor["sha256"]


def test_direct_composer_rejects_unsupported_binding_even_with_valid_template(tmp_path):
    sites, _, _ = bundle(tmp_path, template(tmp_path))
    slab = read_poscar(SLAB)
    rule = load_yaml(CONFIG / "adsorbate_rules.yaml")["adsorbates"]["CO"]
    motif = {"site_pattern": "top", "binding_mode": "bidentate", "binding_atoms": ["C", "O"],
             "reviewed_structure_template": template(tmp_path)}
    with pytest.raises(ValueError, match="binding_mode_not_supported_by_generator"):
        builder.compose_candidate_structure(slab, builder.site_from_record(sites["sites"][0], slab), "CO", rule, motif)


def test_template_geometry_does_not_depend_on_default_coordinates(tmp_path):
    descriptor = template(tmp_path)
    sites, _, _ = bundle(tmp_path, descriptor)
    rule = load_yaml(CONFIG / "adsorbate_rules.yaml")["adsorbates"]["CO"]
    del rule["relative_cartesian_angstrom"]
    slab = read_poscar(SLAB)
    motif = {"site_pattern": "top", "binding_mode": "monodentate", "binding_atoms": ["C"],
             "reviewed_structure_template": descriptor}
    structure, mapping = builder.compose_candidate_structure(
        slab, builder.site_from_record(sites["sites"][0], slab), "CO", rule, motif,
    )
    assert np.allclose(adsorbate_vector(structure, mapping["adsorbate_indices_structure_0based"]), [0.7, 0.2, 1.1])


def test_template_parsing_uses_the_same_bytes_that_were_hashed(tmp_path, monkeypatch):
    descriptor = template(tmp_path)
    sites, _, _ = bundle(tmp_path, descriptor)
    parse = builder.parse_poscar_text

    def change_after_read(text, source):
        Path(descriptor["path"]).write_text("changed after reviewed bytes were read", encoding="utf-8")
        return parse(text, source)

    monkeypatch.setattr(builder, "parse_poscar_text", change_after_read)
    rule = load_yaml(CONFIG / "adsorbate_rules.yaml")["adsorbates"]["CO"]
    motif = {"site_pattern": "top", "binding_mode": "monodentate", "binding_atoms": ["C"],
             "reviewed_structure_template": descriptor}
    slab = read_poscar(SLAB)
    structure, mapping = builder.compose_candidate_structure(
        slab, builder.site_from_record(sites["sites"][0], slab), "CO", rule, motif,
    )
    assert np.allclose(adsorbate_vector(structure, mapping["adsorbate_indices_structure_0based"]), [0.7, 0.2, 1.1])
    assert mapping["geometry_source"]["sha256"] == descriptor["sha256"]
    assert sha256_file(Path(descriptor["path"])) != descriptor["sha256"]
