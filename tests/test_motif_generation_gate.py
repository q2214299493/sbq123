from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.adsmind_lite.core import detect_surface_sites, generate_candidates, read_json, write_json
from scripts.adsmind_lite.evidence_gate import resolve_external_evidence
from scripts.adsmind_lite.prescreen import load_prescreen_rules, plan_species
from scripts.artifact_io import sha256_file
from tests.evidence_fixtures import bound_evidence
from test_adsmind_lite import CONFIG, SLAB, write_site_plan


def bundle(tmp_path, species):
    sites = detect_surface_sites(SLAB, "Fe110", "metallic_fe", CONFIG / "surfaces.yaml", CONFIG / "site_rules.yaml")
    sites_path = tmp_path / "sites.json"
    write_json(sites_path, sites)
    plan_path = write_site_plan(tmp_path / "plan.json", species, sites)
    return sites_path, plan_path


def generate(tmp_path, species, sites_path, plan_path):
    return generate_candidates(
        SLAB, sites_path, species, CONFIG / "adsorbate_rules.yaml", tmp_path / "candidates", plan_path,
    )


def test_cached_ready_and_cached_policy_cannot_count_rotations_as_modes(tmp_path):
    sites, path = bundle(tmp_path, ["H2O"])
    plan = read_json(path)
    item = plan["species_plans"][0]
    base = item["candidates"][0]
    item["candidates"] = [
        {**base, "motif_id": f"rotation_{angle}", "configuration_id": str(angle), "orientation_degrees": angle}
        for angle in (0, 90, 180)
    ]
    item["initial_motif_coverage"] = {"status": "PASS", "distinct_count": 3, "required_count": 1}
    plan["policy"] = {"minimum_distinct_initial_motifs": 1}
    write_json(path, plan)
    with pytest.raises(ValueError, match=r"initial_motif_coverage 1/3 shortfall=2"):
        generate(tmp_path, ["H2O"], sites, path)
    assert not (tmp_path / "candidates").exists()


def test_entire_batch_is_checked_before_any_poscar_is_written(tmp_path):
    sites, path = bundle(tmp_path, ["C", "H2O"])
    plan = read_json(path)
    water = plan["species_plans"][1]
    water["candidates"] = water["candidates"][:1]
    write_json(path, plan)
    with pytest.raises(ValueError, match="H2O: initial_motif_coverage"):
        generate(tmp_path, ["C", "H2O"], sites, path)
    assert not (tmp_path / "candidates").exists()


def test_generation_cli_reports_shortfall_and_fails_without_structures(tmp_path):
    sites, path = bundle(tmp_path, ["H2O"])
    plan = read_json(path)
    plan["species_plans"][0]["candidates"] = plan["species_plans"][0]["candidates"][:1]
    write_json(path, plan)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.adsmind_lite.generate_adsorption_candidates",
         "--surface", str(SLAB), "--sites", str(sites), "--adsorbates", "H2O",
         "--plan", str(path), "--output", str(tmp_path / "candidates")],
        cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=False,
    )
    assert result.returncode == 1
    assert "initial_motif_coverage 1/3 shortfall=2" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "candidates").exists()


def test_simulated_site_migration_and_dedup_keep_original_mode_identity(tmp_path):
    from ase.io import read, write
    from scripts.adsmind_lite.core import analyze_relaxed_tree, deduplicate_records, load_yaml

    sites, path = bundle(tmp_path, ["C"])
    initial = generate(tmp_path, ["C"], sites, path)
    candidate_root = tmp_path / "candidates"
    relaxed_root = tmp_path / "relaxed"
    for item in initial:
        target = relaxed_root / Path(item["initial_structure"]).relative_to(candidate_root).with_name("CONTCAR")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(item["initial_structure"]).read_bytes())
    moved = relaxed_root / Path(initial[0]["initial_structure"]).relative_to(candidate_root).with_name("CONTCAR")
    atoms = read(moved, format="vasp")
    other = read(initial[1]["initial_structure"], format="vasp")
    atoms.positions[initial[0]["anchor_index_structure_0based"]] = other.positions[initial[1]["anchor_index_structure_0based"]]
    write(moved, atoms, format="vasp", direct=True, vasp5=True)
    analyzed = analyze_relaxed_tree(candidate_root, relaxed_root, sites, CONFIG / "analysis_rules.yaml")
    migrated = next(item for item in analyzed if item["candidate_id"] == initial[0]["candidate_id"])
    assert migrated["relaxed_site_class"] != migrated["initial_motif"]["site_pattern"]
    original = {item["candidate_id"]: item["initial_motif"] for item in initial}
    deduplicated = deduplicate_records(analyzed, load_yaml(CONFIG / "analysis_rules.yaml"))
    assert all(item["initial_motif"] == original[item["candidate_id"]] for item in deduplicated)
    assert len(deduplicated) == len(initial)


