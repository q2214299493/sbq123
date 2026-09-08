from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from scripts.adsorption.build_fe110_adsorption import (
    Poscar,
    Site,
    anchor_cartesian_position,
    read_poscar,
    validate_adsorbate,
    write_poscar,
)
from scripts.workflow_geometry import expand_symbols

from .adsmind_common import load_yaml, read_json, require_ase_structure, write_json, write_jsonl


def site_from_record(record: dict[str, Any], slab: Poscar) -> Site:
    name = str(record.get("generator_site_name", record["site_class"]))
    frac = np.array([*record["fractional_xy"], float(np.max(slab.frac[:, 2]))], dtype=float)
    indices = tuple(int(value) - 1 for value in record.get("support_indices_1based", []))
    distance = record.get("support_distance_angstrom")
    return Site(name, frac, indices, None if distance is None else float(distance))


def generate_candidates(
    surface_path: Path,
    sites_path: Path,
    adsorbates: list[str],
    adsorbate_config_path: Path,
    output_root: Path,
    plan_path: Path,
    backend_mode: str = "no_relax",
) -> list[dict[str, Any]]:
    require_ase_structure(surface_path)
    slab = read_poscar(surface_path)
    site_payload = read_json(sites_path)
    config = load_yaml(adsorbate_config_path)
    rules = config["adsorbates"]
    plan = read_json(plan_path)
    planned = {str(item["species"]): item for item in plan.get("species_plans", [])}
    surface_name = str(site_payload["surface_name"])
    records: list[dict[str, Any]] = []
    site_records = list(site_payload.get("sites", []))
    for adsorbate in adsorbates:
        if adsorbate not in rules:
            records.append(generation_failure(surface_name, site_payload, adsorbate, "invalid_binding_atom"))
            continue
        species_plan = planned.get(adsorbate)
        if species_plan is None:
            records.append(generation_failure(surface_name, site_payload, adsorbate, "missing_evidence_gated_plan"))
            continue
        rule = rules[adsorbate]
        selected, rejected = select_planned_sites(species_plan, site_records)
        for motif, reason in rejected:
            failure = generation_failure(surface_name, site_payload, adsorbate, reason)
            failure["motif_id"] = motif.get("motif_id")
            records.append(failure)
        if not selected and not rejected:
            records.append(generation_failure(surface_name, site_payload, adsorbate, "no_build_ready_supported_motif"))
            continue
        for serial, (motif, site_record) in enumerate(selected, start=1):
            site = site_from_record(site_record, slab)
            structure, index_map = compose_candidate_structure(slab, site, adsorbate, rule, motif)
            candidate_id = f"{surface_name}_{motif['motif_id']}_{serial:04d}"
            folder = output_root / surface_name / adsorbate / candidate_id
            structure_path = folder / "POSCAR"
            write_poscar(structure_path, structure)
            metadata = candidate_metadata(
                candidate_id,
                surface_name,
                site_payload,
                adsorbate,
                rule,
                site_record,
                surface_path,
                structure_path,
                sum(slab.counts),
                backend_mode,
                index_map,
                motif,
            )
            write_json(folder / "metadata.json", metadata)
            records.append(metadata)
    write_jsonl(output_root / "candidates.jsonl", records)
    return records


def select_planned_sites(
    species_plan: dict[str, Any], site_records: list[dict[str, Any]]
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[tuple[dict[str, Any], str]]]:
    """Match build-ready motif identities to generated site records without collapsing orientations."""
    aliases = {
        "top": "top_Fe",
        "short_bridge": "bridge_FeFe_short",
        "long_bridge": "bridge_FeFe_long",
        "hollow": "hollow_FeFeFe",
    }
    by_class = {str(site["site_class"]): site for site in site_records}
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    rejected: list[tuple[dict[str, Any], str]] = []
    used: set[tuple[str, str]] = set()
    for motif in sorted(species_plan.get("candidates", []), key=lambda item: int(item.get("priority", 999))):
        if not motif.get("build_ready"):
            continue
        site_class = str(motif.get("generator_site_class") or aliases.get(str(motif.get("site_pattern")), motif.get("site_pattern")))
        if site_class not in by_class:
            rejected.append((motif, "planned_site_not_supported_by_generator"))
            continue
        configuration_id = str(motif.get("configuration_id") or motif.get("motif_id") or "")
        fingerprint = (site_class, configuration_id)
        if not configuration_id:
            rejected.append((motif, "planned_configuration_identity_missing"))
            continue
        if fingerprint in used:
            rejected.append((motif, "duplicate_planned_configuration"))
            continue
        used.add(fingerprint)
        selected.append((motif, by_class[site_class]))
    return selected, rejected


