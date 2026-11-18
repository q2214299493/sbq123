"""Public planner/generator handoff for reviewed local poses outside the catalog."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsmind_lite.candidate_generation import generate_candidates
from scripts.adsmind_lite.adsmind_common import read_json, write_json
from scripts.adsmind_lite.generation_validation import same_binding_mode
from scripts.adsmind_lite.relaxed_analysis import validate_candidates
from scripts.artifact_io import sha256_file
from tests.evidence_fixtures import bound_evidence
from tests.test_adsmind_lite import CONFIG, SLAB
from tests.test_multi_anchor_templates import multi_bundle


def reviewed_bundle(tmp_path, count=3):
    _, sites_path, old_plan = multi_bundle(tmp_path)
    motifs = read_json(old_plan)["species_plans"][0]["candidates"][:count]
    fields = (
        "motif_id", "site_pattern", "binding_mode", "binding_atoms", "generator_site_class",
        "binding_atom_indices_zero_based", "reviewed_structure_template",
    )
    data = {
        "species": "synthetic-reviewed",
        "surface": "Fe110",
        "slab_sha256": sha256_file(SLAB),
        "molecular_reference": {
            "atom_symbols": ["C", "O"], "relative_cartesian_angstrom": [[0, 0, 0], [0, 0, 1.15]],
        },
        "motifs": [{**{key: motif[key] for key in fields}, "geometry_origin": "local_construction"} for motif in motifs],
    }
    data["evidence"] = bound_evidence(
        data, kind="expert_opinion", scope="candidate_guidance",
        compatibility={key: data[key] for key in ("species", "surface", "slab_sha256")},
    )
    path = tmp_path / "reviewed.json"
    write_json(path, data)
    out = tmp_path / "plan.json"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.adsmind_lite.plan_adsorption_candidates",
         "--species", data["species"], "--reviewed-templates", str(path), "--output", str(out)],
        capture_output=True, text=True, check=True,
    )
    return data, sites_path, out, result.stdout


def test_reviewed_bundle_generates_without_catalog_entry(tmp_path):
    bundle, sites, plan, stdout = reviewed_bundle(tmp_path)
    assert "initial_motifs=3/3" in stdout
    out = tmp_path / "generated"
    records = generate_candidates(SLAB, sites, [bundle["species"]], CONFIG / "adsorbate_rules.yaml", out, plan)
    assert len(records) == 3
    assert {r["geometry_origin"] for r in records} == {"local_construction"}
    assert {r["reviewed_template_subject_sha256"] for r in records} == {bundle["evidence"]["review"]["subject_sha256"]}
    assert all(r["initial_geometry_validation"] == "PASS" and r["scientific_stability"] == "NOT_ASSESSED" for r in records)
    assert len(list(out.rglob("POSCAR"))) == 3
    result = validate_candidates(
        out, CONFIG / "surfaces.yaml", CONFIG / "adsorbate_rules.yaml", CONFIG / "analysis_rules.yaml", plan_path=plan,
    )
    assert len(result) == 3 and all(row["validation_passed"] for row in result)


def test_swapping_equivalent_diatomic_anchors_keeps_one_site_pair():
    slab = read_poscar(SLAB)
    first, second = slab.frac[41], slab.frac[43]
    pose = ({45: first, 46: second}, "top_Fe")
    swapped = ({45: second, 46: first}, "top_Fe")
    operations = [(np.eye(3), np.zeros(3))]
    assert same_binding_mode(pose, swapped, slab, operations, 0.1, interchangeable_pair=True)
    assert not same_binding_mode(pose, swapped, slab, operations, 0.1)


@pytest.mark.parametrize("change", ["slab", "mapping", "source", "file", "shortfall"])
def test_reviewed_bundle_cannot_be_rebound_or_written_partially(tmp_path, change):
    bundle, sites, path, _ = reviewed_bundle(tmp_path, count=2 if change == "shortfall" else 3)
    payload = read_json(path)
    plan = payload["species_plans"][0]
    slab = SLAB
    if change == "slab":
        slab = tmp_path / "same_geometry_changed_bytes.vasp"
        slab.write_bytes(b"changed header\n" + SLAB.read_bytes().split(b"\n", 1)[1])
    elif change == "mapping":
        plan["candidates"][0]["binding_atom_indices_zero_based"] = {"C": 1, "O": 0}
    elif change == "source":
        plan["reviewed_template_bundle"]["molecular_reference"]["relative_cartesian_angstrom"][1][2] = 1.18
    elif change == "file":
        Path(bundle["motifs"][-1]["reviewed_structure_template"]["path"]).write_text("changed", encoding="utf-8")
    write_json(path, payload)
    reason = {
        "slab": "slab SHA256 mismatch", "mapping": "differs from the source bundle",
        "source": "differs from the reviewed subject", "file": "reviewed_template_sha256_mismatch",
        "shortfall": "initial_motif_coverage 2/3",
    }[change]
    out = tmp_path / "generated"
    with pytest.raises(ValueError, match=reason):
        generate_candidates(slab, sites, [bundle["species"]], CONFIG / "adsorbate_rules.yaml", out, path)
    assert not out.exists()
