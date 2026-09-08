from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from ase import Atoms

from scripts.adsorption.build_fe110_adsorption import (
    Poscar,
    center_score,
    choose_pair_representative,
    cluster_pairs,
    deduplicate_points,
    generate_sites,
    identify_top_layer,
    inplane_fractional_distance,
    minimum_image_delta,
    pair_candidates,
    read_poscar,
)

from .adsmind_common import SITE_CLASS_MAP, load_yaml, read_json, require_ase_structure, standardized_site_id, surface_family_config


def detect_surface_sites(
    structure_path: Path,
    surface_name: str,
    surface_family: str,
    surfaces_config: Path,
    site_rules_config: Path,
    explicit_sites: Path | None = None,
) -> dict[str, Any]:
    atoms = require_ase_structure(structure_path)
    family = surface_family_config(surfaces_config, surface_family)
    rules = load_yaml(site_rules_config)
    orientation = metallic_orientation(surface_name)
    if surface_family != "metallic_fe":
        return detect_explicit_or_gated_sites(atoms, structure_path, surface_name, surface_family, family, explicit_sites)
    if orientation not in {"Fe110", "Fe100", "Fe111"}:
        return detect_explicit_or_gated_sites(atoms, structure_path, surface_name, surface_family, family, explicit_sites)
    detector = rules["metallic_fe"][orientation]
    if not detector.get("implemented"):
        raise ValueError(f"{orientation} detector is disabled")
    defaults = rules["defaults"]
    poscar = read_poscar(structure_path)
    if orientation != "Fe110":
        return detect_generic_metallic_sites(poscar, atoms, structure_path, surface_name, orientation, defaults)
    sites, top_indices = generate_sites(
        poscar,
        z_tolerance=float(defaults["exposed_layer_tolerance_angstrom"]),
        pair_tolerance=float(defaults["pair_class_tolerance_angstrom"]),
        site_tolerance=float(defaults["site_deduplication_tolerance_angstrom"]),
    )
    records: list[dict[str, Any]] = []
    for serial, name in enumerate(("top", "short_bridge", "long_bridge", "hollow"), start=1):
        site = sites[name]
        site_class = SITE_CLASS_MAP[name]
        pattern = "Fe" if name == "top" else ("Fe-Fe-Fe" if name == "hollow" else "Fe-Fe")
        records.append(
            {
                "site_id": standardized_site_id(surface_name, site_class, pattern, serial),
                "site_class": site_class,
                "generator_site_name": name,
                "atom_type_pattern": pattern,
                "fractional_xy": [float(site.frac[0]), float(site.frac[1])],
                "support_indices_1based": [int(index + 1) for index in site.support_indices],
                "support_distance_angstrom": None if site.support_distance is None else float(site.support_distance),
                "confidence_level": "high",
                "needs_review": False,
                "reason_code": "accepted",
            }
        )
    return {
        "version": 1,
        "surface_name": surface_name,
        "surface_family": surface_family,
        "source_structure": str(structure_path),
        "atom_count": len(atoms),
        "top_layer_indices_1based": [int(index + 1) for index in top_indices],
        "status": "PASS",
        "confidence_level": "high",
        "needs_review": False,
        "sites": records,
    }


def metallic_orientation(surface_name: str) -> str:
    compact = surface_name.lower().replace("(", "").replace(")", "").replace("_", "").replace("-", "")
    for orientation in ("110", "100", "111"):
        if compact == f"fe{orientation}":
            return f"Fe{orientation}"
    return ""


def base_site_record(
    surface_name: str,
    site_class: str,
    generator_name: str,
    pattern: str,
    frac: np.ndarray,
    support_indices: Iterable[int],
    distance: float | None,
    serial: int,
) -> dict[str, Any]:
    return {
        "site_id": standardized_site_id(surface_name, site_class, pattern, serial),
        "site_class": site_class,
        "generator_site_name": generator_name,
        "atom_type_pattern": pattern,
        "fractional_xy": [float(frac[0]), float(frac[1])],
        "support_indices_1based": [int(index + 1) for index in support_indices],
        "support_distance_angstrom": distance,
        "confidence_level": "high",
        "needs_review": False,
        "reason_code": "accepted",
    }