def compose_candidate_structure(
    slab: Poscar,
    site: Site,
    adsorbate: str,
    rule: dict[str, Any],
    motif: dict[str, Any] | None = None,
) -> tuple[Poscar, dict[str, Any]]:
    """Place one motif using Cartesian Å offsets and return explicit 0-based structure indices."""
    atom_symbols, relative, anchor_local, target = validate_adsorbate(adsorbate, rule)
    relative = rotate_relative_geometry(relative, float((motif or {}).get("orientation_degrees", 0.0)))
    anchor = anchor_cartesian_position(slab, site, target)
    adsorbate_frac = (anchor + relative) @ np.linalg.inv(slab.cell)
    adsorbate_frac[:, :2] %= 1.0
    slab_symbols = expanded_poscar_symbols(slab)
    species_order = ordered_unique([*slab.symbols, *rule["species_order"]])
    new_frac: list[np.ndarray] = []
    new_flags: list[tuple[str, str, str]] = []
    slab_indices: list[int] = []
    adsorbate_indices = [-1] * len(atom_symbols)
    original_to_structure: dict[int, int] = {}
    counts: list[int] = []
    for symbol in species_order:
        count_before = len(new_frac)
        for original, atom_symbol in enumerate(slab_symbols):
            if atom_symbol != symbol:
                continue
            original_to_structure[original] = len(new_frac)
            slab_indices.append(len(new_frac))
            new_frac.append(slab.frac[original].copy())
            new_flags.append(slab.flags[original])
        for local, atom_symbol in enumerate(atom_symbols):
            if atom_symbol != symbol:
                continue
            adsorbate_indices[local] = len(new_frac)
            new_frac.append(adsorbate_frac[local].copy())
            new_flags.append(("T", "T", "T"))
        counts.append(len(new_frac) - count_before)
    if any(index < 0 for index in adsorbate_indices):
        raise ValueError(f"{adsorbate}: failed to map every adsorbate atom into POSCAR groups")
    structure = Poscar(
        comment=f"{slab.comment} {adsorbate} {site.name}",
        cell=slab.cell.copy(),
        symbols=species_order,
        counts=counts,
        frac=np.asarray(new_frac),
        flags=new_flags,
    )
    return structure, {
        "slab_indices_structure_0based": slab_indices,
        "adsorbate_indices_structure_0based": adsorbate_indices,
        "anchor_index_structure_0based": adsorbate_indices[anchor_local],
        "slab_original_to_structure_0based": {str(key): value for key, value in original_to_structure.items()},
    }


def expanded_poscar_symbols(poscar: Poscar) -> list[str]:
    return expand_symbols(poscar.symbols, poscar.counts)


def rotate_relative_geometry(relative: np.ndarray, angle_degrees: float) -> np.ndarray:
    if angle_degrees == 0.0:
        return relative.copy()
    angle = np.deg2rad(angle_degrees)
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0.0], [np.sin(angle), np.cos(angle), 0.0], [0.0, 0.0, 1.0]])
    return relative @ rotation.T


def ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def generation_failure(surface_name: str, sites: dict[str, Any], adsorbate: str, reason: str) -> dict[str, Any]:
    return {
        "candidate_id": f"{surface_name}_{adsorbate}_not_generated",
        "surface_name": surface_name,
        "surface_family": sites["surface_family"],
        "adsorbate": adsorbate,
        "validation_passed": False,
        "needs_review": True,
        "confidence_level": "low",
        "reason_code": reason,
    }


def candidate_metadata(
    candidate_id: str,
    surface_name: str,
    sites: dict[str, Any],
    adsorbate: str,
    rule: dict[str, Any],
    site: dict[str, Any],
    surface_path: Path,
    structure_path: Path,
    slab_atom_count: int,
    backend_mode: str,
    index_map: dict[str, Any],
    motif: dict[str, Any],
) -> dict[str, Any]:
    """Create the candidate contract with Å geometry provenance and 0-based atom-index mappings."""
    rule_confidence = str(rule.get("default_confidence", "low"))
    if (
        sites["surface_family"] == "metallic_fe"
        and rule.get("class") in {"simple", "C1_oxygenate"}
        and not rule.get("isomer_sensitive", False)
    ):
        rule_confidence = "high"
    confidence = lowest_confidence(
        rule_confidence,
        str(sites.get("confidence_level", "low")),
        str(site.get("confidence_level", "low")),
    )
    return {
        "candidate_id": candidate_id,
        "surface_name": surface_name,
        "surface_family": sites["surface_family"],
        "adsorbate": adsorbate,
        "motif_id": motif["motif_id"],
        "configuration_id": motif.get("configuration_id", motif["motif_id"]),
        "orientation_degrees": float(motif.get("orientation_degrees", 0.0)),
        "planned_site_id": site["site_id"],
        "planned_site_class": site["site_class"],
        "planned_site_fractional_xy": site["fractional_xy"],
        "planned_binding_atom": rule["anchor_atom"],
        "anchor_index_adsorbate_0based": int(rule["anchor_index"]),
        "anchor_index_structure_0based": index_map["anchor_index_structure_0based"],
        "slab_atom_count": slab_atom_count,
        "slab_indices_structure_0based": index_map["slab_indices_structure_0based"],
        "adsorbate_indices_structure_0based": index_map["adsorbate_indices_structure_0based"],
        "slab_original_to_structure_0based": index_map["slab_original_to_structure_0based"],
        "atom_symbols": rule["atom_symbols"],
        "preferred_binding_atoms": rule["preferred_binding_atoms"],
        "forbidden_binding_atoms": rule.get("forbidden_binding_atoms", []),
        "dissociation_check": bool(rule.get("dissociation_check", False)),
        "target_dissociative": bool(rule.get("target_dissociative", False)),
        "site_label_source": sites.get("site_label_source", "automatic_detector"),
        "atom_labels": sites.get("atom_labels", {}),
        "surface_tags": sites.get("surface_tags", []),
        "high_risk_sites": sites.get("high_risk_sites", {}),
        "site_explicitly_validated": bool(site.get("explicitly_validated", False)),
        "backend_mode": backend_mode,
        "initial_structure": str(structure_path),
        "surface_structure": str(surface_path),
        "confidence_level": confidence,
        "needs_review": bool(sites.get("needs_review", False) or site.get("needs_review", False)),
        "reason_code": site.get("reason_code", "generated"),
    }


def lowest_confidence(*values: str) -> str:
    rank = {"high": 2, "medium": 1, "low": 0}
    return min(values, key=lambda value: rank.get(value, 0))
