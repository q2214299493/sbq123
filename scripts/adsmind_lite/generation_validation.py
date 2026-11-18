"""Initial-pose sanity and actual binding-site diversity, before any output."""
from __future__ import annotations

import numpy as np
from ase import Atoms

from scripts.adsorption.build_fe110_adsorption import fe110_rule_defaults, fe110_site_centers, nearest_fe110_site_centers
from scripts.runtime_resources import resource_path
from scripts.workflow_geometry import expand_symbols, minimum_image_delta_xy

from .adsmind_common import SITE_CLASS_MAP, load_yaml
from .motif_coverage import generation_coverage_rules
from .relaxed_analysis import (
    classify_manifest_site, connectivity_edges, hard_contact_distance,
    structure_indices, validate_one_candidate,
)
from .site_detection import metallic_orientation


def pose_atoms(pose):
    return Atoms(expand_symbols(pose.symbols, pose.counts), scaled_positions=pose.frac,
                 cell=pose.cell, pbc=(True, True, False))


def molecular_geometry(atoms, indices, rule, analysis):
    """Preserve configured molecular connectivity and bound initial bond distortion."""
    connectivity = analysis["connectivity"]
    minimum = float(connectivity["minimum_bond_distance_angstrom"])
    scale = float(connectivity["covalent_radius_scale"])
    edges = connectivity_edges(atoms, indices, scale, minimum)
    if "relative_cartesian_angstrom" not in rule:
        raise ValueError("initial_molecular_reference_required")
    reference = Atoms(rule["atom_symbols"], positions=rule["relative_cartesian_angstrom"])
    reference_edges = connectivity_edges(reference, list(range(len(reference))), scale, minimum)
    if edges != reference_edges:
        raise ValueError("initial_molecular_connectivity_mismatch")
    for first, second in reference_edges:
        distance = atoms.get_distance(indices[first], indices[second], mic=True)
        expected = reference.get_distance(first, second)
        if distance < expected / scale:
            raise ValueError("initial_bond_too_short_relative_to_reference")
    # Check every internal pair, including pairs excluded from the bond graph.
    if any(atoms.get_distance(first, second, mic=True) < minimum
           for local, first in enumerate(indices) for second in indices[local + 1:]):
        raise ValueError("initial_adsorbate_atom_overlap")


def binding_geometry(pose, record, slab, rule, sites, analysis, centers):
    """Read actual anchor positions; molecular azimuth/height are not identities."""
    from scripts.adsorption.build_fe110_care_isomers import initial_binding_contact, initial_contact_checks

    atoms = pose_atoms(pose)
    slab_indices, ads = structure_indices(record, len(atoms))
    nearest = [min(atoms.get_distance(index, iron, mic=True) for iron in slab_indices) for index in ads]
    if record["surface_family"] == "metallic_fe":
        checks = initial_contact_checks([atoms[index].symbol for index in ads], nearest)
        if not all(checks.values()):
            raise ValueError("initial_surface_contact_not_plausible")
        if np.min(atoms.positions[ads, 2]) < np.max(atoms.positions[slab_indices, 2]) - 1e-8:
            raise ValueError("initial_adsorbate_buried_in_slab")
    mapping = record.get("binding_atom_indices_structure_0based") or {
        record["planned_binding_atom"]: record["anchor_index_structure_0based"],
    }
    classes = {}
    anchor_sites = {}
    for label, index in mapping.items():
        distance = nearest[ads.index(index)]
        if len(mapping) == 1 and record["surface_family"] == "metallic_fe":
            low, high = rule["allowed_fe_anchor_distance_angstrom"]
            if not float(low) - 1e-8 <= distance <= float(high) + 1e-8:
                raise ValueError("initial_primary_anchor_distance_out_of_range")
        elif not initial_binding_contact(distance):
            raise ValueError("initial_secondary_anchor_not_surface_bound")
        if centers is not None:
            nearest_sites = nearest_fe110_site_centers(slab, pose.frac[index], centers)
            name, (center, offset) = min(nearest_sites.items(), key=lambda item: item[1][1])
            tolerance = analysis["site_classification"]["top_lateral_tolerance_angstrom"]
            classes[label] = SITE_CLASS_MAP[name] if offset <= tolerance else "unknown"
        else:
            classes[label] = classify_manifest_site(atoms, index, sites, analysis)
            center = pose.frac[index]
        anchor_sites[index] = center
    primary = next(label for label, index in mapping.items() if index == record["anchor_index_structure_0based"])
    if classes[primary] != record["planned_site_class"]:
        raise ValueError("initial_binding_site_not_realized")
    return atoms, ads, classes, anchor_sites


