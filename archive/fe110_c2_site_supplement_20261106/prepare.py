"""Prepare reviewed-local/exploratory supplemental POSCARs, never calculations."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

from archive.fe110_c2_site_coverage_20261106.audit import describe
from scripts.adsorption.build_fe110_adsorption import Poscar, expanded_symbols, generate_sites, read_poscar, write_poscar
from scripts.adsorption.build_fe110_care_batch import display_coordinates, molecular_signature, pose_measurements
from scripts.adsorption.build_fe110_care_isomers import (
    connectivity, equivalent_pose_rmsd, review, rigid_reanchor_pose, surface_pose_symmetries,
)
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.workflow_geometry import minimum_image_delta_xy


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "calculations/fe110_c2_site_supplement_20261106/review_v1"
SLAB = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
PRIOR = ROOT / "outputs/fe110_c2_site_coverage_20261106_final/evidence_checked.json"
PRIOR_SHA = "07cf68284879aaa2c4a31e3f30454ff7e53eb1e91f374e9eda7c510cda8cd6b9"
POLICY = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
GRAPHS = {
    "05": "[C]-[C]-OH", "06": "[C]-O-[CH]", "07": "[CH2]-[C]-[O]",
    "09": "[C]-O-[CH2]", "11": "[C]-CH3", "12": "CH3-[C]-[O]",
    "13": "[CH2]-[C]-OH", "14": "[C]-O-CH3", "18": "[CH]-O-CH3",
}
RESTORED = (
    ("05_S1", "05_cfg0", "shared_Fe_CC", "双C接近同一Fe，OH侧向；不是现有C-top/C-LB终点"),
    ("06_S1", "06_A", "shared_Fe_CC", "完整C-O-CH，双C接近同一Fe，O抬起"),
    ("09_S1", "09_B", "CC_near_long_bridges", "完整C-O-CH2，双C近长桥/O协同；不使用解离后的B"),
    ("11_S1", "11_A", "bare_C_hollow", "无H的C46空位；甲基C45不作为位点判据"),
    ("12_S1", "12_A", "C_top_O_near_long_bridge", "C46顶位单中心，O47近长桥；使用已审120度骨架"),
    ("13_S1", "13_A", "C_long_bridge_CH2_top", "C46长桥、CH2分支近顶位；不是续算转位后的A"),
    ("14_S1", "14_B", "bare_C_hollow", "无H的C46空位，保留C-O-CH3完整连接"),
)
CONSTRUCTED = (
    ("05_S2", "cached_DFT_output", "05_cfg0", 47, 46, "hollow", 210., 0., 2.25, None,
     "terminal_C_hollow_CC_multife", "末端C47空位，另一C参与多Fe配位，OH抬起"),
    ("06_S2", "original_seed", "06_C", 46, 47, "hollow", 60., 60., 2.25, None,
     "single_C_hollow_chain_lifted", "无H的C46空位主锚定，O/CH支路抬起"),
    ("07_S1", "cached_DFT_output", "07_B", 46, 47, "long_bridge", 180., 20., 2.25, None,
     "central_C_long_bridge_CO", "中央C46长桥、多Fe接触及O47协同，不沿用top-C起点"),
    ("18_S1", "original_seed", "18_A", 45, 47, "short_bridge", 120., 0., 2.30, (47, 45, -120.),
     "CH_C_short_bridge", "C45短桥；调整H-C-O-C二面角，保持键长/键角及H归属"),
    ("18_S2", "original_seed", "18_A", 45, 47, "long_bridge", 120., 0., 2.25, (47, 45, -120.),
     "CH_C_long_bridge", "C45长桥；调整H-C-O-C二面角，保持键长/键角及H归属"),
)
# Reference geometry is shown, not copied into new calculation folders or
# relabelled as a new relaxed result. Input and output references stay distinct.
REFERENCES = {
    "05": (("cached_DFT_output", "05_cfg0", "C_top_C_LB"),),
    "06": (("cached_DFT_output", "06_C", "multife_CCO"),),
    "07": (("first_DFT_input_source_hash_verified", "07_A", "CC_anchor_O_lifted"),
           ("first_DFT_input_source_hash_verified", "07_B", "lowcoord_C_O_anchor")),
    "09": (("first_DFT_input_source_hash_verified", "09_A", "CH2_hollow_C_SB"),
           ("first_DFT_input_source_hash_verified", "09_C", "CH2_top_C_LB")),
    "11": (("cached_DFT_output", "11_B", "C_LB"), ("cached_DFT_output", "11_C", "C_top")),
    "12": (("cached_DFT_output", "12_B", "highcoord_CO"), ("cached_DFT_output", "12_C", "CO_bridge_family")),
    "13": (("cached_DFT_output", "13_B", "C_SB"), ("cached_DFT_output", "13_C", "C_top")),
    "14": (("cached_DFT_output", "14_B", "C_LB"), ("cached_DFT_output", "14_C", "C_top")),
    "18": (("original_seed", "18_A", "C_top_seed_not_DFT_minimum"),),
}


def twist_branch(pose: Poscar, parent: int, child: int, angle: float) -> Poscar:
    """Rotate one graph component about a cut bond; no bond stretching or H swap."""
    ads = list(range(45, len(expanded_symbols(pose))))
    edges = [(ads[a], ads[b]) for a, b in connectivity(pose, ads)]
    if tuple(sorted((parent, child))) not in {tuple(sorted(e)) for e in edges}:
        raise ValueError("torsion axis is not a source bond")
    group = [child]
    for current in group:
        for a, b in edges:
            if {a, b} == {parent, child} or current not in (a, b):
                continue
            other = b if a == current else a
            if other not in group:
                group.append(other)
    if parent in group:
        raise ValueError("cut bond belongs to a ring")
    cart = display_coordinates(pose)
    axis = cart[child] - cart[parent]
    axis /= np.linalg.norm(axis)
    x, y, z = axis
    cross = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
    theta = np.radians(angle)
    rotation = np.eye(3) * np.cos(theta) + (1 - np.cos(theta)) * np.outer(axis, axis) + np.sin(theta) * cross
    frac = pose.frac.copy()
    frac[group] = ((cart[group] - cart[parent]) @ rotation.T + pose.frac[parent] @ pose.cell) @ np.linalg.inv(pose.cell)
    frac[group, :2] %= 1.
    return Poscar(pose.comment, pose.cell.copy(), pose.symbols.copy(), pose.counts.copy(), frac, pose.flags.copy())


def saved_rows() -> dict:
    if sha256_file(PRIOR) != PRIOR_SHA:
        raise ValueError("prior source bindings changed")
    data = load_json_object(PRIOR)
    rows = {(r["stage"], r["name"]): r for r in data["rows"]}
    return rows


def source_pose(rows, stage, name):
    row = rows[stage, name]
    path = ROOT / row["path"]
    if sha256_file(path) != row["sha256"]:
        raise ValueError(f"source structure changed: {path}")
    return read_poscar(path), path


def geometry(source, pose, slab) -> dict:
    ads = list(range(45, len(expanded_symbols(source))))
    result = review(source, pose, ads)
    if result["verdict"] != "pass" or molecular_signature(source) != molecular_signature(pose):
        raise ValueError(f"invalid candidate geometry: {result['checks']}")
    np.testing.assert_allclose(pose.frac[:45], slab.frac, atol=1e-12, rtol=0)
    np.testing.assert_allclose(pose.cell, slab.cell, atol=1e-12, rtol=0)
    if pose.flags[:45] != slab.flags:
        raise ValueError("clean-slab mask changed")
    distances = np.linalg.norm(minimum_image_delta_xy(pose.frac[:, None] - pose.frac[None, :]) @ pose.cell, axis=2)
    edges = {(ads[a], ads[b]) for a, b in connectivity(pose, ads)}
    minimum = min(distances[a, b] for a in range(len(pose.frac)) for b in range(a + 1, len(pose.frac)) if (a, b) not in edges)
    rules = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    if minimum < rules["contact_validation"]["hard_contact_distance_angstrom"]:
        raise ValueError("emergency nonbonded overlap")
    return {**result, "minimum_contact_excluding_adsorbate_bonds_A": float(minimum), **pose_measurements(pose)}


def candidates():
    rows, slab = saved_rows(), read_poscar(SLAB)
    sites, _ = generate_sites(slab)
    poses, records = {}, []

    def add(name, source, path, pose, family, note, recipe, copied):
        poses[name] = pose
        records.append({"name": name, "species_number": name[:2], "target_graph": GRAPHS[name[:2]],
            "source_path": str(path), "source_sha256": sha256_file(path), "source_role": recipe["source_stage"],
            "construction": recipe, "byte_exact_recovery": copied, "proposed_binding_family": family, "note_zh": note,
            "geometry": geometry(source, pose, slab), "energy_eV": None, "relaxed": False,
            "submitted": False, "scientific_acceptance": False})

    for name, old, family, note in RESTORED:
        source, path = source_pose(rows, "original_seed", old)
        add(name, source, path, source, family, note, {"type": "recover_original_complete_seed",
            "source_stage": "original_seed", "source_name": old, "coordinate_changes": False}, True)
    for name, stage, old, anchor, axis, site, azimuth, tilt, distance, torsion, family, note in CONSTRUCTED:
        source, path = source_pose(rows, stage, old)
        pose = rigid_reanchor_pose(source, slab, sites[site], anchor=anchor, axis_to=axis,
            azimuth_deg=azimuth, tilt_deg=tilt, binding_distance_A=distance)
        if torsion is not None:
            pose = twist_branch(pose, *torsion)
        add(name, source, path, pose, family, note, {"type": "local_template_exploratory_reanchor",
            "source_stage": stage, "source_name": old, "primary_atom_0based": anchor, "site": site,
            "axis_to_0based": axis, "azimuth_deg": azimuth, "tilt_deg": tilt,
            "initial_nearest_primary_Fe_A": distance, "torsion_parent_child_angle": torsion,
            "coordinate_changes": True, "source_Fe_positions_copied": False}, False)
    return slab, rows, poses, sorted(records, key=lambda r: r["name"])


def comparisons(slab, rows, poses, records):
    operations = surface_pose_symmetries(slab)
    tolerance = yaml.safe_load(POLICY.read_text(encoding="utf-8"))["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"]
    references, pairs = {}, []
    for species, refs in REFERENCES.items():
        group = [(r["name"], poses[r["name"]], True) for r in records if r["species_number"] == species]
        references[species] = []
        for stage, name, family in refs:
            pose, path = source_pose(rows, stage, name)
            references[species].append({"name": name, "stage": stage, "family": family,
                "path": str(path), "sha256": sha256_file(path)})
            group.append((f"reference:{name}", pose, False))
        for i, (first, a, is_new) in enumerate(group):
            for second, b, other_new in group[i + 1:]:
                distance = equivalent_pose_rmsd(a, b, operations, remove_height_shift=True)
                pairs.append({"species": species, "first": first, "second": second,
                    "seed_only_RMSD_without_height_padding_A": distance})
                if (is_new or other_new) and distance <= tolerance:
                    raise ValueError(f"candidate duplicates an existing pose: {first}/{second}")
    return references, pairs


def prepare(dry_run=False):
    slab, rows, poses, records = candidates()
    references, pairs = comparisons(slab, rows, poses, records)
    if dry_run:
        for record in records:
            print(record["name"], record["proposed_binding_family"], record["geometry"]["verdict"], record["geometry"]["warnings"])
        print("DRY_RUN_ONLY", len(records), "new candidates", len(pairs), "seed-only comparisons")
        return
    OUT.mkdir(parents=True, exist_ok=False)
    paths = [PRIOR, SLAB, POLICY, Path(__file__), ROOT / "AGENTS.md",
             ROOT / "scripts/adsorption/build_fe110_adsorption.py",
             ROOT / "scripts/adsorption/build_fe110_care_isomers.py",
             ROOT / "scripts/adsorption/build_fe110_care_batch.py"]
    cached_retrieval = [
        ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/retrieval/whitelist_search.json",
        ROOT / "calculations/fe110_c2_adsorption_11_15_20261020/retrieval/whitelist_search.json",
        ROOT / "calculations/fe110_c2_adsorption_16_19_20261101/whitelist_screen.json",
    ]
    paths.extend(cached_retrieval)
    for record in records:
        folder = OUT / record["name"]
        folder.mkdir()
        target = folder / "POSCAR"
        if record["byte_exact_recovery"]:
            with target.open("xb") as handle:
                handle.write(Path(record["source_path"]).read_bytes())
        else:
            write_poscar(target, poses[record["name"]])
        record.update({"structure": str(target), "structure_sha256": sha256_file(target),
                       "saved_geometry": describe(target, slab)})
        paths.append(Path(record["source_path"]))
    manifest = {"status": "PREPARED_FOR_USER_STRUCTURE_REVIEW_ONLY", "candidate_count": len(records),
        "candidate_counts": dict(Counter(r["species_number"] for r in records)), "candidates": records,
        "reference_structures_not_new_jobs": references, "seed_only_comparisons": pairs,
        "slab_sha256": sha256_file(SLAB), "source_files": source_file_manifest(list(dict.fromkeys(paths))),
        "execution": {"GPU": 0, "VASP": 0}, "submitted": False, "gpu_ready": False,
        "stable_top_three_claim": False, "scientific_acceptance": False, "source_energies_imported": False,
        "source_basis": "Verified local structures; no new external structure, energy or literature-stability claim.",
        "retrieval_context": {"mode": "verified_local_sources_first; prior bounded screens reused as context only",
            "fresh_external_retrieval": False, "external_records_ingested": 0,
            "cached_whitelist_screens": source_file_manifest(cached_retrieval)},
        "coverage_caveat": "Three proposed core modes include existing references; no claim of three distinct relaxed minima.",
        "excluded_original_variants": [{"name": "06_B", "reason": "same shared-Fe double-C core family as06_A; different pose is retained at its original source, not padded as another new site"},
                                       {"name": "12_B", "reason": "reserved; priority is original12_A missing single-C top mode"}]}
    write_json_exclusive(OUT / "candidate_review.json", manifest)
    print("PREPARED", len(records), "POSCARs; no model or VASP run")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    prepare(args.dry_run)
