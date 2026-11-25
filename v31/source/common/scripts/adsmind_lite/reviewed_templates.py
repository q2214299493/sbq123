"""Read hash-bound templates and validate explicitly mapped full adsorption poses."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from scripts.adsorption.build_fe110_adsorption import Poscar, parse_poscar_text
from scripts.scientific_validation import finite_number
from scripts.workflow_geometry import expand_symbols


def read_reviewed_template(name: str, descriptor: dict) -> tuple[Poscar, dict[str, Any]]:
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
    except (UnicodeError, ValueError, IndexError, np.linalg.LinAlgError) as exc:
        raise ValueError(f"{name}: unsupported_reviewed_template_geometry: {exc}") from exc
    return template, {
        "type": "reviewed_structure_template", "path": str(path), "sha256": digest,
        "coordinate_units": "angstrom",
    }


def multi_anchor_mapping(name: str, rule: dict, motif: dict) -> dict[str, int]:
    """Labels identify reviewed atoms; repeated elements never imply an index."""
    labels = motif.get("binding_atoms", [])
    mapping = motif.get("binding_atom_indices_zero_based")
    if (not isinstance(labels, list) or len(labels) < 2 or len(set(labels)) != len(labels)
            or not isinstance(mapping, dict) or set(mapping) != set(labels)
            or any(type(index) is not int or not 0 <= index < len(rule["atom_symbols"])
                   for index in mapping.values()) or len(set(mapping.values())) != len(labels)):
        raise ValueError(f"{name}: explicit_multi_anchor_mapping_required")
    if any(rule["atom_symbols"][index] in rule.get("forbidden_binding_atoms", []) for index in mapping.values()):
        raise ValueError(f"{name}: invalid_binding_atom")
    if rule["atom_symbols"][mapping[labels[0]]] not in rule["preferred_binding_atoms"]:
        raise ValueError(f"{name}: invalid_primary_binding_atom")
    if not motif.get("generator_site_class"):
        raise ValueError(f"{name}: multi_anchor_primary_generator_site_class_required")
    return {label: mapping[label] for label in labels}


def full_pose_geometry(name: str, slab: Poscar, rule: dict, motif: dict) -> tuple[np.ndarray, dict]:
    """Keep the reviewed slab-frame pose; no single-anchor height or rotation."""
    if finite_number(motif.get("orientation_degrees", 0.0), "orientation_degrees") != 0.0:
        raise ValueError(f"{name}: reviewed_template_full_pose_cannot_be_rotated")
    template, source = read_reviewed_template(name, motif.get("reviewed_structure_template"))
    slab_count = sum(slab.counts)
    symbols = expand_symbols(slab.symbols, slab.counts) + list(rule["atom_symbols"])
    if expand_symbols(template.symbols, template.counts) != symbols:
        raise ValueError(f"{name}: reviewed_template_requires_slab_then_configured_adsorbate_order")
    template_flags = [tuple(value.upper() for value in flag) for flag in template.flags]
    slab_flags = [tuple(value.upper() for value in flag) for flag in slab.flags]
    if (not np.allclose(template.cell, slab.cell, rtol=0.0, atol=1e-8)
            or not np.allclose(template.frac[:slab_count], slab.frac, rtol=0.0, atol=1e-8)
            or template_flags[:slab_count] != slab_flags):
        raise ValueError(f"{name}: reviewed_template_slab_mismatch")
    if any(flag != ("T", "T", "T") for flag in template_flags[slab_count:]):
        raise ValueError(f"{name}: reviewed_template_adsorbate_constraints_not_supported")
    return template.frac[slab_count:].copy(), {**source, "format": "slab_adsorbate_POSCAR"}
