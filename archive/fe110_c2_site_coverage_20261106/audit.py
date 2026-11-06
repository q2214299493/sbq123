"""Reproduce a local, read-only stage/geometry audit; never accept or run jobs.

Run from the canonical work repository. Original manifests and cached VASP
sources are required. Nearest xy projections are NOT chemical binding labels.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.adsorption.build_fe110_adsorption import (
    expanded_symbols, fe110_anchor_site_distances, read_poscar,
)
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.workflow_geometry import pbc_xy_distance


ROOT = Path(__file__).resolve().parents[2]
SLAB = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
SEEDS = (
    "calculations/fe110_five_c2_adsorption_20261006/candidate_review.json",
    "calculations/fe110_c2_adsorption_06_10_20261012/candidates_v2/candidate_review.json",
    "calculations/fe110_c2_adsorption_11_15_20261020/candidates_v5/candidate_review.json",
    "calculations/fe110_c2_adsorption_16_19_20261101/review_ready_v2/candidate_review.json",
)
FINALS = (
    ("calculations/fe110_five_c2_adsorption_20261006/final_review_20261012/final_analysis.json", "records"),
    ("calculations/fe110_c2_adsorption_06_10_20261012/dedup_final_review_20261021_v1/review.json", "rows"),
    ("calculations/fe110_c2_adsorption_11_15_20261020/final_review_20261101_v1/analysis.json", "records"),
)


def resolve_source(value: str, manifest: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (ROOT if path.parts[0] == "calculations" else manifest.parent) / path


def describe(path: Path, slab) -> dict:
    pose = read_poscar(path)
    symbols = expanded_symbols(pose)
    assert symbols[:45] == ["Fe"] * 45 and symbols.count("Fe") == 45, path
    assert np.isfinite(pose.frac).all() and np.allclose(pose.cell, slab.cell, atol=1e-8, rtol=0), path
    ads = list(range(45, len(symbols)))
    edges = [(ads[a], ads[b]) for a, b in connectivity(pose, ads)]
    cart = pose.frac @ pose.cell
    heavy = []
    for index in ads:
        if symbols[index] == "H":
            continue
        neighbors = [b if a == index else a for a, b in edges if index in (a, b)]
        projections = fe110_anchor_site_distances(slab, pose.frac[index])
        nearest = sorted((pbc_xy_distance(pose.cell, cart[index], cart[fe]), fe) for fe in range(45))[:3]
        heavy.append({
            "atom_0based": index, "element": symbols[index],
            "bonded_H_count": sum(symbols[n] == "H" for n in neighbors),
            "nearest_xy_projection": min(projections, key=projections.get),
            "xy_projection_distances_A": projections,
            "nearest_Fe": [{"Fe_0based": fe, "distance_A": distance} for distance, fe in nearest],
        })
    return {
        "path": str(path.relative_to(ROOT)), "sha256": sha256_file(path),
        "heavy_atoms": heavy, "adsorbate_edges_0based": edges,
        "detached_H_0based": [i for i in ads if symbols[i] == "H" and not any(i in edge for edge in edges)],
        "fixed_flags_match_clean": pose.flags[:45] == slab.flags,
    }


def first_input_manifests():
    """Keep first submissions separate from later collected restart inputs."""
    base = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
    extra_groups = {"01_extra1": "vasp_supplement_v1", "02_extra2": "vasp_supplement_v1",
                    "03_extra1": "vasp_supplement_v1", "03_extra2_repair_v1": "vasp_repair_v1"}
    for item in load_json_object(ROOT / FINALS[0][0])["records"]:
        name = item["name"]
        yield base / extra_groups.get(name, "vasp_batch_v1") / name / "candidate_manifest.json"
    for species in range(6, 20):
        if species < 11:
            base = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/vasp_batch_v1"
        elif species < 16:
            base = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020/ft512_gpu_20261029_v1/dft80_v1"
        else:
            base = ROOT / "calculations/fe110_c2_adsorption_16_19_20261101/gpu_ft512_20261102_v1/dft300_v2"
        for letter in "ABC":
            yield base / f"{species:02d}_{letter}" / "candidate_manifest.json"


def audit() -> dict:
    slab = read_poscar(SLAB)
    clean_sha = sha256_file(SLAB)
    rows, manifests = [], []

    def add(name, stage, path, manifest, expected_sha=None, source_status=None):
        if expected_sha is not None and sha256_file(path) != expected_sha:
            raise ValueError(f"source hash mismatch: {path}")
        rows.append({"name": name, "stage": stage, "manifest": str(manifest.relative_to(ROOT)),
                     "source_status_not_reinterpreted": source_status, **describe(path, slab)})

    for value in SEEDS:
        manifest = ROOT / value
        data = load_json_object(manifest)
        assert data.get("slab_sha256", data.get("source_slab_sha256")) == clean_sha, manifest
        manifests.append(manifest)
        for item in data["candidates"]:
            name = item.get("name") or f"{item['species_id']}_cfg{item['config_id']}"
            add(name, "original_seed", resolve_source(item["structure"], manifest), manifest,
                item["structure_sha256"], item.get("status"))
    for suffix, key in (("supplement_v1/candidate_review.json", "candidates"),
                        ("supplement_repair_v1/repair_review.json", None)):
        manifest = ROOT / "calculations/fe110_five_c2_adsorption_20261006" / suffix
        data = load_json_object(manifest)
        manifests.append(manifest)
        for item in data[key] if key else [data]:
            path = resolve_source(item["structure_path"], manifest)
            add(item.get("name", path.parent.name), "supplement_seed", path, manifest,
                item["structure_sha256"], item.get("status"))
    for value, key in FINALS:
        manifest = ROOT / value
        data = load_json_object(manifest)
        manifests.append(manifest)
        for item in data[key]:
            # A collected POSCAR can belong to a continuation. It alone cannot
            # establish that a site change happened before the first DFT step.
            for stage, filename in (("collected_VASP_input", "POSCAR"), ("cached_DFT_output", "CONTCAR")):
                add(item["name"], stage, Path(item["directory"]) / filename, manifest)
    for manifest in first_input_manifests():
        data = load_json_object(manifest)
        manifests.append(manifest)
        expected = data.get("source_POSCAR_sha256", data.get("source_sha256"))
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"missing first-input source hash: {manifest}")
        add(manifest.parent.name, "first_DFT_input_source_hash_verified", manifest.parent / "POSCAR",
            manifest, expected, data["source_role"])
    manifest = ROOT / "calculations/fe110_c2_adsorption_16_19_20261101/gpu_ft512_20261102_v1/dft_submission_v1/submission_summary.json"
    manifests.append(manifest)
    return {
        "scope": "01-19 local stage coverage; no live scheduler check or new acceptance",
        "projection_caveat": "nearest xy site alone does not prove a bond, stable state or independent motif",
        "stage_counts": dict(Counter(row["stage"] for row in rows)),
        "slab": {"path": str(SLAB.relative_to(ROOT)), "sha256": clean_sha},
        "source_manifests": [{"path": str(p.relative_to(ROOT)), "sha256": sha256_file(p)} for p in manifests],
        "audit_source_sha256": sha256_file(Path(__file__)), "rows": rows,
        "scientific_acceptance": False, "execution_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    data = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(args.output, data)
    print(data["stage_counts"])
    print(f"Saved {args.output}; no jobs or scientific records changed.")


if __name__ == "__main__":
    main()
