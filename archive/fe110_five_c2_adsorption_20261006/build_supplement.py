"""Build local-template variants and audit symmetry, chemistry and surface contacts."""
import json
from itertools import permutations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import spglib
import yaml

from scripts.artifact_io import sha256_file, write_json
from scripts.adsorption.build_fe110_adsorption import (
    Poscar, read_poscar, write_poscar, generate_sites, anchor_cartesian_position,
    expanded_symbols,
)
from scripts.adsorption.build_fe110_care_isomers import review
from scripts.workflow_geometry import minimum_image_delta_xy, pbc_xy_distance

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "supplement_v1"
PLAN = Path(__file__).with_name("supplement_plan.json")


def oriented_frame(axis):
    x = np.asarray(axis, dtype=float)
    x /= np.linalg.norm(x)
    z = np.array([0., 0., 1.]) - x * x[2]
    if np.linalg.norm(z) < 1e-8:
        z = np.array([1., 0., 0.]) - x * x[0]
    z /= np.linalg.norm(z)
    return np.column_stack((x, np.cross(z, x), z))


def surface_symmetries(slab):
    data = spglib.get_symmetry((slab.cell, slab.frac, [26]*45), symprec=0.01)
    assert data is not None
    operations = []
    for rotation, translation in zip(data["rotations"], data["translations"]):
        if np.array_equal(rotation[2], [0, 0, 1]) and np.array_equal(rotation[:, 2], [0, 0, 1]) and abs(translation[2] - round(translation[2])) < 1e-8:
            operations.append((rotation, translation))
    assert operations
    return operations


def equivalent_rmsd(first, second, operations):
    """Adsorbate comparison under actual slab symmetry; identical H may permute.

    Remove only uniform z height shift so height-only seeds cannot pad motif counts.
    No arbitrary adsorbate Kabsch rotation or lateral COM alignment is permitted.
    """
    symbols = expanded_symbols(first)[45:]
    assert symbols == expanded_symbols(second)[45:]
    hs = [i for i, s in enumerate(symbols) if s == "H"]
    best = float("inf")
    for rotation, translation in operations:
        mapped = second.frac[45:] @ rotation.T + translation
        for order in permutations(hs):
            indices = list(range(len(symbols)))
            for i, j in zip(hs, order):
                indices[i] = j
            delta = minimum_image_delta_xy(mapped[indices] - first.frac[45:]) @ first.cell
            delta[:, 2] -= delta[:, 2].mean()
            best = min(best, float(np.sqrt(np.mean(np.sum(delta**2, axis=1)))))
    return best


def make_variant(source, slab, sites, spec, distance):
    anchor = spec["anchor_global_0based"]
    relative = minimum_image_delta_xy(source.frac[45:] - source.frac[anchor]) @ source.cell
    old_axis = relative[spec["axis_to"]-45] - relative[spec["axis_from"]-45]
    azimuth, tilt = np.radians([spec["azimuth_deg"], spec["tilt_deg"]])
    new_axis = np.array([np.cos(tilt)*np.cos(azimuth), np.cos(tilt)*np.sin(azimuth), np.sin(tilt)])
    rotation = oriented_frame(new_axis) @ oriented_frame(old_axis).T
    assert np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-10)
    target = anchor_cartesian_position(slab, sites[spec["site"]], distance)
    adsorbate = relative @ rotation.T + target
    frac = np.vstack((slab.frac, adsorbate @ np.linalg.inv(slab.cell)))
    flags = [("F", "F", "F")]*18 + [("T", "T", "T")]*(len(frac)-18)
    return Poscar(spec["name"] + " intact local-template hypothesis", slab.cell.copy(), source.symbols.copy(), source.counts.copy(), frac, flags)


def draw_candidate(axes, structure, spec, geometry, slab):
    cart = structure.frac @ structure.cell
    ads = cart[45:]
    centre = ads[:, :2].mean(axis=0)
    colours = {"C":"#292929", "H":"#f4f4f4", "O":"#d13d3d"}
    sizes = {"C":130, "H":65, "O":120}
    symbols = expanded_symbols(structure)
    top_z = (slab.frac @ slab.cell)[:, 2].max()
    azimuth = np.radians(spec["azimuth_deg"])
    direction = np.array([np.cos(azimuth), np.sin(azimuth)])
    centre_u = float(centre @ direction)
    for ax, side in zip(axes, (False, True)):
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                irons = cart[:45] + i*slab.cell[0] + j*slab.cell[1]
                mask = np.linalg.norm(irons[:, :2]-centre, axis=1) < 3.6
                if not side:
                    mask &= irons[:, 2] > top_z - .8
                x = irons[mask, :2] @ direction if side else irons[mask, 0]
                y = irons[mask, 2] if side else irons[mask, 1]
                ax.scatter(x, y, s=200 if not side else 65, c="#a8aeb8", alpha=.55, edgecolors="#7a818d")
        for a, b in geometry["connectivity_edges_local_0based"]:
            pair = ads[[a,b]]
            ax.plot(pair[:,:2] @ direction if side else pair[:,0], pair[:,2] if side else pair[:,1], color="#484848", lw=2, zorder=4)
        for index, point in enumerate(ads, start=45):
            element = symbols[index]
            x = float(point[:2] @ direction) if side else point[0]
            y = point[2] if side else point[1]
            ax.scatter(x, y, c=colours[element], s=sizes[element], edgecolors="black", zorder=5)
            ax.annotate(f"{element}{index}", (x, y), xytext=(5,5), textcoords="offset points", fontsize=8)
        midpoint = centre_u if side else centre[0]
        ax.set_xlim(midpoint-3.4, midpoint+3.4)
        if side:
            ax.set_ylim(top_z-4.2, ads[:,2].max()+.6)
        else:
            ax.set_ylim(centre[1]-3.4, centre[1]+3.4)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(spec["name"] + (" side (chain-z)" if side else " top (x-y)"), fontsize=10)
        ax.set_xlabel("chain direction / A" if side else "x / A")
        ax.set_ylabel("z / A" if side else "y / A")


