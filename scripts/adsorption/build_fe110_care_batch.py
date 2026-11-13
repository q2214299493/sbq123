"""Shared molecular identity check used by completed adsorption review."""
from __future__ import annotations

from .build_fe110_adsorption import Poscar, expanded_symbols
from .build_fe110_care_isomers import adsorbate_indices, connectivity


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