def same_binding_mode(first, second, slab, operations, tolerance):
    """Compare only mapped anchors in x/y under actual slab symmetries."""
    anchors, primary_class = first
    other_anchors, other_primary_class = second
    if anchors.keys() != other_anchors.keys():
        return False
    if len(anchors) == 1:
        return primary_class == other_primary_class
    indices = sorted(anchors)
    first_xy = np.array([anchors[index] for index in indices])
    other_xy = np.array([other_anchors[index] for index in indices])
    for rotation, translation in operations:
        delta = minimum_image_delta_xy(other_xy @ rotation.T + translation - first_xy)
        delta[:, 2] = 0.0
        if np.max(np.linalg.norm(delta @ slab.cell, axis=1)) <= tolerance:
            return True
    return False


def validate_generated_batch(pending, slab, sites, rules):
    """Publish one plausible representative per actual initial binding-site mode."""
    analysis = load_yaml(resource_path("configs/adsmind_lite/analysis_rules.yaml"))
    families = load_yaml(resource_path("configs/adsmind_lite/surfaces.yaml"))["surface_families"]
    connectivity = analysis["connectivity"]
    surface_atoms = pose_atoms(slab)
    is_fe110 = sites["surface_family"] == "metallic_fe" and metallic_orientation(sites["surface_name"]) == "Fe110"
    centers = fe110_site_centers(slab) if is_fe110 else None
    tolerance = fe110_rule_defaults()["site_tolerance"] if is_fe110 else analysis["site_classification"]["top_lateral_tolerance_angstrom"]
    retained, groups = [], {}
    operations = [(np.eye(3, dtype=int), np.zeros(3))]
    if slab.symbols == ["Fe"] and slab.counts == [45] and any(item[2].get("binding_atom_indices_structure_0based") for item in pending):
        from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
        operations = surface_pose_symmetries(slab)
    for path, pose, record in pending:
        species = record["adsorbate"]
        try:
            atoms, ads, classes, anchor_sites = binding_geometry(pose, record, slab, rules[species], sites, analysis, centers)
            reason = validate_one_candidate(
                record, families, rules, float(connectivity["minimum_bond_distance_angstrom"]),
                float(connectivity["covalent_radius_scale"]), hard_contact_distance(analysis), set(),
                atoms=atoms, surface_atoms=surface_atoms,
            )
            if reason != "accepted":
                raise ValueError(reason)
            molecular_geometry(atoms, ads, rules[species], analysis)
        except ValueError as exc:
            raise ValueError(f"{record['candidate_id']}: {exc}; no candidates generated") from exc
        candidate = (anchor_sites, record["planned_site_class"])
        representatives = groups.setdefault(species, [])
        match = next((item for item in representatives if same_binding_mode(
            candidate, item[0], slab, operations, tolerance,
        )), None)
        if match is not None:
            match[1].setdefault("omitted_same_site_variants", []).append(record["candidate_id"])
            continue
        record["initial_geometry_validation"] = "PASS"
        record["observed_binding_site_classes"] = classes
        record["scientific_stability"] = "NOT_ASSESSED"
        representatives.append((candidate, record))
        retained.append((path, pose, record))
    required = generation_coverage_rules()["policy"]["minimum_distinct_initial_motifs"]
    for species, representatives in groups.items():
        if len(representatives) < required:
            raise ValueError(f"{species}: actual_initial_site_coverage {len(representatives)}/{required}; no candidates generated")
    return retained
