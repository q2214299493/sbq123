from __future__ import annotations

import itertools
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.data import covalent_radii

from scripts.adsorption.build_fe110_adsorption import Poscar, classify_fe110_anchor_site
from scripts.workflow_geometry import inplane_pbc_vector, minimum_image_delta_xy, relative_positions_xy

from .adsmind_common import SITE_CLASS_MAP, load_yaml, read_json, require_ase_structure
from .candidate_generation import ordered_unique


def connectivity_edges(atoms: Atoms, indices: list[int], scale: float, minimum: float) -> list[tuple[int, int]]:
    """Return adsorbate-local 0-based bonds using MIC distances and Å cutoffs."""
    edges: list[tuple[int, int]] = []
    for local_first, local_second in itertools.combinations(range(len(indices)), 2):
        first, second = indices[local_first], indices[local_second]
        cutoff = scale * (covalent_radii[atoms.numbers[first]] + covalent_radii[atoms.numbers[second]])
        distance = float(atoms.get_distance(first, second, mic=True))
        if minimum <= distance <= cutoff:
            edges.append((local_first, local_second))
    return edges


def is_connected(atom_count: int, edges: list[tuple[int, int]]) -> bool:
    if atom_count <= 1:
        return True
    neighbors: dict[int, set[int]] = defaultdict(set)
    for first, second in edges:
        neighbors[first].add(second)
        neighbors[second].add(first)
    visited = {0}
    stack = [0]
    while stack:
        stack.extend(neighbors[stack.pop()] - visited)
        visited.update(stack)
    return len(visited) == atom_count


def connected_component_count(atom_count: int, edges: list[tuple[int, int]]) -> int:
    if atom_count == 0:
        return 0
    neighbors: dict[int, set[int]] = defaultdict(set)
    for first, second in edges:
        neighbors[first].add(second)
        neighbors[second].add(first)
    remaining = set(range(atom_count))
    components = 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            neighbors_to_visit = neighbors[stack.pop()] & remaining
            remaining.difference_update(neighbors_to_visit)
            stack.extend(neighbors_to_visit)
    return components


def connectivity_change(
    atom_count: int,
    initial_edges: list[tuple[int, int]],
    relaxed_edges: list[tuple[int, int]],
) -> dict[str, Any]:
    """Classify local-index bond changes; dissociation requires an increased fragment count."""
    initial = set(initial_edges)
    relaxed = set(relaxed_edges)
    lost = sorted(initial - relaxed)
    formed = sorted(relaxed - initial)
    initial_components = connected_component_count(atom_count, initial_edges)
    relaxed_components = connected_component_count(atom_count, relaxed_edges)
    if relaxed_components > initial_components:
        event = "dissociation"
    elif relaxed_components < initial_components:
        event = "association"
    elif lost or formed:
        event = "bond_rearrangement"
    else:
        event = "none"
    return {
        "connectivity_changed": bool(lost or formed),
        "dissociated": event == "dissociation",
        "chemical_event": event,
        "lost_bonds": lost,
        "formed_bonds": formed,
        "initial_fragment_count": initial_components,
        "relaxed_fragment_count": relaxed_components,
    }


def minimum_cross_distance(atoms: Atoms, slab_indices: list[int], adsorbate_indices: list[int]) -> float:
    """Return the minimum slab–adsorbate distance in Å using 0-based ASE indices and MIC."""
    if not slab_indices or not adsorbate_indices:
        raise ValueError("slab and adsorbate atom indices are required")
    return min(float(atoms.get_distance(first, second, mic=True)) for first in slab_indices for second in adsorbate_indices)


def hard_contact_distance(analysis: dict[str, Any]) -> float:
    """Read and validate the emergency slab–adsorbate overlap cutoff in Å."""
    value = analysis.get("contact_validation", {}).get("hard_contact_distance_angstrom")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("contact_validation.hard_contact_distance_angstrom must be a positive number in Å")
    return float(value)


def is_hard_contact(distance_angstrom: float, threshold_angstrom: float) -> bool:
    """Return whether an Å-valued distance is strictly below the Å-valued overlap cutoff."""
    if distance_angstrom < 0 or threshold_angstrom <= 0:
        raise ValueError("contact distances and thresholds must use non-negative Å values")
    return distance_angstrom < threshold_angstrom


def structure_indices(record: dict[str, Any], atom_count: int) -> tuple[list[int], list[int]]:
    """Validate and return 0-based slab and adsorbate indices for one structure."""
    slab_count = int(record["slab_atom_count"])
    slab_indices = [int(value) for value in record.get("slab_indices_structure_0based", range(slab_count))]
    adsorbate_indices = [int(value) for value in record.get("adsorbate_indices_structure_0based", range(slab_count, atom_count))]
    combined = slab_indices + adsorbate_indices
    if (
        len(slab_indices) != slab_count
        or not adsorbate_indices
        or len(set(combined)) != len(combined)
        or min(combined) < 0
        or max(combined) >= atom_count
    ):
        raise ValueError("invalid slab/adsorbate structure index map")
    return slab_indices, adsorbate_indices