def main():
    if DEST.exists():
        raise FileExistsError("Preserve existing candidate bytes; use a reviewed new version")
    plan = json.loads(PLAN.read_text())
    original = json.loads((BASE / "candidate_review.json").read_text())
    gpu = json.loads((BASE / "gpu_return_review.json").read_text())
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    slab_path = ROOT / original["slab"]
    assert sha256_file(slab_path) == original["slab_sha256"]
    slab = read_poscar(slab_path)
    sites, _ = generate_sites(slab)
    symmetry = surface_symmetries(slab)
    sources = {(c["species_id"], c["config_id"]): c for c in original["candidates"]}
    comparison = [(c["species_id"], "original_cfg"+c["config_id"], read_poscar(ROOT / c["structure"])) for c in original["candidates"] if c["species_id"] in {"01","02","03"}]
    for item in gpu["records"]:
        if item["candidate"] in gpu["selected"] and item["candidate"][:2] in {"01","02","03"}:
            comparison.append((item["candidate"][:2], "GPU_"+item["candidate"], read_poscar(BASE / "gpu_batch_v4" / item["candidate"] / "output/job_2139/POSCAR")))
    candidates = []
    for spec in plan["candidates"]:
        metadata = sources[(spec["species_id"], spec["source_config"])]
        source_path = ROOT / metadata["structure"]
        assert sha256_file(source_path) == metadata["structure_sha256"]
        source = read_poscar(source_path)
        structure = make_variant(source, slab, sites, spec, spec.get("binding_distance_A", plan["binding_distance_A"]))
        geometry = review(source, structure, list(range(45, sum(source.counts))))
        assert geometry["verdict"] == "pass", (spec["name"], geometry)
        assert np.allclose(structure.frac[:45], slab.frac, atol=1e-12)
        distances = [(name, equivalent_rmsd(structure, other, symmetry)) for species, name, other in comparison if species == spec["species_id"]]
        closest = min(distances, key=lambda p: p[1])
        assert closest[1] > rules["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"], (spec["name"], closest)
        symbols, cart = expanded_symbols(structure), structure.frac @ structure.cell
        neighbours, bonds = [], []
        for index in range(45, len(cart)):
            nearest = sorted((pbc_xy_distance(structure.cell, cart[index], cart[i]), i) for i in range(45))[:3]
            neighbours.append({"atom": symbols[index]+str(index), "nearest_Fe": [{"index_0based":i, "distance_A":d} for d,i in nearest]})
        for a,b in geometry["connectivity_edges_local_0based"]:
            bonds.append({"atoms_0based":[a+45,b+45], "distance_A":pbc_xy_distance(structure.cell, cart[a+45], cart[b+45])})
        candidates.append((spec, structure, {**spec, "connectivity": metadata["connectivity"], "care_code": metadata["care_code"],
            "source_path": str(source_path), "source_sha256": sha256_file(source_path), "geometry": geometry,
            "bond_distances": bonds, "nearest_Fe": neighbours,
            "symmetry_comparison": {"operation_count":len(symmetry), "height_shift_removed":True, "closest":closest,
                                    "all_RMSD_A": dict(distances)}, "status":"GEOMETRY_PASS_REVIEW_REQUIRED_NOT_RELAXED"}))
        comparison.append((spec["species_id"], spec["name"], structure))
    DEST.mkdir()
    fig, axes = plt.subplots(len(candidates), 2, figsize=(10, 17), constrained_layout=True)
    records = []
    for row, (spec, structure, record) in enumerate(candidates):
        path = DEST / spec["name"] / "POSCAR"
        write_poscar(path, structure)
        record.update(structure_path=path.relative_to(ROOT).as_posix(), structure_sha256=sha256_file(path))
        records.append(record)
        draw_candidate(axes[row], structure, spec, record["geometry"], slab)
        print(spec["name"], "GEOMETRY_PASS", [(a["atom"],a["site"]) for a in record["geometry"]["atom_site_details"]], "closest_symmetry_RMSD", round(record["symmetry_comparison"]["closest"][1],3))
    fig.suptitle("Five supplemental intact adsorption candidates (not relaxed)\nFe110 / Fe45 / bottom Fe0-17 fixed; atom labels are zero-based", fontsize=12)
    fig.savefig(DEST / "structure_review.png", dpi=150)
    plt.close(fig)
    write_json(DEST / "candidate_review.json", {"plan_path":str(PLAN), "plan_sha256":sha256_file(PLAN),
        "slab_sha256":sha256_file(slab_path), "source_review_sha256":sha256_file(BASE / "candidate_review.json"),
        "candidates":records, "gpu_submitted":False, "vasp_submitted":False,
        "after_addition_candidate_counts":[3,3,3,3,3],
        "count_caution":"15 initial candidates, NOT15 distinct converged minima; relaxation may merge or dissociate.",
        "scientific_acceptance":False})


if __name__ == "__main__":
    main()
