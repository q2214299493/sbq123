"""Initial geometry/diversity contracts, without energy or stability claims."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from scripts.adsorption.build_fe110_adsorption import read_poscar, write_poscar
from scripts.adsmind_lite.adsmind_common import read_json, write_json
from scripts.artifact_io import sha256_file
from tests.test_multi_anchor_templates import multi_bundle
from tests.test_reviewed_template_generation import bundle, generate, template


def test_output_has_actual_distinct_sites_and_initial_geometry_evidence(tmp_path):
    _, sites_path, plan_path = bundle(tmp_path, template(tmp_path))
    records = generate(tmp_path, sites_path, plan_path)
    assert len(records) == 4
    actual = []
    for record in records:
        assert record["initial_geometry_validation"] == "PASS"
        assert record["scientific_stability"] == "NOT_ASSESSED"
        actual.append(record["observed_binding_site_classes"]["C"])
    assert set(actual) == {"top_Fe", "bridge_FeFe_short", "bridge_FeFe_long", "hollow_FeFeFe"}


def test_same_anchor_orientation_variants_are_not_emitted_as_extra_sites(tmp_path):
    _, sites_path, plan_path = bundle(tmp_path, template(tmp_path))
    plan = read_json(plan_path)
    motifs = plan["species_plans"][0]["candidates"]
    first = deepcopy(motifs[0])
    for angle in (30, 150):
        motifs.append({**first, "motif_id": f"same_site_{angle}", "orientation_degrees": angle})
    write_json(plan_path, plan)
    records = generate(tmp_path, sites_path, plan_path)
    assert len(records) == 4
    assert sum(len(record.get("omitted_same_site_variants", [])) for record in records) == 2
    assert len(list((tmp_path / "output").rglob("POSCAR"))) == 4


def test_site_manifest_cannot_relabel_one_actual_site_as_three_sites(tmp_path):
    _, sites_path, plan_path = bundle(tmp_path, template(tmp_path))
    sites = read_json(sites_path)
    primary = sites["sites"][0]
    for site in sites["sites"]:
        site["fractional_xy"] = primary["fractional_xy"]
        site["support_indices_1based"] = primary["support_indices_1based"]
    write_json(sites_path, sites)
    with pytest.raises(ValueError, match="initial_binding_site_not_realized"):
        generate(tmp_path, sites_path, plan_path)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("rename_anchors", [False, True])
def test_distinct_labels_cannot_pad_one_actual_multi_anchor_pose(tmp_path, rename_anchors):
    _, sites_path, plan_path = multi_bundle(tmp_path)
    plan = read_json(plan_path)
    base = plan["species_plans"][0]["candidates"][0]
    motifs = []
    for number in range(3):
        motif = {**deepcopy(base), "motif_id": f"claimed_mode_{number}", "site_pattern": f"claimed_pattern_{number}"}
        if rename_anchors:
            motif["binding_atoms"] = [f"C_label_{number}", f"O_label_{number}"]
            motif["binding_atom_indices_zero_based"] = dict(zip(motif["binding_atoms"], [0, 1]))
        motifs.append(motif)
    plan["species_plans"][0]["candidates"] = motifs
    write_json(plan_path, plan)
    with pytest.raises(ValueError, match="actual_initial_site_coverage 1/3"):
        generate(tmp_path, sites_path, plan_path)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("length", [0.1, 0.6, 3.0])
def test_bad_internal_geometry_blocks_batch_before_first_write(tmp_path, length):
    _, sites_path, plan_path = bundle(tmp_path, template(tmp_path))
    damaged = tmp_path / "bad-template"
    damaged.mkdir()
    descriptor = template(damaged, vector=(0.0, 0.0, length))
    plan = read_json(plan_path)
    plan["species_plans"][0]["candidates"][-1]["reviewed_structure_template"] = descriptor
    write_json(plan_path, plan)
    with pytest.raises(ValueError, match="adsorbate_fragmented|initial_bond|initial_adsorbate"):
        generate(tmp_path, sites_path, plan_path)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("damage", ["collision", "desorbed", "buried"])
def test_bad_multi_anchor_surface_geometry_blocks_entire_batch(tmp_path, damage):
    _, sites_path, plan_path = multi_bundle(tmp_path)
    plan = read_json(plan_path)
    descriptor = plan["species_plans"][0]["candidates"][-1]["reviewed_structure_template"]
    path = Path(descriptor["path"])
    pose = read_poscar(path)
    if damage == "collision":
        pose.frac[-1] = pose.frac[0] + np.array([0.0, 0.0, 0.001])
    elif damage == "desorbed":
        pose.frac[-1, 2] += 0.3
    else:
        pose.frac[-1, 2] = np.max(pose.frac[:-2, 2]) - 0.01
    write_poscar(path, pose)
    descriptor["sha256"] = sha256_file(path)
    write_json(plan_path, plan)
    with pytest.raises(ValueError, match="initial_surface|initial_secondary|initial_adsorbate"):
        generate(tmp_path, sites_path, plan_path)
    assert not (tmp_path / "output").exists()
