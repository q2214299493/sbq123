"""Read-only geometric diagnostics; no structure generation or calculators."""
from __future__ import annotations

from collections import Counter
import numpy as np
from ase import Atoms
from scipy.optimize import linear_sum_assignment

from archive.fe110_10b_lowforce_20261023.legacy_helpers import pose_variants
from archive.fe110_c2_c4_gap_inventory_20261114.inventory import component_sizes
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, fe110_anchor_site_distances, minimum_image_delta_xy
from scripts.adsorption.reico_chemical_environments import chemical_environment


def composition_key(pose):
    return tuple(sorted(Counter(expanded_symbols(pose)[45:]).items()))


def iron_maps(slab, operations):
    maps = []
    for rotation, translation in operations:
        mapped = slab.frac @ rotation.T + translation
        vectors = minimum_image_delta_xy(mapped[:, None] - slab.frac[None, :]) @ slab.cell
        cost = np.sum(vectors**2, axis=-1)
        rows, columns = linear_sum_assignment(cost)
        if np.sqrt(cost[rows, columns].max()) > .01:
            raise ValueError("surface symmetry does not map clean Fe atoms")
        inverse = np.empty(45, dtype=int)
        inverse[columns] = rows
        if set(inverse[:18]) != set(range(18)):
            raise ValueError("symmetry changes fixed/free Fe roles")
        maps.append(inverse)
    return {"permutations": maps, "clean_frac": slab.frac.copy()}


def canonical_iron(pose, clean_frac):
    """Assign identical Fe within fixed/free roles to the clean lattice for comparison only."""
    result = np.empty((45, 3), dtype=float)
    for indices in (np.arange(18), np.arange(18, 45)):
        delta = minimum_image_delta_xy(pose.frac[indices, None] - clean_frac[None, indices]) @ pose.cell
        rows, columns = linear_sum_assignment(np.sum(delta**2, axis=-1))
        result[indices[columns]] = pose.frac[indices[rows]]
    return result


def packed_pose(pose, operations, maps):
    if not np.isfinite(pose.frac).all() or not np.isfinite(pose.cell).all():
        raise ValueError("nonfinite geometry")
    if expanded_symbols(pose)[:45] != ["Fe"] * 45:
        raise ValueError("expected the existing Fe45 geometry branch")
    canonical = canonical_iron(pose, maps["clean_frac"])
    fe = np.asarray([(canonical @ rotation.T + translation)[mapping][18:]
                     for (rotation, translation), mapping in zip(operations, maps["permutations"], strict=True)])
    return {"pose": pose, "key": composition_key(pose), "ads_variants": pose_variants(pose, operations), "fe_variants": fe,
            "clean_frac": maps["clean_frac"]}


def distance_metrics(first, reference, first_fe=None):
    if composition_key(first) != reference["key"]:
        return {"full_RMSD_A": float("inf"), "minimum_ads_pose_RMSD_A": float("inf")}
    if not np.allclose(first.cell, reference["pose"].cell, atol=1e-6, rtol=0):
        raise ValueError("incompatible cells;do not call different cells duplicate")
    symbols = expanded_symbols(first)[45:]
    order = sorted(range(len(symbols)), key=lambda i: symbols[i])
    delta = minimum_image_delta_xy(reference["ads_variants"] - first.frac[45:][order]) @ first.cell
    n_operations = len(reference["fe_variants"])
    ads2 = np.mean(np.sum(delta**2, axis=-1), axis=-1).reshape(n_operations, -1).min(axis=1)
    first_fe = canonical_iron(first, reference["clean_frac"]) if first_fe is None else first_fe
    fe_delta = minimum_image_delta_xy(reference["fe_variants"] - first_fe[18:45]) @ first.cell
    fe2 = np.mean(np.sum(fe_delta**2, axis=-1), axis=-1)
    values = np.maximum(ads2, fe2)
    best = int(np.argmin(values))
    return {"full_RMSD_A": float(np.sqrt(values[best])),
            "ads_RMSD_at_best_full_A": float(np.sqrt(ads2[best])), "movable_Fe_RMSD_at_best_full_A": float(np.sqrt(fe2[best])),
            "movable_Fe_max_displacement_A_at_best_full": float(np.linalg.norm(fe_delta[best], axis=1).max()),
            "minimum_ads_pose_RMSD_A": float(np.sqrt(ads2.min())), "surface_symmetry_index": best,
            "method": "min_surface_symmetry max(adsorbate_permutation_RMSD,movableFe_RMSD);XY_MIC;no_rigid_fit"}


