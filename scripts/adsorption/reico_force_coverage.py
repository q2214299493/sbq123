"""Training-only force distributions and permutation-aware DFT force differences."""
from __future__ import annotations

from collections import Counter

import numpy as np
from ase.geometry import find_mic
from scipy.optimize import linear_sum_assignment

from scripts.adsorption.reico_selection import frame_distance


def checked_forces(atoms, values) -> np.ndarray:
    forces = np.asarray(values, dtype=float)
    if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all():
        raise ValueError("incomplete or nonfinite raw force array")
    return forces


def force_histogram(values: list[float], edges: list[float]) -> dict:
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0) or edges[0] != 0 or any(b <= a for a,b in zip(edges,edges[1:])):
        raise ValueError("invalid nonnegative force values or histogram edges")
    bins = np.array([*edges, np.inf])
    counts, _ = np.histogram(values, bins=bins)
    return {f"[{a:g},{b:g})":int(n) for a,b,n in zip(bins[:-1], bins[1:], counts, strict=True)}


def force_coverage(rows: list[dict], atoms: dict, edges: list[float]) -> dict:
    if any(r["partition"] != "train" for r in rows):
        raise ValueError("force coverage accepts training labels only")
    groups = {}
    for composition in sorted({r["composition"] for r in rows}):
        subset = [r for r in rows if r["composition"] == composition]
        maxima, ads_maxima, role_values = [], [], {s:[] for s in ("Fe", "C", "O", "H")}
        for row in subset:
            structure = atoms[row["sample_id"]]
            forces = checked_forces(structure, row["forces_eV_per_A"])
            norms = np.linalg.norm(forces, axis=1)
            maxima.append(float(norms[18:].max()))
            ads_maxima.append(float(norms[45:].max()))
            for i,symbol in enumerate(structure.get_chemical_symbols()):
                if i >= 18:
                    role_values[symbol].append(float(norms[i]))
        groups[composition] = {"frames":len(subset),"families":len({r["family_id"] for r in subset}),
                               "movable_fmax_range_eV_A":[min(maxima),max(maxima)],
                               "movable_fmax_quantiles_eV_A":dict(zip(("p10","p50","p90"), np.quantile(maxima,[.1,.5,.9]).tolist(), strict=True)),
                               "near_equilibrium_fmax_le_0p05":sum(v <= .05 for v in maxima),
                               "movable_fmax_histogram":force_histogram(maxima,edges),
                               "adsorbate_fmax_histogram":force_histogram(ads_maxima,edges),
                               "per_atom_role_histograms":{s:force_histogram(v,edges) for s,v in role_values.items() if v}}
    return groups


def matched_force_difference(first, second, forces_first, forces_second) -> dict:
    if Counter(first.get_chemical_symbols()) != Counter(second.get_chemical_symbols()) or not np.allclose(first.cell,second.cell,atol=1e-12,rtol=0):
        raise ValueError("incompatible pair composition or cell")
    one, two = checked_forces(first,forces_first), checked_forces(second,forces_second)
    mapping = np.arange(len(first))
    for element in sorted(set(first.get_chemical_symbols()[45:])):
        indices_a = [i for i in range(45,len(first)) if first[i].symbol == element]
        indices_b = [i for i in range(45,len(second)) if second[i].symbol == element]
        vectors = first.positions[indices_a,None,:]-second.positions[None,indices_b,:]
        _,lengths = find_mic(vectors.reshape(-1,3),first.cell,[True,True,False])
        a,b = linear_sum_assignment(lengths.reshape(len(indices_a),len(indices_b))**2)
        mapping[np.asarray(indices_a)[a]] = np.asarray(indices_b)[b]
    difference = two[mapping]-one
    result = {"geometry_RMSD_A":frame_distance(first,second),"second_atom_for_each_first_0based":mapping.tolist()}
    groups = {"movable":np.arange(18,len(first)),"adsorbate":np.arange(45,len(first)),"movable_Fe":np.arange(18,45)}
    for name,indices in groups.items():
        norms = np.linalg.norm(difference[indices],axis=1)
        result[name] = {"mean_vector_difference_eV_A":float(norms.mean()),
                        "vector_RMSE_difference_eV_A":float(np.sqrt(np.mean(norms**2))),
                        "maximum_vector_difference_eV_A":float(norms.max())}
    return result


def nearby_force_pairs(rows: list[dict], atoms: dict, geometry: dict, maximum_A: float) -> list[dict]:
    if any(r["partition"] != "train" for r in rows):
        raise ValueError("near-pair comparisons accept training labels only")
    result = []
    for index,one in enumerate(rows):
        for two in rows[index+1:]:
            if one["composition"] != two["composition"]:
                continue
            a,b = atoms[one["sample_id"]],atoms[two["sample_id"]]
            distance = frame_distance(a,b)
            if distance >= maximum_A:
                continue
            metrics = matched_force_difference(a,b,one["forces_eV_per_A"],two["forces_eV_per_A"])
            pair = {"first":one["sample_id"],"second":two["sample_id"],"composition":one["composition"],
                    "same_family":one["family_id"] == two["family_id"],**metrics,
                    "same_graph":geometry[one["sample_id"]]["graph_signature"] == geometry[two["sample_id"]]["graph_signature"],
                    "same_joint_stratum":geometry[one["sample_id"]]["joint_signature"] == geometry[two["sample_id"]]["joint_signature"],
                    "total_moment_difference_muB":abs(one["total_magnetization_muB"]-two["total_magnetization_muB"]),
                    "maximum_Fe_local_moment_difference_muB":float(np.max(np.abs(np.asarray(one["local_magnetization_muB"][:45])-np.asarray(two["local_magnetization_muB"][:45]))))}
            result.append(pair)
    return sorted(result,key=lambda r:(-r["adsorbate"]["vector_RMSE_difference_eV_A"],r["first"],r["second"]))
