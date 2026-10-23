"""Permutation-invariant geometric strata for the bounded Fe45 training audit."""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations, permutations, product

import numpy as np
from ase.data import atomic_numbers, covalent_radii

from scripts.adsmind_lite.relaxed_analysis import (
    connected_component_count, connectivity_edges,
)


def canonical_graph(symbols: list[str], edges: list, coordination=None) -> str:
    """Exact small-graph canonicalization; no atom-index or graph-hash collisions."""
    if not symbols or len(symbols) > 6 or set(symbols)-{"C", "H", "O"}:
        raise ValueError("expected one to six C/H/O atoms")
    adjacency = {tuple(sorted(edge)) for edge in edges}
    groups = [[i for i, symbol in enumerate(symbols) if symbol == element] for element in sorted(set(symbols))]
    candidates = []
    for ordering in product(*(permutations(group) for group in groups)):
        order = sum((list(group) for group in ordering), [])
        labels = ",".join(symbols[i] + (f":{coordination[i]}" if coordination is not None else "") for i in order)
        bits = "".join("1" if tuple(sorted((order[i], order[j]))) in adjacency else "0"
                       for i, j in combinations(range(len(order)), 2))
        candidates.append(labels + "|" + bits)
    return min(candidates)


def chemical_environment(atoms, rules: dict, *, scale: float | None = None) -> dict:
    """Radius-based contacts are geometric diagnostics, not electronic bonds."""
    symbols = atoms.get_chemical_symbols()[45:]
    if not symbols or set(symbols)-{"C", "H", "O"}:
        raise ValueError("unexpected adsorbate elements")
    scale = float(rules["covalent_radius_scale"] if scale is None else scale)
    minimum = float(rules["minimum_bond_distance_angstrom"])
    edges = connectivity_edges(atoms, list(range(45, len(atoms))), scale, minimum)
    distances = atoms.get_all_distances(mic=True)[45:, :45]
    cutoffs = scale*(covalent_radii[atomic_numbers["Fe"]] + np.array([covalent_radii[atomic_numbers[s]] for s in symbols]))
    coordination = np.sum((distances >= minimum) & (distances <= cutoffs[:, None]), axis=1).astype(int).tolist()
    profile = {s: sorted(coordination[i] for i, symbol in enumerate(symbols) if symbol == s) for s in ("C", "O", "H")}
    return {
        "graph_signature": canonical_graph(symbols, edges),
        "coordination_signature": ";".join(s+":"+",".join(map(str, profile[s])) for s in profile),
        "joint_signature": canonical_graph(symbols, edges, coordination),
        "coordination_by_element": profile,
        "Fe_coordination_by_adsorbate_index": coordination,
        "adsorbate_edges_local_0based": edges,
        "bond_counts": dict(Counter("-".join(sorted((symbols[i], symbols[j]))) for i, j in edges)),
        "adsorbate_component_count": connected_component_count(len(symbols), edges),
        "Fe_contact_cutoffs_A": {s: float(scale*(covalent_radii[atomic_numbers["Fe"]]+covalent_radii[atomic_numbers[s]])) for s in sorted(set(symbols))},
        "Fe_contacts_within_0p05A_of_cutoff": int(np.sum(np.abs(distances-cutoffs[:, None]) <= .05)),
    }


def stratum_summary(rows: list[dict], selected_ids: set[str], key: str) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    result = []
    for signature, members in sorted(groups.items()):
        selected = [r for r in members if r["sample_id"] in selected_ids]
        representative = min(members, key=lambda r: (-r["novelty_ratio"], r["sample_id"]))
        result.append({"signature": signature, "pool_frames": len(members),
                       "pool_families": len({r["family_id"] for r in members}),
                       "selected_frames": len(selected),
                       "selected_families": len({r["family_id"] for r in selected}),
                       "representative_id": representative["sample_id"],
                       "maximum_SOAP_ratio": representative["novelty_ratio"]})
    return {"pool_strata": len(result), "covered_strata": sum(r["selected_frames"] > 0 for r in result),
            "missing_strata": sum(r["selected_frames"] == 0 for r in result),
            "frames_in_missing_strata": sum(r["pool_frames"] for r in result if r["selected_frames"] == 0),
            "strata": result}
