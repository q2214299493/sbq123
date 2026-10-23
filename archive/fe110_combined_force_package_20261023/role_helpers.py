"""Exact legacy geometry-role helpers for data metadata,not a new loss policy."""
from __future__ import annotations
import numpy as np

ROLE_WEIGHTS = {'adsorbate_C': 2.0, 'adsorbate_O': 1.0, 'adsorbate_H': 1.0, 'near_Fe': 2.0, 'other_Fe': 1.0}
FUNCTION_BINDINGS = {'role_groups': {'source': 'archive\\fe110_adsorption_pool_rebuild_20261019\\roles.py', 'source_sha256': 'a727f9c1dccbbd3bfba2abaa2b04ceb3c3d2a0bb5ad507c9663c6974ba0dd196', 'function_sha256': 'ad35a3a7241ce174970b09b0535c7bbf52eeab9a1c04ea1a714ac1be29c303d6'}, 'atom_weights': {'source': 'archive\\fe110_adsorption_pool_rebuild_20261019\\roles.py', 'source_sha256': 'a727f9c1dccbbd3bfba2abaa2b04ceb3c3d2a0bb5ad507c9663c6974ba0dd196', 'function_sha256': '9babe7e1214c1a91f9a70b63a83fd752894d44f59d5af02aed0293b71e18acfb'}}

def role_groups(atoms, radius: float = 3.) -> dict[str, list[int]]:
    """Radius selects a proposed loss group, never a geometry acceptance gate."""
    fixed = {int(i) for c in atoms.constraints for i in c.get_indices()}
    symbols = atoms.get_chemical_symbols()
    groups = {key: [] for key in ROLE_WEIGHTS}
    active = [i for i, s in enumerate(symbols) if s != "Fe" and i not in fixed]
    distances = atoms.get_all_distances(mic=True)
    for i, symbol in enumerate(symbols):
        if i in fixed:
            continue
        if symbol != "Fe":
            key = "adsorbate_" + symbol
            if key not in groups:
                raise ValueError("unsupported role element")
        else:
            key = "near_Fe" if active and min(distances[i, j] for j in active) <= radius else "other_Fe"
        groups[key].append(i)
    if sorted(i for g in groups.values() for i in g) != [i for i in range(len(atoms)) if i not in fixed]:
        raise ValueError("roles must partition the movable atoms")
    return groups


def atom_weights(groups: dict, count: int) -> np.ndarray:
    result = np.zeros(count)
    mass = sum(ROLE_WEIGHTS[k] for k, indices in groups.items() if indices)
    if not mass:
        raise ValueError("no active roles")
    for key, indices in groups.items():
        if indices:
            result[indices] = ROLE_WEIGHTS[key] / (mass * len(indices))
    return result