def validate_candidates(
    candidate_root: Path,
    surfaces_config: Path,
    adsorbate_config: Path,
    analysis_config: Path,
) -> list[dict[str, Any]]:
    family_config = load_yaml(surfaces_config)["surface_families"]
    adsorbates = load_yaml(adsorbate_config)["adsorbates"]
    analysis = load_yaml(analysis_config)
    minimum = float(analysis["connectivity"]["minimum_bond_distance_angstrom"])
    scale = float(analysis["connectivity"]["covalent_radius_scale"])
    hard_contact = hard_contact_distance(analysis)
    seen: set[tuple[Any, ...]] = set()
    results: list[dict[str, Any]] = []
    for metadata_path in sorted(candidate_root.rglob("metadata.json")):
        metadata = read_json(metadata_path)
        result = dict(metadata)
        reason = validate_one_candidate(result, family_config, adsorbates, minimum, scale, hard_contact, seen)
        result["validation_passed"] = reason == "accepted"
        result["recommend_for_vasp"] = (
            reason == "accepted" and result.get("confidence_level") in {"high", "medium"} and not result.get("needs_review", False)
        )
        result["reason_code"] = reason
        results.append(result)
    return results


def validate_one_candidate(
    record: dict[str, Any],
    families: dict[str, Any],
    adsorbates: dict[str, Any],
    minimum: float,
    scale: float,
    hard_contact: float,
    seen: set[tuple[Any, ...]],
) -> str:
    family = record["surface_family"]
    adsorbate = record["adsorbate"]
    if family not in families:
        return "unsupported_surface_family"
    if adsorbate not in adsorbates:
        return "invalid_binding_atom"
    rule = adsorbates[adsorbate]
    if record["planned_binding_atom"] not in rule["preferred_binding_atoms"]:
        return "invalid_binding_atom"
    if record["planned_binding_atom"] in rule.get("forbidden_binding_atoms", []):
        return "invalid_binding_atom"
    if record["planned_site_class"] not in families[family]["site_classes"]:
        return "site_type_not_allowed"
    if family != "metallic_fe" and record.get("site_label_source") != "explicit_manifest":
        record["needs_review"] = True
        return "explicit_site_label_required"
    atoms = require_ase_structure(Path(record["initial_structure"]))
    slab_indices, adsorbate_indices = structure_indices(record, len(atoms))
    surface_atoms = require_ase_structure(Path(record["surface_structure"]))
    role_reason = lattice_role_reason(record, surface_atoms, rule)
    if role_reason is not None:
        record["needs_review"] = True
        record["confidence_level"] = "low"
        return role_reason
    if record.get("reason_code") in {
        "lattice_adsorbate_atom_confusion",
        "explicit_site_label_required",
        "oxygen_vacancy_not_tagged",
    }:
        return str(record["reason_code"])
    if is_hard_contact(minimum_cross_distance(atoms, slab_indices, adsorbate_indices), hard_contact):
        return "too_close_to_surface"
    edges = connectivity_edges(atoms, adsorbate_indices, scale, minimum)
    if not is_connected(len(adsorbate_indices), edges):
        return "adsorbate_fragmented"
    fingerprint = initial_configuration_fingerprint(record, atoms, adsorbate_indices)
    if fingerprint in seen:
        return "duplicate_candidate"
    seen.add(fingerprint)
    return "accepted"


def initial_configuration_fingerprint(
    record: dict[str, Any], atoms: Atoms, adsorbate_indices: list[int], decimals: int = 4
) -> tuple[Any, ...]:
    anchor = int(record["anchor_index_structure_0based"])
    relative = relative_positions_xy(np.asarray(atoms.cell), atoms.positions[adsorbate_indices], atoms.positions[anchor])
    geometry = tuple(np.round(relative, decimals=decimals).ravel().tolist())
    symbols = tuple(atoms[index].symbol for index in adsorbate_indices)
    return (str(record["adsorbate"]), str(record["planned_site_class"]), symbols, geometry)


