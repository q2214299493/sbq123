"""Prepare a reviewed-input CARE/exploratory batch; never runs models or submits.

Existing site, transfer and geometry owners are reused. A local prediction or
constructed pose is not a literature-stable motif, relaxed state, or GPU gate.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import itertools
import json
from pathlib import Path

import numpy as np
import yaml

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json
from scripts.runtime_resources import resource_path
from scripts.workflow_geometry import minimum_image_delta_xy, pbc_xy_distance
from .build_fe110_adsorption import Poscar, expanded_symbols, generate_sites, read_poscar, write_poscar
from .build_fe110_care_isomers import (
    ASCII_SITE_LABEL, adsorbate_indices, care_source_pose, connectivity,
    equivalent_pose_rmsd, review, rigid_reanchor_pose, surface_pose_symmetries,
    transfer_pose,
)


def molecular_signature(structure: Poscar) -> list:
    """Check C2 H placement and heavy-atom neighbors, not formula alone."""
    indices = adsorbate_indices(structure)
    symbols = [expanded_symbols(structure)[i] for i in indices]
    edges = connectivity(structure, indices)
    signature = []
    for index, symbol in enumerate(symbols):
        neighbors = [symbols[b if a == index else a] for a, b in edges if index in (a, b)]
        if symbol == "H":
            if len(neighbors) != 1 or neighbors[0] == "H":
                raise ValueError("hydrogen is detached or multiply connected in the candidate")
        else:
            signature.append([symbol, neighbors.count("H"), sorted(s for s in neighbors if s != "H")])
    return sorted(signature)


def pose_measurements(structure: Poscar) -> dict:
    symbols = expanded_symbols(structure)
    cart = structure.frac @ structure.cell
    ads = adsorbate_indices(structure)
    bonds = [
        {"atoms_0based": [ads[a], ads[b]], "pair": symbols[ads[a]] + "-" + symbols[ads[b]],
         "distance_A": pbc_xy_distance(structure.cell, cart[ads[a]], cart[ads[b]])}
        for a, b in connectivity(structure, ads)
    ]
    nearest = [
        {"atom": symbols[index] + str(index), "neighbors": [
            {"Fe_index_0based": iron, "distance_A": distance}
            for distance, iron in sorted(
                (pbc_xy_distance(structure.cell, cart[index], cart[iron]), iron) for iron in range(45)
            )[:3]
        ]} for index in ads
    ]
    return {"bond_distances": bonds, "nearest_Fe": nearest}


def construct_extra(source, slab, sites, operations, kept, target, tolerance):
    """Bounded deterministic exploration, only for the explicitly authorized fallback."""
    symbols = expanded_symbols(source)
    ads = adsorbate_indices(source)
    edges = connectivity(source, ads)
    anchors = []
    for index in ads:
        local = ads.index(index)
        neighbors = [ads[b if a == local else a] for a, b in edges if local in (a, b)]
        if symbols[index] == "C" and sum(symbols[j] == "H" for j in neighbors) == target["anchor_H_count"]:
            anchors.append((index, next(j for j in neighbors if symbols[j] != "H")))
    if len(anchors) != 1:
        raise ValueError("fallback needs an unambiguous graph-defined carbon anchor")
    anchor, axis_to = anchors[0]
    attempts = 0
    warned_candidate = None
    for site_name in target["fallback_sites"]:
        for tilt, azimuth, distance in itertools.product((0., 20., 40., 60.), (0., 45., 90., 135.), (2.05, 2.15, 2.25)):
            attempts += 1
            structure = rigid_reanchor_pose(
                source, slab, sites[site_name], anchor=anchor, axis_to=axis_to,
                azimuth_deg=azimuth, tilt_deg=tilt, binding_distance_A=distance,
            )
            geometry = review(source, structure, ads)
            if geometry["verdict"] != "pass" or molecular_signature(structure) != target["signature"]:
                continue
            scores = [equivalent_pose_rmsd(structure, pose, operations) for pose, _ in kept]
            if min(scores) <= tolerance:
                continue
            result = (structure, {
                "origin": "USER_AUTHORIZED_RIGID_REANCHOR_HYPOTHESIS", "parent": kept[0][1]["source_config"],
                "recipe": {"site": site_name, "anchor_0based": anchor, "axis_to_0based": axis_to,
                           "azimuth_deg": azimuth, "tilt_deg": tilt, "binding_distance_A": distance},
                "attempts": attempts, "source_config": None, "geometry_review": geometry,
                "minimum_seed_RMSD_A": min(scores), "CARE_mu_source_order_only_eV": None,
            })
            if not geometry["warnings"]:
                return result
            # Warnings rank constructed seeds; they are not a new hard gate.
            if warned_candidate is None or len(geometry["warnings"]) < len(warned_candidate[1]["geometry_review"]["warnings"]):
                warned_candidate = result
    if warned_candidate is not None:
        return warned_candidate
    raise ValueError(f"no safe nonduplicate fallback for {target['id']}; do not pad the batch")


def display_coordinates(pose: Poscar) -> np.ndarray:
    """Unwrap bonded adsorbates for plots without splitting a long branch at PBC."""
    ads_indices = adsorbate_indices(pose)
    anchor = pose.frac[ads_indices[0]]
    cart = minimum_image_delta_xy(pose.frac - anchor) @ pose.cell
    edges = connectivity(pose, ads_indices)
    visited = {0}
    pending = [0]
    for current in pending:
        for first, second in edges:
            if current not in (first, second):
                continue
            neighbor = second if current == first else first
            if neighbor in visited:
                continue
            a, b = ads_indices[current], ads_indices[neighbor]
            cart[b] = cart[a] + minimum_image_delta_xy(pose.frac[b] - pose.frac[a]) @ pose.cell
            visited.add(neighbor)
            pending.append(neighbor)
    if len(visited) != len(ads_indices):
        raise ValueError("cannot draw a disconnected adsorbate as one molecule")
    return cart


def draw_pose(axes, pose: Poscar, slab: Poscar, name: str):
    symbols = expanded_symbols(pose)
    ads_indices = adsorbate_indices(pose)
    cart = display_coordinates(pose)
    top_z = float(np.max(cart[:45, 2]))
    colors = {"C": "#222222", "O": "#d93737", "H": "#38bdf8"}
    heavy = [i for i in ads_indices if symbols[i] != "H"]
    direction = cart[heavy[-1], :2] - cart[heavy[0], :2]
    direction = direction / np.linalg.norm(direction) if np.linalg.norm(direction) > 1e-8 else np.array([1., 0.])
    for ax, side in zip(axes, (False, True), strict=True):
        irons = list(range(45)) if side else [i for i in range(45) if cart[i, 2] > top_z - .5]
        x = cart[irons, :2] @ direction if side else cart[irons, 0]
        y = cart[irons, 2] if side else cart[irons, 1]
        ax.scatter(x, y, c="#9ca3af", s=85 if side else 180, alpha=.7, edgecolors="white")
        for a, b in connectivity(pose, ads_indices):
            pair = cart[[ads_indices[a], ads_indices[b]]]
            ax.plot(pair[:, :2] @ direction if side else pair[:, 0], pair[:, 2] if side else pair[:, 1], c="#505050", lw=2)
        for index in ads_indices:
            x = float(cart[index, :2] @ direction) if side else cart[index, 0]
            y = cart[index, 2] if side else cart[index, 1]
            ax.scatter(x, y, c=colors[symbols[index]], s=70 if symbols[index] == "H" else 125, edgecolors="white", zorder=5)
            ax.annotate(symbols[index] + str(index), (x, y), xytext=(5, 5), textcoords="offset points", fontsize=8)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(-3.5, 3.5)
        ax.set_ylim((top_z - 4.1, float(cart[ads_indices, 2].max()) + .7) if side else (-3.5, 3.5))
        ax.set_title(name + (" side" if side else " top"), fontsize=10)
        ax.set_xlabel("chain direction / A" if side else "x / A")
        ax.set_ylabel("z / A" if side else "y / A")


def requested_seeds(target, originals, slab, sites, operations, tolerance):
    """Build explicitly requested review seeds; never infer a stable motif or pad failures."""
    recipes = target["seed_recipes"]
    if len(recipes) != 3:
        raise ValueError("an explicit seed plan must contain exactly three recipes")
    parents = {config: (pose, metadata) for _, config, _, pose, metadata, _ in originals}
    kept = []
    for recipe in recipes:
        config = str(recipe["source_config"])
        if config not in parents:
            raise ValueError(f"missing requested source configuration: {config}")
        parent, parent_metadata = parents[config]
        pose = parent
        metadata = dict(parent_metadata)
        placement = recipe.get("placement")
        if placement is not None:
            ads = adsorbate_indices(parent)
            first, second = placement["anchor_local_0based"], placement["axis_to_local_0based"]
            symbols = expanded_symbols(parent)
            edges = connectivity(parent, ads)
            if (not isinstance(first, int) or not isinstance(second, int)
                    or not 0 <= first < len(ads) or not 0 <= second < len(ads)
                    or symbols[ads[first]] == "H" or symbols[ads[second]] == "H"
                    or tuple(sorted((first, second))) not in edges):
                raise ValueError("requested anchor axis must join two bonded heavy atoms")
            hydrogen_neighbors = sum(
                symbols[ads[b if a == first else a]] == "H"
                for a, b in edges if first in (a, b)
            )
            if hydrogen_neighbors != placement["anchor_H_count"]:
                raise ValueError("requested anchor hydrogen count does not match the exact graph")
            pose = rigid_reanchor_pose(
                parent, slab, sites[placement["site"]], anchor=ads[first], axis_to=ads[second],
                azimuth_deg=placement["azimuth_deg"], tilt_deg=placement["tilt_deg"],
                binding_distance_A=placement["binding_distance_A"],
            )
            metadata = {
                "origin": "USER_AUTHORIZED_RIGID_REANCHOR_HYPOTHESIS", "parent": config,
                "source_config": None, "recipe": placement,
                "CARE_mu_source_order_only_eV": None,
            }
        geometry = review(parent, pose, adsorbate_indices(parent))
        if geometry["verdict"] != "pass" or molecular_signature(pose) != target["signature"]:
            raise ValueError(f"requested seed failed geometry/identity: {target['id']} {recipe['label']}: {geometry['checks']}")
        scores = [equivalent_pose_rmsd(pose, other, operations) for other, _ in kept]
        if scores and min(scores) <= tolerance:
            raise ValueError(f"requested seed is a near duplicate: {target['id']} {recipe['label']}")
        metadata.update({
            "geometry_review": geometry, "requested_label": recipe["label"],
            "selection_basis": recipe["selection_basis"],
            "minimum_seed_RMSD_A": min(scores) if scores else None,
        })
        kept.append((pose, metadata))
    return kept


def prepare_group(target, network, slab, sites, operations, tolerance):
    matches = [v for k, v in network["species_registry"].items() if k.split("-", 1)[0] == target["care_prefix"] and v["phase"] == "ads"]
    if len(matches) != 1:
        raise ValueError(f"ambiguous or missing exact CARE identity: {target['id']}")
    species = matches[0]
    kept, excluded, originals = [], [], []
    for config, raw in sorted(species["ads_configs"].items(), key=lambda item: (float(item[1]["mu"]), item[0])):
        if not np.isfinite(float(raw["mu"])):
            raise ValueError("nonfinite source-only prediction")
        source, source_order = care_source_pose(raw)
        pose, source_ads = transfer_pose(source, slab)
        if molecular_signature(source) != target["signature"] or molecular_signature(pose) != target["signature"]:
            raise ValueError(f"formula-only substitution or source chemistry mismatch: {target['id']} cfg{config}")
        geometry = review(source, pose, source_ads)
        metadata = {"source_config": config, "origin": "LOCAL_CARE_POSE_TRANSFER",
                    "CARE_mu_source_order_only_eV": float(raw["mu"]), "CARE_grouping_permutation": source_order,
                    "geometry_review": geometry}
        originals.append((target, config, source, pose, metadata, species["molecule"]))
        if geometry["verdict"] != "pass":
            excluded.append({"config": config, "reason": "geometry_review_failed"})
            continue
        scores = [equivalent_pose_rmsd(pose, other, operations) for other, _ in kept]
        if scores and min(scores) <= tolerance:
            excluded.append({"config": config, "reason": "near_duplicate_seed", "RMSD_A": min(scores)})
            continue
        kept.append((pose, metadata))
    if "seed_recipes" in target:
        selected = requested_seeds(target, originals, slab, sites, operations, tolerance)
        used = {str(recipe["source_config"]) for recipe in target["seed_recipes"]}
        excluded = [
            {"config": config, "reason": (
                "geometry_review_failed" if metadata["geometry_review"]["verdict"] != "pass"
                else "not_selected_by_explicit_plan"
            )}
            for _, config, _, _, metadata, _ in originals if config not in used
        ]
        return (target, selected, excluded), originals
    if not kept:
        raise ValueError(f"no intact safe parent for {target['id']}; construction is blocked")
    kept = kept[:3]
    while len(kept) < 3:
        kept.append(construct_extra(kept[0][0], slab, sites, operations, kept, target, tolerance))
    return (target, kept, excluded), originals


def build(network_path: Path, slab_path: Path, request_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("preserve the existing output; use a reviewed new version")
    request = load_json_object(request_path)
    if sha256_file(network_path) != request["source_network_sha256"] or sha256_file(slab_path) != request["source_slab_sha256"]:
        raise ValueError("source network or accepted slab hash changed")
    if request.get("candidate_count_per_species") != 3 or not request.get("allow_exploratory_reanchor"):
        raise ValueError("this scoped preparation requires the explicit three-candidate fallback request")
    with gzip.open(network_path, "rt", encoding="utf-8") as stream:
        network = json.load(stream)
    if str(network["surface"]["facet"]) != "110":
        raise ValueError("CARE source is not the requested facet")
    slab = read_poscar(slab_path)
    if slab.symbols != ["Fe"] or slab.counts != [45] or slab.flags[:18] != [("F", "F", "F")] * 18:
        raise ValueError("accepted clean Fe45 slab / bottom-layer constraint mismatch")
    if slab.flags[18:] != [("T", "T", "T")] * 27:
        raise ValueError("unexpected extra slab constraints")
    sites, _ = generate_sites(slab)
    operations = surface_pose_symmetries(slab)
    rules_path = resource_path("configs/adsmind_lite/analysis_rules.yaml")
    tolerance = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"]
    groups, originals = [], []
    for target in request["targets"]:
        group, group_originals = prepare_group(target, network, slab, sites, operations, tolerance)
        groups.append(group)
        originals.extend(group_originals)

    # No scientific inputs or model requests are written. All output is exploratory review data.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    records, exclusions = [], []
    for target, kept, excluded in groups:
        exclusions.append({"species_id": target["id"], "excluded_originals": excluded})
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        for column, (pose, metadata) in enumerate(kept):
            name = target["id"] + "_" + "ABC"[column]
            path = output / name / "POSCAR"
            labeled = Poscar(name + " " + target["connectivity"] + " exploratory", pose.cell, pose.symbols, pose.counts, pose.frac, pose.flags)
            write_poscar(path, labeled)
            record = {**metadata, "name": name, "species_id": target["id"], "formula": target["formula"],
                      "connectivity": target["connectivity"], "care_code": target["care_prefix"],
                      "structure": f"{name}/POSCAR", "structure_sha256": sha256_file(path),
                      "status": "GEOMETRY_PASS_REVIEW_REQUIRED_NOT_RELAXED_NOT_GPU_READY",
                      **pose_measurements(pose)}
            records.append(record)
            title = name + " " + metadata["geometry_review"]["site_label"].translate(ASCII_SITE_LABEL)
            draw_pose(axes[:, column], pose, slab, title)
        fig.suptitle(target["id"] + " " + target["connectivity"] + " | Fe45 / bottom Fe0-17 fixed\nExploratory candidates only. Fe gray, C black, O red, H blue. Labels are zero-based.")
        fig.savefig(output / (target["id"] + "_structures.png"), dpi=140)
        plt.close(fig)
    for target, config, source, pose, metadata, mol in originals:
        directory = output / "originals" / target["id"] / ("cfg" + config)
        write_poscar(directory / "CARE_Fe48.vasp", source)
        write_poscar(directory / "POSCAR", pose)
        write_json(directory / "source_review.json", metadata)
        mol_path = output / "originals" / target["id"] / "source_molecule.mol"
        if not mol_path.exists():
            mol_path.write_text(mol, encoding="utf-8")
    pairwise = []
    for target, kept, _ in groups:
        for first, second in itertools.combinations(range(3), 2):
            pairwise.append({"species_id": target["id"], "pair": ["ABC"[first], "ABC"[second]],
                             "RMSD_A": equivalent_pose_rmsd(kept[first][0], kept[second][0], operations)})
    manifest = {
        "version": 1, "status": "PREPARED_FOR_HUMAN_REVIEW_ONLY", "submitted": False,
        "scientific_acceptance": False, "gpu_ready": False, "stable_motif_claim": False,
        "surface_branch": request["surface_branch"], "source_network": str(network_path),
        "source_network_sha256": sha256_file(network_path), "source_slab": str(slab_path),
        "source_slab_sha256": sha256_file(slab_path), "request_sha256": sha256_file(request_path),
        "builder_source_files": source_file_manifest([
            Path(__file__), Path(__file__).with_name("build_fe110_care_isomers.py"),
            Path(__file__).with_name("build_fe110_adsorption.py"), Path(__file__).parents[1] / "workflow_geometry.py",
        ]),
        "deduplication": {"scope": "initial_seeds_only", "slab_operation_count": len(operations),
                          "height_shift_removed": True, "RMSD_tolerance_A": tolerance,
                          "rules_sha256": sha256_file(rules_path), "pairwise": pairwise},
        "exclusions": exclusions, "candidates": records,
        "next_gate": "Human review of literature scope, local predictions, constructed motifs and soft geometry warnings; no execution authorized.",
    }
    write_json(output / "candidate_review.json", manifest)
    with (output / "structure_summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["name", "formula", "connectivity", "origin", "source_config", "site_label", "bonds_A", "nearest_Fe", "warnings"])
        writer.writeheader()
        for row in records:
            writer.writerow({**{key: row[key] for key in ("name", "formula", "connectivity", "origin", "source_config")},
                             "site_label": row["geometry_review"]["site_label"],
                             "bonds_A": json.dumps(row["bond_distances"]), "nearest_Fe": json.dumps(row["nearest_Fe"]),
                             "warnings": ";".join(row["geometry_review"]["warnings"])})
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("network", "slab", "request", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    result = build(args.network, args.slab, args.request, args.output)
    print(f"prepared={len(result['candidates'])} submitted=0 GPU_ready=False stable_claim=False")
    for row in result["candidates"]:
        print(row["name"], row["origin"], row["geometry_review"]["site_label"].translate(ASCII_SITE_LABEL), row["geometry_review"]["warnings"])


if __name__ == "__main__":
    main()
