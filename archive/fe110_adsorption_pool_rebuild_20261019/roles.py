"""Chemical-role groups for a proposed force objective, not a training launcher."""
from __future__ import annotations

from itertools import permutations, product

import numpy as np

from scripts.adsorption.build_fe110_adsorption import expanded_symbols
from scripts.workflow_geometry import minimum_image_delta_xy

ROLE_WEIGHTS = {"adsorbate_C": 2., "adsorbate_O": 1., "adsorbate_H": 1.,
                "near_Fe": 2., "other_Fe": 1.}


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


def grouped_vector_loss(reference, prediction, groups) -> float:
    reference, prediction = np.asarray(reference), np.asarray(prediction)
    if reference.shape != prediction.shape or reference.ndim != 2 or reference.shape[1] != 3:
        raise ValueError("force dimensions changed")
    if not np.isfinite(reference).all() or not np.isfinite(prediction).all():
        raise ValueError("nonfinite force")
    return float(np.dot(atom_weights(groups, len(reference)), np.linalg.norm(prediction-reference, axis=1)))


def pose_variants(pose, operations) -> np.ndarray:
    """Same-element permutations for leakage audit only; no stored atoms moved."""
    original_symbols = expanded_symbols(pose)[45:]
    canonical_order = sorted(range(len(original_symbols)), key=lambda i: original_symbols[i])
    symbols = [original_symbols[i] for i in canonical_order]
    coordinates = pose.frac[45:][canonical_order]
    by_symbol = [[i for i, v in enumerate(symbols) if v == s] for s in sorted(set(symbols))]
    orders = []
    for choices in product(*(permutations(indices) for indices in by_symbol)):
        order = list(range(len(symbols)))
        for indices, permutation in zip(by_symbol, choices, strict=True):
            for a, b in zip(indices, permutation, strict=True):
                order[a] = b
        orders.append(order)
    return np.asarray([(coordinates @ rotation.T + translation)[order]
                       for rotation, translation in operations for order in orders])


def pose_distance(first, second_variants) -> float:
    symbols = expanded_symbols(first)[45:]
    order = sorted(range(len(symbols)), key=lambda i: symbols[i])
    delta = minimum_image_delta_xy(second_variants-first.frac[45:][order]) @ first.cell
    return float(np.sqrt(np.min(np.mean(np.sum(delta**2, axis=-1), axis=-1))))
