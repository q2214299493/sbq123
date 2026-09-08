"""Raw geometry and connectivity evidence for TS endpoint validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from scripts.adsmind_lite.adsmind_common import require_ase_structure
from scripts.adsmind_lite.relaxed_analysis import connectivity_edges
from scripts.neb_agent.utils_structure import (
    Poscar,
    displacement_cart,
    pbc_distance,
    read_poscar,
)


@dataclass(frozen=True)
class EndpointStructures:
    initial: Poscar
    endpoint: Poscar


@dataclass(frozen=True)
class EndpointGeometryEvidence:
    atomic_displacement_A: dict[int, float]
    adsorbate_com_displacement_A: float
    initial_connectivity_edges: tuple[tuple[int, int], ...]
    endpoint_connectivity_edges: tuple[tuple[int, int], ...]
    endpoint_pair_distances_A: dict[tuple[int, int], float]
    adsorbate_surface_height_change_A: dict[int, float]


def load_endpoint_structures(
    initial_path: Path,
    endpoint_path: Path,
) -> EndpointStructures:
    """Load endpoint inputs without assigning any scientific status."""

    return EndpointStructures(
        initial=read_poscar(initial_path),
        endpoint=read_poscar(endpoint_path),
    )


def collect_endpoint_geometry_evidence(
    structures: EndpointStructures,
    *,
    initial_path: Path,
    endpoint_path: Path,
    adsorbate_atoms: tuple[int, ...],
    surface_atoms: tuple[int, ...],
    covalent_radius_scale: float,
    minimum_bond_distance_A: float,
) -> EndpointGeometryEvidence:
    """Collect raw displacement and connectivity evidence without judging it."""

    displacement_vectors = {
        index: displacement_cart(
            structures.initial,
            structures.initial.frac[index],
            structures.endpoint.frac[index],
        )
        for index in range(structures.initial.atom_count)
    }
    displacements = {
        index: float(np.linalg.norm(vector))
        for index, vector in displacement_vectors.items()
    }

    initial_atoms = require_ase_structure(initial_path)
    if adsorbate_atoms:
        masses = initial_atoms.get_masses()[list(adsorbate_atoms)]
        selected = np.array(
            [displacement_vectors[index] for index in adsorbate_atoms]
        )
        adsorbate_com = float(
            np.linalg.norm(np.average(selected, axis=0, weights=masses))
        )
    else:
        adsorbate_com = 0.0

    endpoint_atoms = require_ase_structure(endpoint_path)
    indices = list(range(len(initial_atoms)))
    initial_edges = tuple(
        sorted(
            connectivity_edges(
                initial_atoms,
                indices,
                covalent_radius_scale,
                minimum_bond_distance_A,
            )
        )
    )
    endpoint_edges = tuple(
        sorted(
            connectivity_edges(
                endpoint_atoms,
                indices,
                covalent_radius_scale,
                minimum_bond_distance_A,
            )
        )
    )
    pair_distances = {
        (left, right): pbc_distance(structures.endpoint, left, right)
        for right in range(structures.endpoint.atom_count)
        for left in range(right)
    }
    resolved_surface_atoms = surface_atoms or tuple(
        index
        for index in range(structures.initial.atom_count)
        if index not in adsorbate_atoms
    )
    height_changes: dict[int, float] = {}
    if adsorbate_atoms and resolved_surface_atoms:
        initial_cart = structures.initial.frac @ structures.initial.cell
        endpoint_cart = structures.endpoint.frac @ structures.endpoint.cell
        initial_surface_top = max(
            float(initial_cart[index, 2]) for index in resolved_surface_atoms
        )
        endpoint_surface_top = max(
            float(endpoint_cart[index, 2]) for index in resolved_surface_atoms
        )
        height_changes = {
            index: float(
                (endpoint_cart[index, 2] - endpoint_surface_top)
                - (initial_cart[index, 2] - initial_surface_top)
            )
            for index in adsorbate_atoms
        }
    return EndpointGeometryEvidence(
        atomic_displacement_A=displacements,
        adsorbate_com_displacement_A=adsorbate_com,
        initial_connectivity_edges=initial_edges,
        endpoint_connectivity_edges=endpoint_edges,
        endpoint_pair_distances_A=pair_distances,
        adsorbate_surface_height_change_A=height_changes,
    )
