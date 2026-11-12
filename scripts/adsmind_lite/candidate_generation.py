from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from scripts.adsorption.build_fe110_adsorption import (
    Poscar,
    Site,
    anchor_cartesian_position,
    parse_poscar_text,
    read_poscar,
    validate_adsorbate,
    write_poscar,
)
from scripts.workflow_geometry import expand_symbols
from scripts.scientific_validation import finite_number

from .adsmind_common import load_yaml, read_json, require_ase_structure, write_json, write_jsonl
from .motif_coverage import (
    SITE_PATTERN_ALIASES, generation_coverage_rules, initial_motif_identity,
    review_initial_motif_coverage, validate_generation_plan,
)


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
    if plan.get("surface_name", surface_name) != surface_name:
        raise ValueError("candidate plan surface does not match the site manifest")
    prepared = _prepare_generation_batch(adsorbates, planned, rules, surface_name, site_records)
    pending = []
    for adsorbate in adsorbates:
        rule = rules[adsorbate]
        for serial, (motif, site_record) in enumerate(prepared[adsorbate], start=1):
            site = site_from_record(site_record, slab)
            structure, index_map = compose_candidate_structure(slab, site, adsorbate, rule, motif)
            candidate_id = f"{surface_name}_{motif['motif_id']}_{serial:04d}"
            folder = output_root / surface_name / adsorbate / candidate_id
            structure_path = folder / "POSCAR"
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
            pending.append((structure_path, structure, metadata))
    # Resolve every pose/metadata error before publishing the first structure.
    for structure_path, structure, metadata in pending:
        write_poscar(structure_path, structure)
        write_json(structure_path.with_name("metadata.json"), metadata)
        records.append(metadata)
    write_jsonl(output_root / "candidates.jsonl", records)
    return records


def _prepare_generation_batch(adsorbates: list[str], planned: dict, rules: dict, surface: str, site_records: list) -> dict:
    """Check the whole requested batch before publishing any candidate POSCAR."""
    coverage_rules = generation_coverage_rules()
    prepared = {}
    for species in adsorbates:
        if species not in rules:
            raise ValueError(f"{species}: invalid_binding_atom; no candidates generated")
        if species not in planned:
            raise ValueError(f"{species}: missing_evidence_gated_plan; no candidates generated")
        reviewed = validate_generation_plan(planned[species], species, surface, coverage_rules)
        if any(item.get("build_ready") is not True for item in reviewed["candidates"]):
            raise ValueError(f"{species}: reviewed_structure_template_required; no candidates generated")
        for motif in reviewed["candidates"]:
            motif_id = motif.get("motif_id")
            if not isinstance(motif_id, str) or not motif_id.strip() or any(char in motif_id for char in ("/", "\\", ":", "\0")):
                raise ValueError(f"{species}: invalid motif_id; no candidates generated")
            finite_number(motif.get("orientation_degrees", 0.0), "orientation_degrees")
            _require_supported_binding(species, rules[species], motif)
        selected, rejected = select_planned_sites(reviewed, site_records)
        if rejected:
            raise ValueError(f"{species}: {rejected[0][1]}; no candidates generated")
        selected_plan = review_initial_motif_coverage(
            {**reviewed, "candidates": [motif for motif, _ in selected]}, coverage_rules, surface_name=surface,
        )
        if selected_plan["initial_motif_coverage"]["status"] != "PASS":
            raise ValueError(f"{species}: initial_motif_coverage shortfall after site selection; no candidates generated")
        prepared[species] = selected
    return prepared


def select_planned_sites(
    species_plan: dict[str, Any], site_records: list[dict[str, Any]]
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[tuple[dict[str, Any], str]]]:
    """Match build-ready motif identities to generated site records without collapsing orientations."""
    by_class = {str(site["site_class"]): site for site in site_records}
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    rejected: list[tuple[dict[str, Any], str]] = []
    used: set[tuple[str, str]] = set()
    for motif in sorted(species_plan.get("candidates", []), key=lambda item: int(item.get("priority", 999))):
        if not motif.get("build_ready"):
            continue
        pattern = str(motif.get("generator_site_class") or motif.get("site_pattern"))
        site_class = SITE_PATTERN_ALIASES.get(pattern.strip().casefold(), pattern)
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


