"""Directed numeric comparison and drafts using existing geometry owners."""
from __future__ import annotations

import itertools
import json

import numpy as np
import yaml

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.neb_agent.utils_structure import compatible, read_poscar


def indices(value, count):
    if not isinstance(value, list) or len(value) > 100 or any(type(i) is not int or not 0 <= i < count for i in value):
        raise ValueError("explicit zero-based atom indices outside structure")
    if len(set(value)) != len(value):
        raise ValueError("duplicate atom indices")
    return value


def compare(paths, ids, query):
    from ase.geometry import find_mic
    options = json.loads(query) if query else {}
    if not isinstance(options, dict) or set(options) - {"pairs_zero_based", "adsorbate_zero_based", "surface_zero_based"}:
        raise ValueError("directed comparison requires pairs/adsorbate/surface zero-based lists")
    parsed = [read_poscar(path) for path in paths]
    rows = []
    for identity, structure in zip(ids, parsed):
        active = indices(options.get("adsorbate_zero_based", [i for i, label in enumerate(structure.labels) if label != "Fe"]), structure.atom_count)
        surface = indices(options.get("surface_zero_based", [i for i, label in enumerate(structure.labels) if label == "Fe"]), structure.atom_count)
        pairs = options.get("pairs_zero_based", [])
        if not isinstance(pairs, list) or len(pairs) > 24 or any(not isinstance(p, list) or len(p) != 2 for p in pairs):
            raise ValueError("at most 24 explicit atom pairs required")
        measurements = []
        for pair in pairs:
            i, j = indices(pair, structure.atom_count)
            _, distances = find_mic((structure.frac[j] - structure.frac[i]) @ structure.cell, structure.cell, pbc=True)
            measurements.append({"atoms_zero_based": pair, "atoms_one_based": [i + 1, j + 1],
                                 "elements": [structure.labels[i], structure.labels[j]], "MIC_A": float(distances)})
        contacts = []
        for atom in active:
            if not surface:
                continue
            _, distances = find_mic((structure.frac[surface] - structure.frac[atom]) @ structure.cell, structure.cell, pbc=True)
            which = int(np.argmin(distances))
            neighbor = surface[which]
            contacts.append({"atom_zero_based": atom, "atom_one_based": atom + 1, "element": structure.labels[atom],
                             "surface_atom_zero_based": neighbor, "surface_atom_one_based": neighbor + 1,
                             "surface_element": structure.labels[neighbor], "MIC_A": float(distances[which])})
        rows.append({"source_id": identity, "directed_pairs": measurements, "nearest_selected_surface_contacts": contacts,
                     "surface_selection_zero_based": surface, "adsorbate_selection_zero_based": active})
    comparisons = []
    for (i, left), (j, right) in itertools.combinations(enumerate(parsed), 2):
        errors = compatible(left, right)
        row = {"left_id": ids[i], "right_id": ids[j], "mapping_cell_constraint_errors": errors}
        if not errors:
            _, norms = find_mic((right.frac - left.frac) @ left.cell, left.cell, pbc=True)
            active = rows[i]["adsorbate_selection_zero_based"]
            row.update({"same_index_maximum_MIC_A": float(np.max(norms)),
                        "adsorbate_same_index_RMS_MIC_A": float(np.sqrt(np.mean(norms[active] ** 2))) if active else None})
        comparisons.append(row)
    return {"structures": rows, "comparisons": comparisons,
            "scope": "numeric comparison in angstrom; no atom permutation, target identity or site/scientific acceptance inferred"}


def review(registry, ids, query, sources):
    from scripts.adsmind_lite.relaxed_analysis import structure_connectivity, connectivity_change
    if len(ids) != 2:
        raise ValueError("workflow.review requires reference/target structure and candidate structure IDs")
    options = json.loads(query)
    if set(options) != {"option_id", "adsorbate_zero_based"} or not isinstance(options["option_id"], str) or not options["option_id"].strip():
        raise ValueError("a branch option_id and explicit adsorbate_zero_based selection required")
    paths = [registry.frozen(identity, sources) for identity in ids]
    structures = [read_poscar(path) for path in paths]
    errors = compatible(*structures)
    if errors:
        raise ValueError("review requires an explicit compatible atom mapping: " + "; ".join(errors))
    active = indices(options["adsorbate_zero_based"], structures[0].atom_count)
    if not active:
        raise ValueError("adsorbate selection must not be empty")
    rules, ref = registry.catalog.freeze(registry.project / "configs/adsmind_lite/analysis_rules.yaml")
    sources.append(ref)
    analysis = yaml.safe_load(rules.read_text(encoding="utf-8"))
    initial, _ = structure_connectivity(paths[0], active, analysis)
    candidate, _ = structure_connectivity(paths[1], active, analysis)
    observation = connectivity_change(len(active), initial, candidate)
    folder = registry.output / "drafts" / f"review-{len(registry.actions) + 1:03d}"
    folder.mkdir(parents=True)
    document = {"schema_version": 1, "option_id": options["option_id"], "status": "UNAPPROVED_REVIEW_DRAFT",
                "reference_structure_id": ids[0], "candidate_structure_id": ids[1], "sources": sources,
                "adsorbate_zero_based": active, "owner": "adsmind_lite.relaxed_analysis",
                "owner_connectivity_observations": observation, "reference_edges_local_zero_based": initial,
                "candidate_edges_local_zero_based": candidate,
                "pending_owner_review": ["research target/isomer and site applicability", "scientific convergence and compatibility",
                                         "budget, complete input package and any execution authority"],
                "parameters_generated": False, "cost": None, "runnable": False, "scientific_acceptance": False}
    target = folder / "review_candidate.json"
    write_json_exclusive(target, document)
    return {"draft": {"path": str(target), "sha256": sha256_file(target), "option_id": options["option_id"],
                      "status": "UNAPPROVED_REVIEW_DRAFT"}, "owner_connectivity_observations": observation,
            "scope": "existing owner rules; reference geometry is a target hypothesis, not accepted science or a ready input package"}
