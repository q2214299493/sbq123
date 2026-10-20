"""Review the 15 starting geometries and repair unsupported linear CCO templates.

No calculator, prediction, energy, scheduler or scientific acceptance is used.
Angle ranges below are declared construction heuristics, not a physical theorem.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import itertools
import json
from pathlib import Path

import numpy as np

from scripts.adsorption.build_fe110_adsorption import Poscar, expanded_symbols, generate_sites, read_poscar, write_poscar
from scripts.adsorption.build_fe110_care_batch import display_coordinates, draw_pose, molecular_signature
from scripts.adsorption.build_fe110_care_isomers import (
    adsorbate_indices, connectivity, equivalent_pose_rmsd, review, rigid_reanchor_pose, surface_pose_symmetries,
)
from scripts.artifact_io import sha256_file, write_json


ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020"


def angle_degrees(first, center, last):
    a, b = first - center, last - center
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator < 1e-12:
        raise ValueError("zero length angle arm")
    return float(np.degrees(np.arccos(np.clip(np.dot(a, b) / denominator, -1., 1.))))


def rotation_between(first, second):
    first, second = first / np.linalg.norm(first), second / np.linalg.norm(second)
    vector = np.cross(first, second)
    sine, cosine = np.linalg.norm(vector), float(np.dot(first, second))
    if sine < 1e-10:
        if cosine > 0.:
            return np.eye(3)
        auxiliary = np.eye(3)[int(np.argmin(np.abs(first)))]
        axis = np.cross(first, auxiliary)
        axis /= np.linalg.norm(axis)
        return 2. * np.outer(axis, axis) - np.eye(3)
    x, y, z = vector
    skew = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
    return np.eye(3) + skew + skew @ skew * ((1. - cosine) / sine**2)


def bend_branch(pose, *, center, fixed, branch, target_angle_deg):
    """Rotate the entire O/OH branch about its bonded carbon; preserve all bond lengths."""
    if not 0. < target_angle_deg < 180.:
        raise ValueError("bend angle must be strictly between zero and 180 degrees")
    ads = adsorbate_indices(pose)
    edges = {(ads[a], ads[b]) for a, b in connectivity(pose, ads)}
    symbols = expanded_symbols(pose)
    if (center not in ads or fixed not in ads or branch not in ads
            or symbols[center] != "C" or symbols[fixed] == "H" or symbols[branch] == "H"
            or tuple(sorted((center, fixed))) not in edges or tuple(sorted((center, branch))) not in edges):
        raise ValueError("bend requires two actual heavy-atom bonds at a carbon")
    selected = {branch}
    pending = [branch]
    for current in pending:
        for a, b in edges:
            if current not in (a, b):
                continue
            other = b if current == a else a
            if other == center or other in selected:
                continue
            selected.add(other)
            pending.append(other)
    if fixed in selected:
        raise ValueError("the rotated branch reconnects to the fixed arm")
    cart = display_coordinates(pose)
    axis = cart[fixed] - cart[center]
    axis /= np.linalg.norm(axis)
    perpendicular = np.array([0., 0., 1.]) - axis * axis[2]
    if np.linalg.norm(perpendicular) < 1e-8:
        auxiliary = np.eye(3)[int(np.argmin(np.abs(axis)))]
        perpendicular = auxiliary - axis * np.dot(axis, auxiliary)
    perpendicular /= np.linalg.norm(perpendicular)
    angle = np.radians(target_angle_deg)
    desired = np.cos(angle) * axis + np.sin(angle) * perpendicular
    rotation = rotation_between(cart[branch] - cart[center], desired)
    fractional = pose.frac.copy()
    origin = pose.frac[center] @ pose.cell
    for index in selected:
        fractional[index] = (origin + rotation @ (cart[index] - cart[center])) @ np.linalg.inv(pose.cell)
        fractional[index, :2] %= 1.
    result = Poscar("Explicitly constructed bent CCO seed; not relaxed", pose.cell.copy(),
                    pose.symbols.copy(), pose.counts.copy(), fractional, pose.flags.copy())
    if molecular_signature(result) != molecular_signature(pose):
        raise ValueError("bending changed the molecular graph or hydrogen placement")
    return result


def metrics(pose, target, slab):
    """Compute contacts by explicit lattice-image enumeration, including adsorbate copies."""
    symbols = expanded_symbols(pose)
    ads = adsorbate_indices(pose)
    xyz = display_coordinates(pose)
    cell = pose.cell
    shifts = [np.array([x, y, 0.]) @ cell for x, y in itertools.product((-2, -1, 0, 1, 2), repeat=2)]
    cart = pose.frac @ cell

    def distance(a, b):
        return min(float(np.linalg.norm(cart[b] - cart[a] + shift)) for shift in shifts)

    edges = {(ads[a], ads[b]) for a, b in connectivity(pose, ads)}
    bonds = [{"atoms_1based": [a + 1, b + 1], "elements": [symbols[a], symbols[b]], "distance_A": distance(a, b)}
             for a, b in sorted(edges)]
    angles = []
    for center in ads:
        neighbors = [b if a == center else a for a, b in edges if center in (a, b)]
        for a, b in itertools.combinations(neighbors, 2):
            angles.append({"atoms_1based": [a + 1, center + 1, b + 1], "elements": [symbols[a], symbols[center], symbols[b]],
                           "angle_deg": angle_degrees(xyz[a], xyz[center], xyz[b])})
    nearest = [{"atom_1based": atom + 1, "element": symbols[atom],
                "neighbors": [{"Fe_1based": iron + 1, "distance_A": value}
                              for value, iron in sorted((distance(atom, iron), iron) for iron in range(45))[:3]]}
               for atom in ads]
    copy_contacts = []
    for x, y, z in itertools.product((-1, 0, 1), repeat=3):
        if (x, y, z) == (0, 0, 0):
            continue
        shift = np.array([x, y, z]) @ cell
        for a, b in itertools.product(ads, repeat=2):
            copy_contacts.append((float(np.linalg.norm(xyz[b] + shift - xyz[a])), a + 1, b + 1, x, y, z))
    opposite_shifts = np.array([[x, y, z] for x, y, z in itertools.product((-1, 0, 1), (-1, 0, 1), (-1, 1))]) @ cell
    opposite_deltas = cart[ads, None, None, :] - cart[None, :45, None, :] + opposite_shifts[None, None, :, :]
    opposite_slab_distance = float(np.linalg.norm(opposite_deltas, axis=3).min())
    nonbonded = [(distance(a, b), a + 1, b + 1)
                 for a, b in itertools.combinations(range(len(symbols)), 2)
                 if b >= 45 and (a, b) not in edges]
    bond_windows = {("C", "H"): (.95, 1.20), ("H", "O"): (.85, 1.10),
                    ("C", "C"): (1.20, 1.65), ("C", "O"): (1.15, 1.60)}
    bond_checks = [bond_windows[tuple(sorted(bond["elements"]))][0] <= bond["distance_A"] <= bond_windows[tuple(sorted(bond["elements"]))][1]
                   for bond in bonds]
    heavy_angles = [value for value in angles if "H" not in value["elements"]]
    angle_ok = all(95. <= value["angle_deg"] <= 140. for value in heavy_angles)
    terminal = next((index for index in ads if symbols[index] == "C"
                     and not any(symbols[b if a == index else a] == "H" for a, b in edges if index in (a, b))), None)
    contacts_ok = all(item["neighbors"][0]["distance_A"] >= (1.90 if item["element"] == "H" else 1.65) for item in nearest)
    carbon_items = [item for item in nearest if item["element"] == "C"]
    target_id = target["id"]
    if target_id in {"11", "14"}:
        anchored = terminal is not None and next(item for item in nearest if item["atom_1based"] == terminal + 1)["neighbors"][0]["distance_A"] <= 2.65
    elif target_id == "12":
        anchored = all(item["neighbors"][0]["distance_A"] <= 2.65 for item in nearest if item["element"] == "O" or item["atom_1based"] == terminal + 1)
    else:
        anchored = all(item["neighbors"][0]["distance_A"] <= 2.65 for item in carbon_items)
    checks = {
        "exact_graph_and_H_placement": molecular_signature(pose) == target["signature"],
        "finite_cell_and_coordinates": bool(np.isfinite(pose.cell).all() and np.isfinite(pose.frac).all()),
        "same_cell_and_all_Fe_coordinates": bool(np.array_equal(pose.cell, slab.cell) and np.array_equal(pose.frac[:45], slab.frac)),
        "same_Fe_flags_all_adsorbates_mobile": pose.flags[:45] == slab.flags and all(flag == ("T", "T", "T") for flag in pose.flags[45:]),
        "bond_length_construction_windows": all(bond_checks),
        "supported_non_linear_heavy_centers": angle_ok,
        "substituent_angles": all(95. <= value["angle_deg"] <= 135. for value in angles if "H" in value["elements"]),
        "no_short_Fe_contacts": contacts_ok,
        "required_binding_atoms_attached": anchored,
        "all_adsorbate_atoms_above_top_by_1p60A": bool(min(cart[index, 2] for index in ads) - max(cart[:45, 2]) >= 1.60),
        "nonbonded_contacts_at_least_1A": min(nonbonded)[0] >= 1.,
        "periodic_molecule_copies_above_2A": min(copy_contacts)[0] >= 2.,
        "no_opposite_slab_image_overlap": opposite_slab_distance >= 2.,
    }
    return {"checks": checks, "plausibility_status": "PASS" if all(checks.values()) else "NEEDS_REVIEW",
            "status_scope": "INITIAL_GEOMETRY_ONLY_NOT_RELAXED", "scientific_acceptance": False,
            "bonds": bonds, "angles": angles, "nearest_Fe": nearest,
            "minimum_nonbonded_contact": min(nonbonded), "minimum_periodic_copy_contact": min(copy_contacts),
            "opposite_slab_image_min_A": opposite_slab_distance,
            "remaining_z_vacuum_gap_A": float(cell[2, 2] - np.ptp(cart[:, 2])),
            "minimum_adsorbate_height_A": float(min(cart[index, 2] for index in ads) - max(cart[:45, 2]))}


def distinct_seed_pairs(poses, targets, slab):
    operations = surface_pose_symmetries(slab)
    pairs = []
    for species in targets:
        names = sorted(name for name in poses if name.startswith(species + "_"))
        for first, second in itertools.combinations(names, 2):
            candidates = [poses[second]]
            if species == "15":
                other = poses[second]
                coords = other.frac.copy()
                coords[[45, 46]] = coords[[46, 45]]
                candidates.append(Poscar(other.comment, other.cell, other.symbols, other.counts, coords, other.flags))
            distance = min(equivalent_pose_rmsd(poses[first], other, operations) for other in candidates)
            if distance <= .20:
                raise ValueError(f"near-duplicate corrected candidates: {first} {second}")
            pairs.append({"names": [first, second], "RMSD_A": distance})
    return pairs


def write_geometry_csv(path, records):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["name", "changed", "plausibility_status", "CCO_or_COC_angle_deg", "min_contact_A", "periodic_copy_min_A"])
        for row in records:
            geometry = row["geometry"]
            writer.writerow([row["name"], row["changed"], geometry["plausibility_status"],
                             [a["angle_deg"] for a in geometry["angles"] if "H" not in a["elements"]],
                             geometry["minimum_nonbonded_contact"][0], geometry["minimum_periodic_copy_contact"][0]])


def prepare(source, output, request_path, dry_run=False):
    if output.exists():
        raise FileExistsError("preserve all previous outputs; choose a new output directory")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    manifest_path = source / "candidate_review.json"
    if sha256_file(manifest_path) != request["source_manifest_sha256"]:
        raise ValueError("source manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original_request = json.loads((ROOT / request["original_request"]).read_text(encoding="utf-8"))
    targets = {item["id"]: item for item in original_request["targets"]}
    slab_path = ROOT / manifest["source_slab"]
    if sha256_file(slab_path) != manifest["source_slab_sha256"]:
        raise ValueError("accepted slab changed")
    slab = read_poscar(slab_path)
    sites, _ = generate_sites(slab)
    originals = {}
    baseline = []
    for row in manifest["candidates"]:
        path = source / row["structure"]
        if sha256_file(path) != row["structure_sha256"]:
            raise ValueError("source candidate changed")
        pose = read_poscar(path)
        originals[row["name"]] = (pose, row)
        baseline.append({"name": row["name"], **metrics(pose, targets[row["species_id"]], slab)})
    records, poses = [], {}
    for name, (parent, old) in originals.items():
        definition = request["corrections"].get(name)
        pose = parent
        if definition:
            template = bend_branch(parent, center=46, fixed=45 if old["species_id"] == "12" else 47,
                                   branch=47 if old["species_id"] == "12" else 45,
                                   target_angle_deg=definition["CCO_angle_deg"])
            placement = definition["placement"]
            pose = rigid_reanchor_pose(template, slab, sites[placement["site"]], anchor=46,
                                       axis_to=45 if old["species_id"] == "12" else 47,
                                       azimuth_deg=placement["azimuth_deg"], tilt_deg=placement["tilt_deg"],
                                       binding_distance_A=placement["binding_distance_A"])
            if review(parent, pose, adsorbate_indices(parent))["verdict"] != "pass":
                raise ValueError(f"bond/connectivity/contact geometry failure: {name}")
        result = metrics(pose, targets[old["species_id"]], slab)
        print(name, result["plausibility_status"], [key for key, value in result["checks"].items() if not value], flush=True)
        poses[name] = pose
        records.append({"name": name, "species_id": old["species_id"], "formula": old["formula"], "connectivity": old["connectivity"],
                        "source_path": str(source / old["structure"]), "source_sha256": old["structure_sha256"],
                        "changed": definition is not None, "recipe": definition, "geometry": result,
                        "previous_label": old.get("requested_label"), "predicted_energy_inherited": False})
    if dry_run:
        return records
    if any(item["geometry"]["plausibility_status"] != "PASS" for item in records):
        raise ValueError("not all 15 candidates pass the declared initial-geometry review")
    pairs = distinct_seed_pairs(poses, targets, slab)
    output.mkdir(parents=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for row in records:
        name = row["name"]
        path = output / name / "POSCAR"
        if row["changed"]:
            write_poscar(path, poses[name])
        else:
            path.parent.mkdir(parents=True)
            path.write_bytes(Path(row["source_path"]).read_bytes())
        row["structure"] = name + "/POSCAR"
        row["structure_sha256"] = sha256_file(path)
        row["unchanged_source_bytes"] = not row["changed"] and row["structure_sha256"] == row["source_sha256"]
    for species in targets:
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        for column, letter in enumerate("ABC"):
            name = species + "_" + letter
            draw_pose(axes[:, column], poses[name], slab, name)
        fig.suptitle(species + " " + targets[species]["connectivity"] + " | reviewed initial geometry, not relaxed\nFe gray / C black / O red / H blue; atom labels zero-based")
        fig.savefig(output / (species + "_structures.png"), dpi=140)
        plt.close(fig)
    write_json(output / "candidate_review.json", {"status": "PASS_INITIAL_GEOMETRY_REVIEW_ONLY", "scientific_acceptance": False,
               "relaxed": False, "gpu_ready": False, "submitted": False, "source_manifest_sha256": request["source_manifest_sha256"],
               "request_sha256": sha256_file(request_path), "slab_path": str(slab_path), "slab_sha256": sha256_file(slab_path),
               "builder_sha256": sha256_file(Path(__file__)), "candidates": records, "same_species_deduplication": pairs,
               "minimum_seed_RMSD_A": min(row["RMSD_A"] for row in pairs), "construction_assumptions": request["assumptions"]})
    write_json(output / "previous_version_chemical_audit.json", {"scope": "v3 initial geometries", "candidates": baseline,
               "summary": dict(Counter(row["plausibility_status"] for row in baseline))})
    write_geometry_csv(output / "geometry_summary.csv", records)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=TASK / "candidates_v3")
    parser.add_argument("--output", type=Path, default=TASK / "candidates_v5")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    prepare(args.source, args.output, args.request, args.dry_run)


if __name__ == "__main__":
    main()