def lattice_role_reason(record: dict[str, Any], surface_atoms: Atoms, adsorbate_rule: dict[str, Any]) -> str | None:
    family = record["surface_family"]
    labels = {int(index): str(role) for index, role in record.get("atom_labels", {}).items()}
    if family == "iron_carbide" and "C" in adsorbate_rule["atom_symbols"]:
        carbon_roles = [labels.get(index + 1) for index, atom in enumerate(surface_atoms) if atom.symbol == "C"]
        if "C_lattice" not in carbon_roles or any(role not in {"C_lattice", "C_ads"} for role in carbon_roles):
            return "lattice_adsorbate_atom_confusion"
    if family == "iron_oxide" and "O" in adsorbate_rule["atom_symbols"]:
        oxygen_roles = [labels.get(index + 1) for index, atom in enumerate(surface_atoms) if atom.symbol == "O"]
        if "O_lattice" not in oxygen_roles or any(role not in {"O_lattice", "O_ads"} for role in oxygen_roles):
            return "lattice_adsorbate_atom_confusion"
    if record["planned_site_class"] == "oxygen_vacancy":
        if not record.get("high_risk_sites", {}).get("oxygen_vacancy", {}).get("explicitly_tagged"):
            return "oxygen_vacancy_not_tagged"
    return None


def structure_connectivity(
    path: Path,
    adsorbate_indices: list[int],
    analysis: dict[str, Any],
) -> tuple[list[tuple[int, int]], Atoms]:
    atoms = require_ase_structure(path)
    rules = analysis["connectivity"]
    edges = connectivity_edges(
        atoms,
        adsorbate_indices,
        float(rules["covalent_radius_scale"]),
        float(rules["minimum_bond_distance_angstrom"]),
    )
    return edges, atoms


def inplane_vector(cell: np.ndarray, first: np.ndarray, second: np.ndarray) -> np.ndarray:
    return inplane_pbc_vector(cell, first, second)


def classify_relaxed_site(
    initial: Atoms,
    relaxed: Atoms,
    anchor_index: int,
    analysis: dict[str, Any],
) -> str:
    """Classify a relaxed 0-based anchor index against the initial slab under x/y PBC."""
    rules = analysis["site_classification"]
    symbols = relaxed.get_chemical_symbols()
    species = ordered_unique(symbols)
    poscar = Poscar(
        comment="relaxed structure for site classification",
        cell=np.asarray(relaxed.cell),
        symbols=species,
        counts=[symbols.count(symbol) for symbol in species],
        frac=relaxed.get_scaled_positions(wrap=False),
        flags=[("T", "T", "T")] * len(relaxed),
    )
    initial_symbols = initial.get_chemical_symbols()
    initial_species = ordered_unique(initial_symbols)
    reference = Poscar(
        comment="initial structure for site classification",
        cell=np.asarray(initial.cell),
        symbols=initial_species,
        counts=[initial_symbols.count(symbol) for symbol in initial_species],
        frac=initial.get_scaled_positions(wrap=False),
        flags=[("T", "T", "T")] * len(initial),
    )
    name, _ = classify_fe110_anchor_site(
        poscar,
        poscar.frac[anchor_index],
        reference_poscar=reference,
        lateral_tolerance=float(rules["top_lateral_tolerance_angstrom"]),
    )
    return SITE_CLASS_MAP.get(name, "unknown")


def classify_manifest_site(relaxed: Atoms, anchor_index: int, sites_payload: dict[str, Any], analysis: dict[str, Any]) -> str:
    cell = np.asarray(relaxed.cell)
    anchor = relaxed.positions[anchor_index]
    candidates: list[tuple[float, str]] = []
    for site in sites_payload.get("sites", []):
        fractional_xy = site.get("fractional_xy")
        if not isinstance(fractional_xy, list) or len(fractional_xy) != 2:
            continue
        site_position = np.array([float(fractional_xy[0]), float(fractional_xy[1]), 0.0]) @ cell
        distance = float(np.linalg.norm(inplane_vector(cell, anchor, site_position)))
        candidates.append((distance, str(site["site_class"])))
    if not candidates:
        return "unknown"
    distance, site_class = min(candidates)
    tolerance = float(analysis["site_classification"].get("explicit_site_lateral_tolerance_angstrom", 0.8))
    return site_class if distance <= tolerance else "unknown"


def maximum_slab_displacement(initial: Atoms, relaxed: Atoms, slab_indices: list[int]) -> float:
    distances = []
    for index in slab_indices:
        vector = relaxed.positions[index] - initial.positions[index]
        fractional = vector @ np.linalg.inv(np.asarray(relaxed.cell))
        distances.append(float(np.linalg.norm(minimum_image_delta_xy(fractional) @ np.asarray(relaxed.cell))))
    return max(distances, default=0.0)


