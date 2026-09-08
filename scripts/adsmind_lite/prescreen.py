from __future__ import annotations

from typing import Any

from .adsmind_common import load_yaml_schema
from .fts_prescreen import assert_fts_surface, plan_calibrated_fts_species, plan_feature_based_fts_species


def load_prescreen_rules(path: str) -> dict[str, Any]:
    return load_yaml_schema(path, ("policy", "species"), "prescreen rules require policy and species mappings")


def plan_species(
    species_name: str,
    rules: dict[str, Any],
    *,
    available_templates: set[str] | None = None,
    adsorbate_catalog: dict[str, Any] | None = None,
    fts_rules: dict[str, Any] | None = None,
    external_plans: dict[str, dict[str, Any]] | None = None,
    species_features: dict[str, dict[str, Any]] | None = None,
    surface_name: str = "Fe110",
) -> dict[str, Any]:
    """Plan one species using local, calibrated, external, then hypothesis evidence.

    Feature-derived entries are retrieval hypotheses only and always contain
    zero build-ready candidates.
    """
    available_templates = available_templates or set()
    species_rules = rules["species"].get(species_name)
    if species_rules is None:
        if fts_rules is not None:
            fts_plan = plan_calibrated_fts_species(
                species_name,
                fts_rules,
                available_templates=available_templates,
                surface_name=surface_name,
            )
            if fts_plan is not None:
                return {**fts_plan, "plan_source": "reviewed_local_fts_rule", "evidence_priority_rank": 2}
        if external_plans and species_name in external_plans:
            return {**external_plans[species_name], "plan_source": "external_evidence_gate", "evidence_priority_rank": 3}
        if fts_rules is not None and species_features and species_name in species_features:
            hypothesis_plan = plan_feature_based_fts_species(
                species_name,
                species_features[species_name],
                fts_rules,
                surface_name=surface_name,
            )
            hypotheses = hypothesis_plan["candidates"]
            return {
                **hypothesis_plan,
                "candidate_count": 0,
                "candidates": [],
                "search_hypothesis_count": len(hypotheses),
                "search_hypotheses": hypotheses,
                "plan_source": "feature_based_retrieval_hypotheses",
                "evidence_priority_rank": 4,
            }
        return {
            "species": species_name,
            "decision": "NEEDS_WHITELIST",
            "reason_code": "no_accepted_local_or_external_adsorption_motif",
            "plan_source": "retrieval_required",
            "evidence_priority_rank": 5,
            "candidate_count": 0,
            "candidates": [],
            "search_metadata_available": species_name in (adsorbate_catalog or {}),
        }

    candidates = sorted(species_rules.get("candidates", []), key=lambda item: int(item.get("priority", 999)))
    planned: list[dict[str, Any]] = []
    blocked = 0
    for candidate in candidates:
        item = dict(candidate)
        template_required = bool(item.get("template_required", False))
        template_available = item["motif_id"] in available_templates
        item["build_ready"] = not template_required or template_available
        if not item["build_ready"]:
            item["reason_code"] = "reviewed_structure_template_required"
            blocked += 1
        else:
            item["reason_code"] = "selected_by_prescreen"
        planned.append(item)

    decision = "READY" if planned and blocked == 0 else "BLOCKED" if blocked == len(planned) else "PARTIAL"
    return {
        "species": species_name,
        "surface": species_rules.get("surface"),
        "plan_source": "reviewed_local_species_rule",
        "evidence_priority_rank": 1,
        "decision": decision,
        "confidence": species_rules.get("confidence", "low"),
        "evidence": species_rules.get("evidence", {}),
        "candidate_count": len(planned),
        "candidates": planned,
        "suppressed": species_rules.get("suppress", []),
    }


def plan_batch(
    species_names: list[str],
    rules: dict[str, Any],
    *,
    available_templates: set[str] | None = None,
    adsorbate_catalog: dict[str, Any] | None = None,
    fts_rules: dict[str, Any] | None = None,
    external_plans: dict[str, dict[str, Any]] | None = None,
    species_features: dict[str, dict[str, Any]] | None = None,
    surface_name: str = "Fe110",
) -> dict[str, Any]:
    """Plan a batch without turning feature-based retrieval hypotheses into candidates."""
    if fts_rules is not None:
        assert_fts_surface(surface_name, fts_rules)
    plans = [
        plan_species(
            name,
            rules,
            available_templates=available_templates,
            adsorbate_catalog=adsorbate_catalog,
            fts_rules=fts_rules,
            external_plans=external_plans,
            species_features=species_features,
            surface_name=surface_name,
        )
        for name in species_names
    ]
    return {
        "version": 1,
        "surface_name": surface_name,
        "policy": rules["policy"],
        "staged_relaxation": rules.get("staged_relaxation", {}),
        "species_plans": plans,
        "summary": {
            "species": len(plans),
            "candidate_count": sum(int(plan["candidate_count"]) for plan in plans),
            "search_hypothesis_count": sum(int(plan.get("search_hypothesis_count", 0)) for plan in plans),
            "ready_species": sum(plan["decision"] == "READY" for plan in plans),
            "blocked_species": sum(plan["decision"] == "BLOCKED" for plan in plans),
            "needs_review_species": sum(plan["decision"] == "NEEDS_REVIEW" for plan in plans),
            "needs_retrieval_species": sum(plan["decision"] == "NEEDS_RETRIEVAL" for plan in plans),
            "needs_whitelist_species": sum(plan["decision"] == "NEEDS_WHITELIST" for plan in plans),
            "needs_literature_species": sum(plan["decision"] == "NEEDS_LITERATURE" for plan in plans),
        },
    }
