"""Synthetic pose contracts only; these are not physical adsorption minima."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import Poscar, read_poscar, write_poscar
from scripts.adsmind_lite import candidate_generation as builder
from scripts.adsmind_lite.adsmind_common import load_yaml, read_json, write_json
from scripts.adsmind_lite.motif_coverage import initial_motif_identity, review_initial_motif_coverage
from scripts.adsmind_lite.evidence_gate import resolve_external_evidence
from scripts.adsmind_lite.prescreen import load_prescreen_rules, plan_species
from scripts.adsmind_lite.relaxed_analysis import analyze_relaxed_candidate
from scripts.artifact_io import sha256_file
from tests.test_adsmind_lite import CONFIG, SLAB
from tests.test_reviewed_template_generation import bundle, generate, template
from tests.evidence_fixtures import bound_evidence


def full_template(tmp_path, site_record, *, symbols=("C", "O"), serial="pose"):
    slab = read_poscar(SLAB)
    # Deliberately unwrapped coordinates and a height unrelated to default rules.
    first = np.array([*site_record["fractional_xy"], max(slab.frac[:, 2]) + 0.12])
    first[0] += 1.0
    tail = np.array([first, first + np.array([0.7, 0.2, 0.3]) @ np.linalg.inv(slab.cell)])
    pose = Poscar("Synthetic full adsorption pose", slab.cell.copy(), [*slab.symbols, *dict.fromkeys(symbols)],
                  [*slab.counts, *[symbols.count(symbol) for symbol in dict.fromkeys(symbols)]],
                  np.vstack([slab.frac, tail]), [*slab.flags, ("T", "T", "T"), ("T", "T", "T")])
    path = tmp_path / f"{serial}.vasp"
    write_poscar(path, pose)
    return {"path": str(path), "sha256": sha256_file(path)}, tail


def multi_bundle(tmp_path):
    sites, sites_path, plan_path = bundle(tmp_path, template(tmp_path))
    plan = read_json(plan_path)
    for serial, motif in enumerate(plan["species_plans"][0]["candidates"]):
        site = next(site for site in sites["sites"] if site["site_class"] == motif["generator_site_class"])
        descriptor, _ = full_template(tmp_path, site, serial=str(serial))
        motif.update(binding_mode="bidentate", binding_atoms=["C", "O"], orientation_degrees=0.0,
                     binding_atom_indices_zero_based={"C": 0, "O": 1}, reviewed_structure_template=descriptor)
    write_json(plan_path, plan)
    return sites, sites_path, plan_path


def test_full_poses_preserve_all_coordinates_constraints_and_provenance(tmp_path):
    _, sites_path, plan_path = multi_bundle(tmp_path)
    records = generate(tmp_path, sites_path, plan_path)
    slab = read_poscar(SLAB)
    assert len(records) == 4
    for record in records:
        pose = read_poscar(Path(record["geometry_source"]["path"]))
        output = read_poscar(Path(record["initial_structure"]))
        assert np.allclose(output.frac[record["adsorbate_indices_structure_0based"]], pose.frac[-2:])
        assert np.array_equal(output.cell, slab.cell)
        assert output.flags[:sum(slab.counts)] == slab.flags
        assert np.array_equal(output.frac[:sum(slab.counts)], slab.frac)
        assert record["geometry_source"]["format"] == "slab_adsorbate_POSCAR"
        assert record["geometry_source"]["sha256"] == sha256_file(Path(record["geometry_source"]["path"]))
        assert record["binding_atom_indices_adsorbate_0based"] == {"C": 0, "O": 1}
        assert record["binding_atom_indices_structure_0based"] == dict(zip(["C", "O"], record["adsorbate_indices_structure_0based"]))
        assert record["initial_motif"]["binding_mode"] == "bidentate"
        assert record["needs_review"] is True
        assert record["confidence_level"] == "low"


def test_full_pose_constraint_flags_are_case_insensitive(tmp_path):
    _, sites_path, plan_path = multi_bundle(tmp_path)
    plan = read_json(plan_path)
    for motif in plan["species_plans"][0]["candidates"]:
        descriptor = motif["reviewed_structure_template"]
        path = Path(descriptor["path"])
        pose = read_poscar(path)
        pose.flags[:] = [tuple(value.lower() for value in flag) for flag in pose.flags]
        write_poscar(path, pose)
        descriptor["sha256"] = sha256_file(path)
    write_json(plan_path, plan)
    assert len(generate(tmp_path, sites_path, plan_path)) == 4


@pytest.mark.parametrize("damage", [
    "missing_map", "duplicate_map", "bool_map", "out_of_range", "wrong_labels", "missing_primary_site",
    "cell", "slab_coordinates", "slab_constraints", "adsorbate_constraints", "order", "rotation", "primary_site",
    "adsorbate_only", "hash", "missing_template", "invalid_primary",
])
def test_bad_late_multi_pose_blocks_whole_batch(tmp_path, damage):
    sites, sites_path, plan_path = multi_bundle(tmp_path)
    plan = read_json(plan_path)
    motif = plan["species_plans"][0]["candidates"][-1]
    descriptor = motif["reviewed_structure_template"]
    path = Path(descriptor["path"])
    if damage == "missing_map":
        del motif["binding_atom_indices_zero_based"]
    elif damage == "duplicate_map":
        motif["binding_atom_indices_zero_based"]["O"] = 0
    elif damage == "bool_map":
        motif["binding_atom_indices_zero_based"]["O"] = True
    elif damage == "out_of_range":
        motif["binding_atom_indices_zero_based"]["O"] = 2
    elif damage == "wrong_labels":
        motif["binding_atom_indices_zero_based"] = {"C1": 0, "C2": 1}
    elif damage == "invalid_primary":
        motif["binding_atom_indices_zero_based"] = {"C": 1, "O": 0}
    elif damage == "missing_primary_site":
        del motif["generator_site_class"]
    elif damage == "rotation":
        motif["orientation_degrees"] = 30.0
    elif damage == "primary_site":
        motif["generator_site_class"] = sites["sites"][0]["site_class"]
    elif damage == "adsorbate_only":
        motif["reviewed_structure_template"] = template(tmp_path)
    elif damage == "hash":
        descriptor["sha256"] = "0" * 64
    elif damage == "missing_template":
        del motif["reviewed_structure_template"]
    else:
        damage_pose(path, descriptor, damage)
    write_json(plan_path, plan)
    with pytest.raises(ValueError):
        generate(tmp_path, sites_path, plan_path)
    assert not (tmp_path / "output").exists()


def damage_pose(path, descriptor, damage):
    pose = read_poscar(path)
    if damage == "cell":
        pose.cell[0, 0] += 0.1
    elif damage == "slab_coordinates":
        pose.frac[0, 0] += 0.01
    elif damage == "slab_constraints":
        pose.flags[0] = ("T", "F", "F")
    elif damage == "adsorbate_constraints":
        pose.flags[-1] = ("F", "F", "F")
    elif damage == "order":
        pose.symbols[-2:] = ["O", "C"]
    write_poscar(path, pose)
    descriptor["sha256"] = sha256_file(path)


def test_repeated_elements_use_explicit_indices_even_with_midpoint_default(tmp_path):
    sites, _, _ = multi_bundle(tmp_path)
    site_record = sites["sites"][0]
    descriptor, tail = full_template(tmp_path, site_record, symbols=("C", "C"), serial="C2")
    rule = {"atom_symbols": ["C", "C"], "species_order": ["C"], "preferred_binding_atoms": ["C"],
            "anchor_mode": "midpoint", "anchor_index": None}
    motif = {"site_pattern": "h-lb-h", "generator_site_class": site_record["site_class"],
             "binding_mode": "di_sigma", "binding_atoms": ["C_beta", "C_alpha"],
             "binding_atom_indices_zero_based": {"C_alpha": 1, "C_beta": 0},
             "reviewed_structure_template": descriptor}
    slab = read_poscar(SLAB)
    output, mapping = builder.compose_candidate_structure(slab, builder.site_from_record(site_record, slab), "toy_C2", rule, motif)
    assert np.allclose(output.frac[mapping["adsorbate_indices_structure_0based"]], tail)
    assert mapping["anchor_index_adsorbate_0based"] == 0
    assert mapping["binding_atom_indices_adsorbate_0based"] == {"C_beta": 0, "C_alpha": 1}


def test_multi_site_coverage_keeps_full_pattern_and_ignores_azimuth():
    motif = {"motif_id": "one", "site_pattern": "h-lb-h", "generator_site_class": "hollow_FeFeFe",
             "binding_mode": "di_sigma", "binding_atoms": ["C1", "C2"]}
    other = {**motif, "motif_id": "two", "site_pattern": "diagonal_near_threefold"}
    assert initial_motif_identity(motif)["site_pattern"] == "h-lb-h"
    rules = {"policy": {"minimum_distinct_initial_motifs": 3}}
    plan = review_initial_motif_coverage({"decision": "READY", "candidates": [motif, other, {**motif, "orientation_degrees": 90}]}, rules)
    assert plan["initial_motif_coverage"]["distinct_count"] == 2
    assert plan["decision"] == "NEEDS_REVIEW"


def test_secondary_forbidden_binding_element_is_rejected(tmp_path):
    sites, _, plan_path = multi_bundle(tmp_path)
    motif = read_json(plan_path)["species_plans"][0]["candidates"][0]
    rule = load_yaml(CONFIG / "adsorbate_rules.yaml")["adsorbates"]["CO"]
    rule["forbidden_binding_atoms"] = ["O"]
    slab = read_poscar(SLAB)
    site = builder.site_from_record(sites["sites"][0], slab)
    with pytest.raises(ValueError, match="invalid_binding_atom"):
        builder.compose_candidate_structure(slab, site, "synthetic_forbidden_O", rule, motif)


def test_secondary_anchor_slip_is_detected_with_primary_unchanged(tmp_path):
    sites, sites_path, plan_path = multi_bundle(tmp_path)
    records = generate(tmp_path, sites_path, plan_path)
    metadata = deepcopy(next(record for record in records if record["planned_site_class"] == "top_Fe"))
    initial = read_poscar(Path(metadata["initial_structure"]))
    oxygen = metadata["binding_atom_indices_structure_0based"]["O"]
    initial.frac[oxygen, :2] = next(site["fractional_xy"] for site in sites["sites"] if site["site_class"] == "bridge_FeFe_short")
    write_poscar(Path(metadata["initial_structure"]), initial)
    analysis = load_yaml(CONFIG / "analysis_rules.yaml")
    unchanged = analyze_relaxed_candidate(metadata, Path(metadata["initial_structure"]), sites, analysis)
    assert unchanged["chemical_slip"] is False
    moved = deepcopy(initial)
    moved.frac[oxygen, :2] = next(site["fractional_xy"] for site in sites["sites"] if site["site_class"] == "bridge_FeFe_long")
    relaxed_path = tmp_path / "CONTCAR"
    write_poscar(relaxed_path, moved)
    result = analyze_relaxed_candidate(metadata, relaxed_path, sites, analysis)
    assert result["relaxed_site_class"] == "top_Fe"
    assert result["initial_binding_site_classes"] == {"C": "top_Fe", "O": "bridge_FeFe_short"}
    assert result["relaxed_binding_site_classes"] == {"C": "top_Fe", "O": "bridge_FeFe_long"}
    assert result["chemical_slip"] is True
    assert result["initial_motif"] == metadata["initial_motif"]
    assert result["recommend_for_vasp"] is False


def test_external_review_binds_multi_anchor_map_through_generation(tmp_path):
    _, sites_path, plan_path = multi_bundle(tmp_path)
    motifs = read_json(plan_path)["species_plans"][0]["candidates"]
    for rank, motif in enumerate(motifs, 1):
        motif.update(geometry_summary="Synthetic full pose; no physical minimum claim", stability_rank=rank,
                     stability_evidence="compared_relaxed_adsorption_energies")
    source = {"id": "full-pose-fixture", "record_id": "full-pose-fixture", "source_id": "catalysis-hub",
              "source_url": "https://api.catalysis-hub.org/graphql", "source_access_verified": True,
              "retrieved_at": "2026-09-09T00:00:00Z", "title": "Synthetic full-pose integration",
              "summary": "Toy template contract", "data_types": ["structure"], "exact_surface_match": True,
              "exact_adsorbate_match": True, "stable_motifs": motifs}
    source["evidence"] = bound_evidence(source, compatibility={"species": "CO", "surface": "Fe110"})
    external = resolve_external_evidence(
        {"species": "CO", "surface": "Fe110", "whitelist": {"status": "MATCH", "records": [source]}},
        load_yaml(CONFIG / "evidence_gate.yaml"),
    )
    planned = plan_species("CO", load_prescreen_rules(str(CONFIG / "prescreen_rules.yaml")), external_plans={"CO": external})
    write_json(plan_path, {"species_plans": [planned]})
    assert len(generate(tmp_path, sites_path, plan_path)) == 4
    planned["candidates"][-1]["binding_atom_indices_zero_based"] = {"C": 1, "O": 0}
    write_json(plan_path, {"species_plans": [planned]})
    with pytest.raises(ValueError, match="source|evidence|plan"):
        builder.generate_candidates(SLAB, sites_path, ["CO"], CONFIG / "adsorbate_rules.yaml",
                                    tmp_path / "tampered-output", plan_path)
    assert not (tmp_path / "tampered-output").exists()