def _require_supported_binding(name: str, rule: dict[str, Any], motif: dict[str, Any] | None) -> None:
    identity = initial_motif_identity(motif) if motif is not None else None
    if rule.get("anchor_mode", "atom") != "atom" or (motif is not None and (
        identity is None or identity["binding_mode"] != "monodentate"
        or identity["binding_atoms"] != [rule["anchor_atom"]]
    )):
        raise ValueError(f"{name}: binding_mode_not_supported_by_generator; only the configured single-atom anchor is implemented")


def _candidate_geometry(
    name: str, rule: dict[str, Any], motif: dict[str, Any] | None,
) -> tuple[list[str], np.ndarray, int | None, float, dict[str, Any]]:
    """Consume the same reviewed bytes whose hash is recorded in provenance."""
    _require_supported_binding(name, rule, motif)
    motif = motif or {}
    geometry_source = {"type": "configured_adsorbate_geometry", "coordinate_units": "angstrom"}
    if "reviewed_structure_template" not in motif:
        if motif.get("template_required") or motif.get("build_mode") == "reviewed_structure_template":
            raise ValueError(f"{name}: reviewed_structure_template_required; a motif ID is not a geometry template")
        effective_rule = rule
    else:
        descriptor = motif["reviewed_structure_template"]
        if (not isinstance(descriptor, dict) or set(descriptor) != {"path", "sha256"}
                or not isinstance(descriptor["path"], str) or not descriptor["path"]
                or not isinstance(descriptor["sha256"], str)):
            raise ValueError(f"{name}: unsupported_reviewed_template_descriptor; require only path and sha256")
        path = Path(descriptor["path"])
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"{name}: reviewed_template_unreadable: {path}") from exc
        digest = hashlib.sha256(content).hexdigest()
        if digest != descriptor["sha256"]:
            raise ValueError(f"{name}: reviewed_template_sha256_mismatch: {path}")
        try:
            text = content.decode("utf-8")
            lines = text.splitlines()
            mode = 8 if lines[7].strip().lower().startswith("s") else 7
            if lines[mode].strip().lower()[:1] not in {"d", "c"}:
                raise ValueError("template coordinates must be Direct or Cartesian")
            template = parse_poscar_text(text, str(path))
            if any(count <= 0 for count in template.counts):
                raise ValueError("template requires positive species counts")
            if (not np.isfinite(template.cell).all() or np.linalg.det(template.cell) == 0.0
                    or not np.isfinite(template.frac).all()):
                raise ValueError("template coordinates and cell must be finite and nonsingular")
            if expanded_poscar_symbols(template) != list(rule["atom_symbols"]):
                raise ValueError("require adsorbate-only POSCAR in configured atom order; slab templates need explicit mapping")
            if any(tuple(value.upper() for value in flag) != ("T", "T", "T") for flag in template.flags):
                raise ValueError("template atom constraints are not supported")
            coordinates = template.frac @ template.cell
            anchor_index = int(rule["anchor_index"])
            relative = coordinates - coordinates[anchor_index]
            effective_rule = {**rule, "relative_cartesian_angstrom": relative.tolist()}
        except (UnicodeError, ValueError, IndexError, np.linalg.LinAlgError) as exc:
            raise ValueError(f"{name}: unsupported_reviewed_template_geometry: {exc}") from exc
        geometry_source = {
            "type": "reviewed_structure_template", "path": str(path), "sha256": digest,
            "format": "adsorbate_only_POSCAR", "coordinate_units": "angstrom",
        }
    atom_symbols, relative, anchor_local, target = validate_adsorbate(name, effective_rule)
    if not np.isfinite(relative).all():
        raise ValueError(f"{name}: adsorbate coordinates must be finite")
    return atom_symbols, relative, anchor_local, target, geometry_source


def compose_candidate_structure(
    slab: Poscar,
    site: Site,
    adsorbate: str,
    rule: dict[str, Any],
    motif: dict[str, Any] | None = None,
) -> tuple[Poscar, dict[str, Any]]:
    """Place one motif using Cartesian Å offsets and return explicit 0-based structure indices."""
    atom_symbols, relative, anchor_local, target, geometry_source = _candidate_geometry(adsorbate, rule, motif)
    relative = rotate_relative_geometry(relative, finite_number((motif or {}).get("orientation_degrees", 0.0), "orientation_degrees"))
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
        "geometry_source": geometry_source,
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
        "initial_motif": initial_motif_identity(motif),
        "geometry_source": index_map["geometry_source"],
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