@pytest.mark.parametrize("damage", [
    "template_missing", "unsupported_site", "duplicate_configuration", "surface", "species", "evidence_blocked",
    "missing_motif_id", "invalid_motif_path", "invalid_orientation", "nonfinite_orientation",
])
def test_late_generation_blocker_cannot_leave_a_partial_batch(tmp_path, damage):
    sites, path = bundle(tmp_path, ["C"])
    plan = read_json(path)
    item = plan["species_plans"][0]
    if damage == "template_missing":
        item["candidates"][-1]["build_ready"] = False
    elif damage == "unsupported_site":
        item["candidates"][-1]["generator_site_class"] = "unsupported_reviewed_site"
    elif damage == "duplicate_configuration":
        item["candidates"].append(deepcopy(item["candidates"][0]))
    elif damage == "surface":
        item["surface"] = "Fe100"
    elif damage == "evidence_blocked":
        item["evidence_decision"] = "BLOCKED"
    elif damage == "missing_motif_id":
        last = item["candidates"][-1]
        last["configuration_id"] = last.pop("motif_id")
    elif damage == "invalid_motif_path":
        item["candidates"][-1]["motif_id"] = "../escape"
    elif damage == "invalid_orientation":
        item["candidates"][-1]["orientation_degrees"] = "not-a-number"
    elif damage == "nonfinite_orientation":
        item["candidates"][-1]["orientation_degrees"] = float("nan")
    else:
        item["species"] = "H2O"
    write_json(path, plan)
    with pytest.raises(ValueError):
        generate(tmp_path, ["C"], sites, path)
    assert not (tmp_path / "candidates").exists()


def test_declared_binding_modes_must_be_realized_by_the_actual_builder(tmp_path):
    sites, path = bundle(tmp_path, ["CO"])
    plan = read_json(path)
    item = plan["species_plans"][0]
    base = item["candidates"][0]
    item["candidates"] = [
        {**base, "motif_id": "C_end", "binding_atoms": ["C"]},
        {**base, "motif_id": "O_end", "binding_atoms": ["O"]},
        {**base, "motif_id": "CO_side_on", "binding_atoms": ["C", "O"], "binding_mode": "bidentate"},
    ]
    write_json(path, plan)
    with pytest.raises(ValueError, match="binding_mode_not_supported_by_generator"):
        generate(tmp_path, ["CO"], sites, path)
    assert not (tmp_path / "candidates").exists()


def external_plan(tmp_path):
    from scripts.adsmind_lite.adsmind_common import load_yaml

    template = tmp_path / "reviewed_template.vasp"
    template.write_bytes(SLAB.read_bytes())
    motifs = [
        {"motif_id": f"C_{site}", "site_pattern": site, "binding_mode": "monodentate", "binding_atoms": ["C"],
         "geometry_summary": "Synthetic reviewed initial motif", "stability_rank": index,
         "stability_evidence": "compared_relaxed_adsorption_energies",
         "reviewed_structure_template": {"path": str(template), "sha256": sha256_file(template)}}
        for index, site in enumerate(("top", "short_bridge", "long_bridge"), start=1)
    ]
    record = {
        "id": "synthetic-coverage", "record_id": "synthetic-coverage", "source_id": "catalysis-hub",
        "source_url": "https://api.catalysis-hub.org/graphql", "source_access_verified": True,
        "retrieved_at": "2026-09-09T00:00:00Z", "title": "Synthetic coverage fixture",
        "summary": "Synthetic reviewed source; no physical minimum claim", "data_types": ["structure"],
        "exact_surface_match": True, "exact_adsorbate_match": True, "stable_motifs": motifs,
    }
    record["evidence"] = bound_evidence(record, compatibility={"species": "C", "surface": "Fe110"})
    raw = resolve_external_evidence(
        {"species": "C", "surface": "Fe110", "whitelist": {"status": "MATCH", "records": [record]}},
        load_yaml(CONFIG / "evidence_gate.yaml"),
    )
    planned = plan_species("C", load_prescreen_rules(str(CONFIG / "prescreen_rules.yaml")), external_plans={"C": raw})
    return planned, template


def test_wrapped_external_plan_is_revalidated_and_preserves_initial_identity(tmp_path):
    sites, path = bundle(tmp_path, ["C"])
    planned, _ = external_plan(tmp_path)
    write_json(path, {"species_plans": [planned]})
    records = generate(tmp_path, ["C"], sites, path)
    assert len(records) == 3
    assert {item["initial_motif"]["site_pattern"] for item in records} == {
        "top_Fe", "bridge_FeFe_short", "bridge_FeFe_long",
    }
    assert all(read_json(Path(item["initial_structure"]).with_name("metadata.json"))["initial_motif"]
               == item["initial_motif"] for item in records)


@pytest.mark.parametrize("damage", ["template_changed", "candidate_changed", "unknown_field", "missing_payload"])
def test_external_cache_wrappers_cannot_bypass_bound_source_review(tmp_path, damage):
    sites, path = bundle(tmp_path, ["C"])
    planned, template = external_plan(tmp_path)
    if damage == "template_changed":
        template.write_bytes(template.read_bytes() + b"\n")
    elif damage == "candidate_changed":
        planned["candidates"][0]["binding_atoms"] = ["O"]
    elif damage == "unknown_field":
        planned["unreviewed_scientific_claim"] = True
    else:
        del planned["source_evidence_payload"]
    write_json(path, {"species_plans": [planned]})
    with pytest.raises(ValueError, match="external plan"):
        generate(tmp_path, ["C"], sites, path)
    assert not (tmp_path / "candidates").exists()
