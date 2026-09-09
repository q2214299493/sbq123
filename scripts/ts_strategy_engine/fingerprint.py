from __future__ import annotations

import json
from typing import Any

from scripts.artifact_io import sha256_json

from .contract import normalize_contract


def chemical_events(contract: dict[str, Any], atom_symbols: list[str] | None) -> dict[str, list[str]] | None:
    """Element-labelled events compare chemistry independently of atom numbering."""
    if atom_symbols is None:
        return None
    from pymatgen.core import Element

    if len(atom_symbols) != len(contract["atom_map"]):
        raise ValueError("fingerprint symbols must label every mapped atom")
    symbols = [Element(value).symbol for value in atom_symbols]
    if contract.get("atom_symbols", symbols) != symbols:
        raise ValueError("contract atom symbols disagree with endpoint structure")
    return {key: sorted("-".join(sorted(symbols[index] for index in bond)) for bond in contract[key])
            for key in ("broken_bonds", "formed_bonds")}


def family_event_matches(fingerprint: dict[str, Any], rule: dict[str, Any]) -> bool:
    from collections import Counter

    events = fingerprint.get("chemical_events")
    for key in ("broken_bonds", "formed_bonds"):
        required = Counter("-".join(sorted(value.strip().title().split("-"))) for value in rule.get(key, []))
        if required and (events is None or required - Counter(events.get(key, []))):
            return False
    return True


def build_fingerprint(contract: dict[str, Any], *, atom_symbols: list[str] | None = None) -> dict[str, Any]:
    contract = normalize_contract(contract)
    events = chemical_events(contract, atom_symbols if atom_symbols is not None else contract.get("atom_symbols"))
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
        "chemical_events": events,
        "chemical_event_sha256": sha256_json(events) if events is not None else None,
        "result_identity_sha256": sha256_json({
            "endpoints": contract["endpoints"], "atom_map": contract["atom_map"],
            "compatibility": contract["compatibility"], "chemical_events": events,
        }),
    }
    # Preserve the legacy path-binding key. Chemistry and scientific-result
    # identities are separate requirements and cannot be inferred from this key.
    identity = {key: value for key, value in payload.items()
                if key not in {"reaction_id", "result_identity_sha256", "chemical_events", "chemical_event_sha256"}}
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
    left, right = fingerprint.get("chemical_events"), prior.get("chemical_events")
    if left is None or right is None:
        return 0.0
    components = [_jaccard(left[key], right.get(key, [])) for key in ("broken_bonds", "formed_bonds")
                  if left[key] or right.get(key)]
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
        event_equivalent = (fingerprint.get("chemical_events") is not None
                            and fingerprint["chemical_events"] == prior.get("chemical_events"))
        exact = bool(compatible and event_equivalent
                     and fingerprint["fingerprint_id"] == prior.get("fingerprint_id")
                     and fingerprint.get("result_identity_sha256")
                     and fingerprint["result_identity_sha256"] == prior.get("result_identity_sha256"))
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
            and event_equivalent
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
                "chemical_event_equivalent": event_equivalent,
                "structural_similarity": round((broken + formed + sites) / 3, 6),
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
