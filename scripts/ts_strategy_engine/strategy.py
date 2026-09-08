from __future__ import annotations

from typing import Any

from .execution_gate import decide_execution
from .strategy_learning import reference_methods

def _family_rule(family: str, config: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    requested = family.lower()
    for name, rule in config["priority_families"].items():
        aliases = {str(value).lower() for value in rule.get("aliases", [])}
        if requested == name.lower() or requested in aliases:
            return name, rule
    return requested, None


def compose_strategy(
    fingerprint: dict[str, Any],
    ranked: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    family_contract_valid = True
    threshold = float(
        config.get("strategy_transfer_threshold", config["template_transfer_threshold"])
    )
    accepted = next(
        (
            item
            for item in ranked
            if item.get("strategy_transferable") and item["score"] >= threshold
        ),
        None,
    )
    failure_constraints = [
        {
            "template_id": item["template_id"],
            "score": item["score"],
            "failure_cases": item["template"]["failure_cases"],
            "correction_strategy": item["template"].get("correction_strategy"),
        }
        for item in ranked
        if item["compatible"] and item["template"]["outcome"] == "failure" and item["score"] >= threshold
    ]
    if accepted:
        template = accepted["template"]
        source = "template_transfer"
        family = template["reaction_family"]
        waypoints = template["waypoint_strategy"]
        interpolation = template["interpolation_strategy"]
        neb = template["neb_settings"]
        dimer = template["dimer_usage"]
        template_match = {
            "template_id": accepted["template_id"],
            "score": accepted["score"],
            "match_level": accepted["strategy_match_level"],
            "strategy_transferable": True,
            "result_transferable": accepted["result_transferable"],
        }
    else:
        family, rule = _family_rule(fingerprint["reaction_family"], config)
        source = "rule_based"
        rule = rule or {}
        waypoints = rule.get("waypoint_strategy", ["reactant", "reviewed_reaction_waypoint", "product"])
        interpolation = rule.get("interpolation_strategy", "segmented_idpp")
        neb = {
            "candidate_methods": rule.get(
                "vasp_candidate_methods",
                ["ordinary_neb", "ci_neb", "gpu_ml_neb_vasp_validated_triad"],
            ),
            "initial_images": int(rule.get("initial_images", 3)),
            "image_policy": "start_minimal_then_add_only_at_large_displacement_or_high_curvature",
            "selection_policy": "choose_from_reviewed_path_evidence_not_a_fixed_sequence",
        }
        dimer = {"policy": rule.get("dimer_usage", "conditional_refinement")}
        template_match = None
        required_broken = {str(value).lower() for value in rule.get("broken_bonds", [])}
        required_formed = {str(value).lower() for value in rule.get("formed_bonds", [])}
        declared_broken = bool(fingerprint["broken_bonds"])
        declared_formed = bool(fingerprint["formed_bonds"])
        family_contract_valid = (not required_broken or declared_broken) and (not required_formed or declared_formed)
    return {
        "version": 5,
        "status": (
            "STOP_FAMILY_CONTRACT_MISMATCH"
            if not accepted and not family_contract_valid
            else "NEEDS_GPU_PATH_OR_VASP_PATH_REVIEW"
        ),
        "strategy_source": source,
        "reaction_family": family,
        "fingerprint_id": fingerprint["fingerprint_id"],
        "template_match": template_match,
        "reuse_scope": "method_strategy_only" if accepted else "family_rule_only",
        "result_reuse_policy": (
            "reference_existing_registered_result_only"
            if accepted and accepted["result_transferable"]
            else "forbidden"
        ),
        "nontransferable_artifacts": [
            "endpoint_coordinates",
            "atom_indices",
            "MODECAR",
            "CHGCAR",
            "WAVECAR",
            "image_number",
            "energies",
            "barrier",
        ],
        "failure_constraints": failure_constraints,
        "reference_methods": reference_methods(),
        "waypoint_strategy": waypoints,
        "interpolation_strategy": interpolation,
        "neb_settings": neb,
        "dimer_usage": dimer,
        "gpu_acceleration": {
            "policy": "active_learning_acceleration_loop",
            "target_product": "complete_hash_bound_gpu_path",
            "does_not_establish": ["vasp_energy", "accepted_transition_state", "reportable_barrier"],
        },
        "path_initialization": {
            "waypoint_policy": "conditional_on_reaction_mapping_and_continuity_risk",
            "direct_idpp_policy": "allowed_only_when_reviewed_geometry_and_periodic_continuity_pass",
            "bond_change_policy": "use_reviewed_waypoints_when_direct_path_underresolves_or_misassigns_the_event",
        },
        "vasp_method_selection": "choose_case_by_case_from_gpu_path_continuity_peaks_forces_and_local_triad_evidence",
        "validation": "docs/10_TS_VALIDATION_PROTOCOL.md",
        "database_storage": "successful Grade-A or explicit failed-experience record only",
        "requires_user_confirmation": True,
        "automatic_submission": False,
    }


def decide_search(
    geometry: dict[str, Any],
    analysis: dict[str, Any],
    thresholds: dict[str, Any],
    climb: bool,
    path_reviewed: bool,
    path_quality: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    scheduler: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return decide_execution(
        geometry,
        analysis,
        thresholds,
        climb=climb,
        path_reviewed=path_reviewed,
        path_quality=path_quality,
        preflight=preflight,
        validation=validation,
        scheduler=scheduler,
    )