def nearest(pose, references):
    eligible = [r for r in references if r["key"] == composition_key(pose)]
    if not eligible:
        return {"reference_id": None, "full_RMSD_A": None, "minimum_ads_pose_RMSD_A": None}
    first_fe = canonical_iron(pose, eligible[0]["clean_frac"])
    values = [(distance_metrics(pose, r, first_fe), r) for r in eligible]
    metrics, reference = min(values, key=lambda value: (value[0]["full_RMSD_A"], value[1]["id"]))
    minimum_ads = min(m["minimum_ads_pose_RMSD_A"] for m, _ in values)
    return {**metrics, "reference_id": reference["id"], "reference_source": reference["source"],
            "minimum_ads_pose_RMSD_A_any_reference": minimum_ads,
            "source_only_not_same_coordinate_force_binding": True}


def geometry_report(pose, slab, rules, pair_minimum):
    symbols = expanded_symbols(pose)
    atoms = Atoms(symbols=symbols, scaled_positions=pose.frac, cell=pose.cell, pbc=[True, True, False])
    distances = atoms.get_all_distances(mic=True)
    fixed = [i for i, flags in enumerate(pose.flags) if all(f.upper() == "F" for f in flags)]
    environment = chemical_environment(atoms, rules["connectivity"])
    elements = Counter()
    sites = []
    for i in range(45, len(symbols)):
        element = symbols[i]
        elements[element] += 1
        iron = int(distances[i, :45].argmin())
        kinds = fe110_anchor_site_distances(slab, pose.frac[i])
        kind, offset = min(kinds.items(), key=lambda item: item[1])
        sites.append({"atom": element + str(elements[element]), "index_1based": i + 1,
                      "nearest_Fe_index_1based": iron + 1, "nearest_Fe_A": float(distances[i, iron]),
                      "geometric_site": kind if offset <= .80 else "unknown", "lateral_offset_A": offset,
                      "Fe_contacts_1based": [j + 1 for j in range(45) if distances[i, j] <= environment["Fe_contact_cutoffs_A"][element]],
                      "classification_scope": "nominal clean-surface geometry;not accepted stable site"})
    pair_values = {}
    failures = []
    for i in range(len(atoms)):
        for j in range(max(i + 1, 45), len(atoms)):
            key = "-".join(sorted((symbols[i], symbols[j])))
            pair_values[key] = min(pair_values.get(key, float("inf")), float(distances[i, j]))
            if key in pair_minimum and distances[i, j] < pair_minimum[key] - 1e-8:
                failures.append({"atoms_1based": [i + 1, j + 1], "pair": key, "distance_A": float(distances[i, j]), "minimum_A": pair_minimum[key]})
    carbon = [i for i in range(45, len(atoms)) if symbols[i] == "C"]
    cc = [{"atoms_1based": [i + 1, j + 1], "distance_A": float(distances[i, j])} for k, i in enumerate(carbon) for j in carbon[k+1:]]
    return {"fixed_indices_0based": fixed, "bottom18_only_fixed": fixed == list(range(18)),
            "same_clean_cell_within1e-6A": bool(np.allclose(pose.cell, slab.cell, atol=1e-6, rtol=0)),
            "cell_max_difference_A": float(np.abs(pose.cell - slab.cell).max()),
            "pair_minima_A": pair_values, "pair_guard_failures": failures, "binding_sites": sites, "C_C_pairs": cc,
            "minimum_ads_height_above_top_Fe_A": float((atoms.positions[45:, 2] - atoms.positions[:45, 2].max()).min()),
            "graph": component_sizes(symbols[45:], environment["adsorbate_edges_local_0based"]),
            "environment": environment, "geometry_is_not_electronic_or_magnetic_acceptance": True}
