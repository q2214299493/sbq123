from __future__ import annotations

import json
from typing import Any

from scripts.artifact_io import sha256_json


def build_fingerprint(contract: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "reaction_id": contract["reaction_id"],
        "reaction_family": contract["reaction_family"],
        "reactant_id": contract["reactant_id"],
        "product_id": contract["product_id"],
        "broken_bonds": contract["broken_bonds"],
        "formed_bonds": contract["formed_bonds"],
        "adsorption_site_changes": contract["site_changes"],
        "atom_map_sha256": contract["atom_map_sha256"],
        "compatibility": contract["compatibility"],
    }
    identity = {key: value for key, value in payload.items() if key != "reaction_id"}
    payload["fingerprint_id"] = sha256_json(identity)
    return payload


def _jaccard(left: list[Any], right: list[Any]) -> float:
    a = {json.dumps(value, sort_keys=True) for value in left}
    b = {json.dumps(value, sort_keys=True) for value in right}
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _reaction_event_similarity(
    fingerprint: dict[str, Any], prior: dict[str, Any]
) -> float:
    components = []
    for key in ("broken_bonds", "formed_bonds", "adsorption_site_changes"):
        left = fingerprint.get(key, [])
        right = prior.get(key, [])
        if left or right:
            components.append(_jaccard(left, right))
    return sum(components) / len(components) if components else 0.0


def rank_templates(fingerprint: dict[str, Any], templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for template in templates:
        prior = template["fingerprint"]
        compatible = fingerprint["compatibility"] == prior.get("compatibility")
        chemical_match = (
            fingerprint["reactant_id"] == prior.get("reactant_id")
            and fingerprint["product_id"] == prior.get("product_id")
        )
        exact = compatible and fingerprint["fingerprint_id"] == prior.get("fingerprint_id")
        family = fingerprint["reaction_family"] == prior.get("reaction_family")
        broken = _jaccard(fingerprint["broken_bonds"], prior.get("broken_bonds", []))
        formed = _jaccard(fingerprint["formed_bonds"], prior.get("formed_bonds", []))
        sites = _jaccard(fingerprint["adsorption_site_changes"], prior.get("adsorption_site_changes", []))
        event_similarity = _reaction_event_similarity(fingerprint, prior)
        strategy_score = (
            1.0
            if exact
            else 0.4 * family
            + 0.35 * event_similarity
            + 0.2 * chemical_match
            + 0.05 * compatible
        )
        level = (
            "incompatible_method_branch"
            if not compatible
            else "exact_fingerprint"
            if exact
            else "chemical_identity"
            if chemical_match
            else "reaction_family"
            if family
            else "bond_transformation"
            if broken or formed
            else "adsorption_environment"
            if sites
            else "unrelated"
        )
        evidence_valid = bool(template.get("evidence_valid"))
        accepted_success = bool(
            evidence_valid
            and template["outcome"] == "success"
            and template["validation_grade"] == "A"
        )
        strategy_transferable = bool(
            accepted_success
            and family
            and (chemical_match or event_similarity > 0.0)
        )
        result_transferable = bool(accepted_success and exact and compatible)
        strategy_match_level = (
            "exact_fingerprint"
            if exact
            else "chemical_identity"
            if chemical_match
            else "reaction_event"
            if family and event_similarity > 0.0
            else "reaction_family"
            if family
            else "unrelated"
        )
        ranked.append(
            {
                "template_id": template["template_id"],
                "score": round(strategy_score, 6),
                "match_level": level,
                "strategy_match_level": strategy_match_level,
                "compatible": compatible,
                "chemical_match": chemical_match,
                "reaction_event_similarity": round(event_similarity, 6),
                "evidence_valid": evidence_valid,
                "strategy_transferable": strategy_transferable,
                "result_transferable": result_transferable,
                # Legacy strict field: callers that have not adopted the split
                # must never become more permissive silently.
                "transferable": result_transferable,
                "template": template,
            }
        )
    return sorted(ranked, key=lambda item: (-item["score"], item["template_id"]))