def confidence_for_analysis(
    record: dict[str, Any], slip: bool, connectivity_changed: bool, unknown: bool, reconstructed: bool
) -> str:
    family = record["surface_family"]
    if connectivity_changed or unknown or reconstructed:
        return "low"
    if family == "metallic_fe" and not slip:
        return str(record.get("confidence_level", "high"))
    if family == "iron_carbide" or slip:
        return "medium"
    if family == "iron_oxide":
        return str(record.get("confidence_level", "low"))
    return str(record.get("confidence_level", "low"))


def analysis_reason(
    slip: bool,
    connectivity_changed: bool,
    dissociated: bool,
    unknown: bool,
    reconstructed: bool,
    intended: bool,
) -> str:
    if reconstructed:
        return "surface_reconstructed"
    if unknown:
        return "unknown_surface_site"
    if dissociated and not intended:
        return "dissociated_unintentionally"
    if connectivity_changed and not (dissociated and intended):
        return "connectivity_changed"
    if slip:
        return "slipped_to_new_site"
    return "accepted"


def analyze_relaxed_candidate(
    metadata: dict[str, Any],
    relaxed_path: Path,
    sites_payload: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    initial_path = Path(metadata["initial_structure"])
    initial_probe = require_ase_structure(initial_path)
    slab_indices, adsorbate_indices = structure_indices(metadata, len(initial_probe))
    initial_edges, initial = structure_connectivity(initial_path, adsorbate_indices, analysis)
    relaxed_edges, relaxed = structure_connectivity(relaxed_path, adsorbate_indices, analysis)
    connectivity = connectivity_change(len(adsorbate_indices), initial_edges, relaxed_edges)
    dissociated = bool(connectivity["dissociated"])
    anchor_index = int(metadata["anchor_index_structure_0based"])
    if metadata["surface_family"] == "metallic_fe":
        relaxed_site = classify_relaxed_site(initial, relaxed, anchor_index, analysis)
    else:
        relaxed_site = classify_manifest_site(relaxed, anchor_index, sites_payload, analysis)
    slip = relaxed_site != metadata["planned_site_class"]
    reconstructed = maximum_slab_displacement(initial, relaxed, slab_indices) > float(
        analysis["surface_reconstruction"]["maximum_slab_displacement_angstrom"]
    )
    unknown = relaxed_site == "unknown"
    confidence = confidence_for_analysis(metadata, slip, bool(connectivity["connectivity_changed"]), unknown, reconstructed)
    intended = bool(metadata.get("target_dissociative", False))
    reason = analysis_reason(
        slip,
        bool(connectivity["connectivity_changed"]),
        dissociated,
        unknown,
        reconstructed,
        intended,
    )
    needs_review = bool(metadata.get("needs_review", False) or connectivity["connectivity_changed"] or unknown or reconstructed)
    recommend = reason in {"accepted", "slipped_to_new_site"} and confidence in {"high", "medium"} and not needs_review
    return {
        **metadata,
        "relaxed_site_class": relaxed_site,
        "chemical_slip": slip,
        "dissociated": dissociated,
        "connectivity_changed": connectivity["connectivity_changed"],
        "chemical_event": connectivity["chemical_event"],
        "lost_bonds": connectivity["lost_bonds"],
        "formed_bonds": connectivity["formed_bonds"],
        "initial_fragment_count": connectivity["initial_fragment_count"],
        "relaxed_fragment_count": connectivity["relaxed_fragment_count"],
        "duplicate": False,
        "surface_reconstructed": reconstructed,
        "connectivity_signature": "-".join(f"{first}-{second}" for first, second in relaxed_edges),
        "relaxed_structure": str(relaxed_path),
        "selected_structure": str(relaxed_path),
        "recommend_for_vasp": recommend,
        "confidence_level": confidence,
        "needs_review": needs_review,
        "reason_code": reason,
    }


def analyze_relaxed_tree(
    candidate_root: Path,
    relaxed_root: Path,
    sites_path: Path,
    analysis_config: Path,
) -> list[dict[str, Any]]:
    sites = read_json(sites_path)
    analysis = load_yaml(analysis_config)
    records: list[dict[str, Any]] = []
    for metadata_path in sorted(candidate_root.rglob("metadata.json")):
        metadata = read_json(metadata_path)
        relative = metadata_path.parent.relative_to(candidate_root)
        relaxed_path = relaxed_root / relative / "CONTCAR"
        if not relaxed_path.is_file():
            records.append(
                {
                    **metadata,
                    "relaxed_site_class": "unknown",
                    "chemical_slip": False,
                    "dissociated": False,
                    "duplicate": False,
                    "recommend_for_vasp": False,
                    "confidence_level": "low",
                    "needs_review": True,
                    "reason_code": "missing_relaxed_structure",
                }
            )
            continue
        records.append(analyze_relaxed_candidate(metadata, relaxed_path, sites, analysis))
    return records