def detect_generic_metallic_sites(
    poscar: Poscar,
    atoms: Atoms,
    structure_path: Path,
    surface_name: str,
    orientation: str,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    top = identify_top_layer(poscar, float(defaults["exposed_layer_tolerance_angstrom"]))
    groups = cluster_pairs(pair_candidates(poscar, top), float(defaults["pair_class_tolerance_angstrom"]))
    groups = [group for group in groups if np.mean([candidate.distance for candidate in group]) > 1.0]
    if not groups:
        raise ValueError(f"{orientation}: no exposed-layer Fe-Fe pair class found")
    shortest = choose_pair_representative(poscar.cell, groups[0])
    top_index = min(top.tolist(), key=lambda index: center_score(poscar.cell, poscar.frac[index]))
    records = [
        base_site_record(surface_name, "top_Fe", "top", "Fe", poscar.frac[top_index], (top_index,), None, 1),
        base_site_record(
            surface_name,
            "bridge_FeFe_short",
            "short_bridge",
            "Fe-Fe",
            shortest.midpoint,
            shortest.indices,
            float(shortest.distance),
            2,
        ),
    ]
    if orientation == "Fe100":
        records.append(fe100_hollow_record(poscar, top, groups, surface_name))
    else:
        records.append(fe111_hollow_record(poscar, top, groups[0], surface_name, float(defaults["site_deduplication_tolerance_angstrom"])))
    return {
        "version": 1,
        "surface_name": surface_name,
        "surface_family": "metallic_fe",
        "source_structure": str(structure_path),
        "atom_count": len(atoms),
        "top_layer_indices_1based": [int(index + 1) for index in top],
        "status": "PASS",
        "confidence_level": "high",
        "needs_review": False,
        "detector": f"{orientation.lower()}_exposed_layer_graph",
        "sites": records,
    }


def fe100_hollow_record(poscar: Poscar, top: np.ndarray, groups: list[list[Any]], surface_name: str) -> dict[str, Any]:
    if len(groups) < 2:
        raise ValueError("Fe100: fourfold hollow requires a second Fe-Fe distance class")
    diagonal = choose_pair_representative(poscar.cell, groups[1])
    center = diagonal.midpoint
    distances = sorted((inplane_fractional_distance(poscar.cell, center, poscar.frac[index]), index) for index in top.tolist())
    support = tuple(index for _, index in distances[:4])
    if distances[3][0] - distances[0][0] > 0.10:
        raise ValueError("Fe100: candidate does not have four equivalent top-layer Fe neighbors")
    return base_site_record(surface_name, "hollow_FeFeFeFe", "hollow", "Fe-Fe-Fe-Fe", center, support, None, 3)


def fe111_hollow_record(
    poscar: Poscar,
    top: np.ndarray,
    shortest_group: list[Any],
    surface_name: str,
    deduplication_tolerance: float,
) -> dict[str, Any]:
    shortest = float(np.mean([candidate.distance for candidate in shortest_group]))
    centers: list[np.ndarray] = []
    supports: list[tuple[int, int, int]] = []
    for first, second, third in itertools.combinations(top.tolist(), 3):
        second_delta = minimum_image_delta(poscar.frac[second] - poscar.frac[first])
        third_delta = minimum_image_delta(poscar.frac[third] - poscar.frac[first])
        sides = (
            float(np.linalg.norm(second_delta @ poscar.cell)),
            float(np.linalg.norm(third_delta @ poscar.cell)),
            float(np.linalg.norm((third_delta - second_delta) @ poscar.cell)),
        )
        if max(abs(side - shortest) for side in sides) > 0.10:
            continue
        centers.append((poscar.frac[first] + (second_delta + third_delta) / 3.0) % 1.0)
        supports.append((first, second, third))
    unique = deduplicate_points(poscar.cell, centers, deduplication_tolerance)
    if not unique:
        raise ValueError("Fe111: no threefold hollow triangle found")
    center = min(unique, key=lambda point: center_score(poscar.cell, point))
    support = next(indices for point, indices in zip(centers, supports, strict=True) if np.allclose(point, center))
    return base_site_record(surface_name, "hollow_FeFeFe", "hollow", "Fe-Fe-Fe", center, support, None, 3)


def detect_explicit_or_gated_sites(
    atoms: Atoms,
    structure_path: Path,
    surface_name: str,
    surface_family: str,
    family_config: dict[str, Any],
    explicit_sites: Path | None,
) -> dict[str, Any]:
    if explicit_sites is not None:
        payload = load_yaml(explicit_sites) if explicit_sites.suffix.lower() in {".yaml", ".yml"} else read_json(explicit_sites)
        return sites_from_manifest(atoms, structure_path, surface_name, surface_family, family_config, payload)
    return {
        "version": 1,
        "surface_name": surface_name,
        "surface_family": surface_family,
        "source_structure": str(structure_path),
        "atom_count": len(atoms),
        "status": "NEEDS_REVIEW",
        "confidence_level": family_config["confidence_default"],
        "needs_review": True,
        "site_label_source": "none",
        "reason_code": "explicit_site_label_required",
        "sites": [],
    }


def sites_from_manifest(
    atoms: Atoms,
    structure_path: Path,
    surface_name: str,
    surface_family: str,
    family_config: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    if manifest.get("surface_name") != surface_name or manifest.get("surface_family") != surface_family:
        raise ValueError("site manifest surface identity does not match CLI arguments")
    labels = normalize_atom_labels(manifest.get("atom_labels", {}), len(atoms))
    enabled = set(manifest.get("enabled_site_classes", []))
    allowed = set(family_config["site_classes"])
    if not enabled or not enabled <= allowed:
        raise ValueError("site manifest enabled_site_classes are empty or unsupported")
    explicit_sites = manifest.get("explicit_sites", [])
    if not isinstance(explicit_sites, list):
        raise ValueError("site manifest explicit_sites must be a list")
    default_confidence = str(manifest.get("default_confidence", family_config["confidence_default"]))
    high_risk = manifest.get("high_risk_sites", {})
    sites = [
        manifest_site_record(surface_name, surface_family, site, serial, enabled, labels, high_risk, default_confidence, len(atoms))
        for serial, site in enumerate(explicit_sites, start=1)
    ]
    needs_review = any(site["needs_review"] for site in sites) or not sites
    status = "PASS_WITH_REVIEW" if needs_review else "PASS"
    reason = "explicit_site_label_required" if not sites else ("needs_review_high_risk_site" if needs_review else "accepted")
    return {
        "version": 1,
        "surface_name": surface_name,
        "surface_family": surface_family,
        "source_structure": str(structure_path),
        "atom_count": len(atoms),
        "status": status,
        "confidence_level": default_confidence,
        "needs_review": needs_review,
        "site_label_source": "explicit_manifest",
        "atom_labels": {str(index): role for index, role in labels.items()},
        "high_risk_sites": high_risk,
        "surface_tags": manifest.get("surface_tags", []),
        "reason_code": reason,
        "sites": sites,
    }


def normalize_atom_labels(raw: Any, atom_count: int) -> dict[int, str]:
    if not isinstance(raw, dict):
        raise ValueError("site manifest atom_labels must be a mapping of 1-based indices to roles")
    labels: dict[int, str] = {}
    for key, value in raw.items():
        index = int(key)
        if not 1 <= index <= atom_count:
            raise ValueError(f"atom label index {index} is outside the structure")
        labels[index] = str(value)
    return labels


def manifest_site_record(
    surface_name: str,
    surface_family: str,
    site: dict[str, Any],
    serial: int,
    enabled: set[str],
    labels: dict[int, str],
    high_risk: dict[str, Any],
    default_confidence: str,
    atom_count: int,
) -> dict[str, Any]:
    site_class = str(site["site_class"])
    if site_class not in enabled:
        raise ValueError(f"site class {site_class} is not enabled by the manifest")
    fractional_xy = [float(value) for value in site["fractional_xy"]]
    if len(fractional_xy) != 2:
        raise ValueError("explicit site fractional_xy requires two values")
    support = [int(value) for value in site.get("support_indices_1based", [])]
    if any(index < 1 or index > atom_count for index in support):
        raise ValueError(f"{site_class}: support index is outside the structure")
    roles = {labels.get(index, "") for index in support}
    if site.get("site_role"):
        roles.add(str(site["site_role"]))
    explicit_validated = bool(site.get("explicitly_validated", False))
    confidence, needs_review, reason = manifest_site_gate(
        surface_family,
        site_class,
        roles,
        high_risk,
        default_confidence,
        explicit_validated,
    )
    pattern = str(site.get("atom_type_pattern", "-".join(sorted(role for role in roles if role)) or "explicit"))
    return {
        "site_id": standardized_site_id(surface_name, site_class, pattern, serial),
        "site_class": site_class,
        "generator_site_name": str(site.get("generator_site_name", site_class)),
        "atom_type_pattern": pattern,
        "fractional_xy": fractional_xy,
        "support_indices_1based": support,
        "site_role": site.get("site_role"),
        "support_distance_angstrom": site.get("support_distance_angstrom"),
        "explicitly_validated": explicit_validated,
        "confidence_level": confidence,
        "needs_review": needs_review,
        "reason_code": reason,
    }


def manifest_site_gate(
    surface_family: str,
    site_class: str,
    support_roles: set[str],
    high_risk: dict[str, Any],
    default_confidence: str,
    explicitly_validated: bool,
) -> tuple[str, bool, str]:
    if surface_family == "iron_carbide" and "C_lattice" in site_class and "C_lattice" not in support_roles:
        return "low", True, "lattice_adsorbate_atom_confusion"
    if surface_family == "iron_oxide":
        required_role = oxide_required_role(site_class)
        if required_role and required_role not in support_roles:
            return "low", True, "explicit_site_label_required"
        if site_class == "oxygen_vacancy":
            vacancy = high_risk.get("oxygen_vacancy", {})
            if not vacancy.get("explicitly_tagged"):
                return "low", True, "oxygen_vacancy_not_tagged"
            if not explicitly_validated or not vacancy.get("explicitly_validated"):
                return "low", True, "needs_review_high_risk_site"
        hydroxylated = high_risk.get("hydroxylated_surface", {})
        if hydroxylated.get("present") and not hydroxylated.get("explicitly_validated"):
            return "low", True, "needs_review_high_risk_site"
    confidence = "medium" if surface_family in {"iron_carbide", "iron_oxide"} else default_confidence
    return confidence, not explicitly_validated, "accepted" if explicitly_validated else "needs_review_high_risk_site"


def oxide_required_role(site_class: str) -> str | None:
    mapping = {
        "top_Fe_oct": "Fe_oct",
        "top_Fe_tet": "Fe_tet",
        "bridge_FeO_lattice": "O_lattice",
        "hollow_FeFeO_lattice": "O_lattice",
        "oxygen_vacancy": "vacancy_O",
    }
    return mapping.get(site_class)
