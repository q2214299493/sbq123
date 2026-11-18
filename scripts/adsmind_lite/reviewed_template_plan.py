"""Plan generation from reviewed local full-slab templates."""
from __future__ import annotations

import re

import numpy as np
from ase.data import atomic_numbers

from scripts.adsorption.build_fe110_adsorption import Poscar
from scripts.workflow_geometry import expand_symbols

from .adsmind_common import SINGLE_ANCHOR_MODES, SITE_CLASS_MAP, ordered_unique
from .evidence_lifecycle import record_subject, require_transferable
from .reviewed_templates import multi_anchor_mapping, read_reviewed_template


PLAN_SOURCE = "reviewed_local_template_bundle"


def _reference_rule(reference: dict) -> dict:
    if not isinstance(reference, dict) or set(reference) != {"atom_symbols", "relative_cartesian_angstrom"}:
        raise ValueError("reviewed molecular reference needs atom symbols and Cartesian Å coordinates")
    symbols = reference["atom_symbols"]
    if not isinstance(symbols, list) or not symbols or any(
        not isinstance(symbol, str) or symbol not in atomic_numbers for symbol in symbols
    ):
        raise ValueError("invalid reviewed molecular atom symbols")
    positions = np.asarray(reference["relative_cartesian_angstrom"], dtype=float)
    if positions.shape != (len(symbols), 3) or not np.isfinite(positions).all():
        raise ValueError("invalid reviewed molecular reference coordinates")
    return {
        **reference,
        "species_order": list(dict.fromkeys(symbols)),
        "preferred_binding_atoms": symbols,
        "default_confidence": "low",
    }


def _reviewed_motif(motif: dict, species: str, rule: dict) -> dict:
    required = {
        "motif_id", "site_pattern", "binding_mode", "binding_atoms", "generator_site_class",
        "binding_atom_indices_zero_based", "reviewed_structure_template", "geometry_origin",
    }
    if not isinstance(motif, dict) or set(motif) != required or any(
        not isinstance(motif[key], str) or not motif[key].strip()
        for key in ("motif_id", "site_pattern", "binding_mode", "generator_site_class")
    ):
        raise ValueError("invalid reviewed full-pose motif fields")
    if motif["geometry_origin"] not in ("archived_local", "literature_guided", "local_construction"):
        raise ValueError("invalid reviewed motif geometry origin")
    if motif["binding_mode"].strip().casefold() in SINGLE_ANCHOR_MODES | {"monodentate"}:
        raise ValueError("reviewed full-pose import requires multiple mapped anchors")
    labels = motif["binding_atoms"]
    if not isinstance(labels, list) or any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError("invalid reviewed binding atom labels")
    multi_anchor_mapping(species, rule, motif)
    read_reviewed_template(species, motif["reviewed_structure_template"])
    return {**motif, "build_ready": True, "template_required": True}


def resolve_reviewed_template_plan(bundle: dict) -> dict:
    """Check the supplied review. A file path or a template ID alone grants nothing."""
    if not isinstance(bundle, dict) or set(bundle) != {
        "species", "surface", "slab_sha256", "molecular_reference", "motifs", "evidence",
    }:
        raise ValueError("invalid reviewed template bundle fields")
    species, surface = bundle["species"], bundle["surface"]
    if not isinstance(species, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_+().-]*", species):
        raise ValueError("invalid exact species label for reviewed templates")
    if surface != "Fe110":
        raise ValueError("reviewed multi-anchor template import supports Fe110")
    digest = bundle["slab_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("reviewed templates require the exact clean slab SHA256")
    evidence = bundle["evidence"]
    if evidence is None:
        raise ValueError("accepted candidate review is required for the template bundle")
    claim = evidence.get("claim") if isinstance(evidence, dict) else None
    if not isinstance(claim, dict) or claim.get("record_sha256") != record_subject(bundle):
        raise ValueError("reviewed template bundle differs from the reviewed subject")
    require_transferable(evidence, {
        "domain": "surface_adsorption",
        "scope": "candidate_guidance",
        "compatibility": {"species": species, "surface": surface, "slab_sha256": digest},
    })
    rule = _reference_rule(bundle["molecular_reference"])
    if not isinstance(bundle["motifs"], list):
        raise ValueError("reviewed motifs must be a list")
    candidates = [_reviewed_motif(motif, species, rule) for motif in bundle["motifs"]]
    if not candidates or len({item["motif_id"] for item in candidates}) != len(candidates):
        raise ValueError("reviewed templates require distinct motif IDs")
    return {
        "species": species, "surface": surface, "decision": "READY", "confidence": "low",
        "plan_source": PLAN_SOURCE, "reviewed_template_bundle": bundle, "candidates": candidates,
    }


def reviewed_template_rule(plan: dict, configured: dict | None) -> dict:
    rule = _reference_rule(plan["reviewed_template_bundle"]["molecular_reference"])
    if configured is None:
        return rule
    if configured["atom_symbols"] != rule["atom_symbols"]:
        raise ValueError("reviewed reference and configured species atom order differ")
    return {**rule, **configured}


def reviewed_pose_matches_output(output: Poscar, record: dict, motif: dict, rule: dict) -> bool:
    """Compare the parsed output with the reviewed pose in POSCAR order."""
    template, _ = read_reviewed_template(record["adsorbate"], motif["reviewed_structure_template"])
    symbols = expand_symbols(template.symbols, template.counts)
    slab_count = len(symbols) - len(rule["atom_symbols"])
    order = ordered_unique(symbols[:slab_count] + rule["species_order"])
    permutation = [index for symbol in order for index, value in enumerate(symbols) if value == symbol]
    if (
        expand_symbols(output.symbols, output.counts) != [symbols[index] for index in permutation]
        or not np.allclose(output.cell, template.cell, atol=1e-8, rtol=0)
        or not np.allclose(output.frac, template.frac[permutation], atol=1e-8, rtol=0)
        or [tuple(flag.upper() for flag in flags) for flags in output.flags]
        != [tuple(flag.upper() for flag in template.flags[index]) for index in permutation]
    ):
        return False
    output_indices = {original: index for index, original in enumerate(permutation)}
    anchors = motif["binding_atom_indices_zero_based"]
    primary = anchors[motif["binding_atoms"][0]]
    declared_site = motif["generator_site_class"].strip().casefold()
    expected_site = SITE_CLASS_MAP.get(declared_site, declared_site)
    return (
        record.get("slab_atom_count") == slab_count
        and record.get("slab_indices_structure_0based")
        == [index for index, original in enumerate(permutation) if original < slab_count]
        and record.get("adsorbate_indices_structure_0based")
        == [output_indices[index] for index in range(slab_count, len(symbols))]
        and record.get("binding_atom_indices_structure_0based")
        == {label: output_indices[slab_count + index] for label, index in anchors.items()}
        and record.get("anchor_index_adsorbate_0based") == primary
        and record.get("anchor_index_structure_0based") == output_indices[slab_count + primary]
        and str(record.get("planned_site_class")).casefold() == expected_site.casefold()
    )
