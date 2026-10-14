"""Pure evidence priority for generated candidates; no method-effect scores or authority."""
from __future__ import annotations


def normalize_method_references(neb, eligible):
    """Interpret existing representations against the caller's existing method owners."""
    methods, excluded = set(), []
    if not isinstance(neb, dict):
        excluded.append({"source_field": "neb_settings", "reason": "method_reference_requires_object"})
        neb = {}
    for field in ("candidate_methods", "sequence"):
        values = neb.get(field, [])
        if not isinstance(values, list):
            excluded.append({"source_field": field, "reason": "method_reference_requires_array"})
            continue
        for method in values:
            if not isinstance(method, str) or method not in eligible:
                excluded.append({"source_field": field, "method": method,
                                 "reason": "not_in_existing_family_or_reference_method_catalog"})
            else:
                methods.add(method)
    return {"methods": sorted(methods), "excluded": excluded, "sequence_is_execution_order": False}


def _template_support(method, ranked, threshold, eligible):
    rows = []
    for match in ranked:
        if not match["evidence_valid"] or not match["strategy_transferable"] or match["score"] < threshold:
            continue
        item = match["template"]
        explicit = normalize_method_references(item["neb_settings"], eligible)["methods"]
        if method in explicit:
            rows.append({"template_id": item["template_id"], "source_calculation_id": item["source_calculation_id"],
                         "ts_validation_id": item["ts_validation_id"], "barrier_set_id": item["barrier_set_id"],
                         "template_similarity": match["score"], "strategy_transferable": match["strategy_transferable"],
                         "result_transferable": match["result_transferable"], "match_level": match["strategy_match_level"],
                         "registered_evidence_only": True, "scientific_results_imported": False})
    return rows


def _unchanged_failures(candidate, context):
    # Input-key equality alone cannot attribute a failure to another proposed method.
    if candidate["method"] != context["variant_settings"]["candidate_method"]:
        return []
    blocked = set(context["retry"]["blocked_attempts"])
    return [row for row in context["history"] if row["attempt_id"] in blocked
            and row["variant_id"] == context["request"]["variant_id"]
            and row["input_key"] == context["input_key"]]


def _annotate(candidate, context, ranked, threshold):
    assessment, evidence, budget = context["assessment"], context["evidence"], context["budget"]
    templates = _template_support(candidate["method"], ranked, threshold, context["resource_ownership"])
    failures = _unchanged_failures(candidate, context)
    blockers = ["prerequisite:" + name for name in candidate["missing_prerequisites"]]
    blockers.extend("budget:" + name for name in candidate["budget_blockers"])
    blockers.extend("confirmed_deterministic_unchanged_failure:" + row["attempt_id"] for row in failures)
    reasons = ["current_contract_and_path_source_identity_verified", "current_method_rationale_cites_causal_evidence"]
    uncertainty = ["future_cost_NOT_MEASURED", "budget_fit_NOT_ESTABLISHED", "method_effectiveness_not_evaluated"]
    if assessment["diagnosis"]["causal_status"] != "confirmed":
        uncertainty.append("causal_claim_is_hypothesis")
    if templates:
        reasons.append("method_explicitly_referenced_by_qualified_matching_template")
        uncertainty.append("historical_physical_source_files_not_reverified")
    else:
        uncertainty.append("no_qualified_method_specific_template_support")
    limits = ("remaining_attempts", "force_calls", candidate["hour_budget_field"])
    known_limits = all(budget.get(name) is not None for name in limits)
    if not known_limits:
        uncertainty.append("relevant_resource_limits_unknown")
    else:
        reasons.append("relevant_resource_ceilings_known_not_proof_of_budget_fit")
    if context["retry"]["status"] != "NO_KNOWN_FAILURE" or context["pending_same_input"]:
        uncertainty.append("fresh_candidate_inputs_require_existing_retry_review")
    if not context["history"]:
        uncertainty.append("historical_results_not_recorded")
    checks = {name: {"status": status, "source": evidence.get(assessment["prerequisites"].get(name))}
              for name, status in candidate["prerequisite_checks"].items()}
    candidate.update(rank=None, reasons=reasons, blocking_conditions=blockers, uncertainty=uncertainty,
                     supporting_evidence={"contract": context["request"]["inputs"]["contract"],
                         "causal_status": assessment["diagnosis"]["causal_status"],
                         "method": [evidence[name] for name in candidate["evidence_ids"]],
                         "path": [evidence[name] for name in assessment["path_evidence_ids"]],
                         "prerequisites": checks, "gate": context["request"]["gate"],
                         "templates": templates, "unchanged_failures": failures,
                         "task_lessons": context["lessons"], "resource_limits": {name: budget.get(name) for name in limits},
                         "variant_attempts_remaining": context["variant_attempts_remaining"]})
    # Lexicographic evidence categories, reusing the owner's similarity without new weights.
    best = max(((row["template_similarity"], row["result_transferable"]) for row in templates), default=(0, False))
    return bool(templates), *best, known_limits


def rank_candidates(plan, context, ranked, threshold):
    """Annotate all search candidates; reorder only eligible slots when evidence differs."""
    searches = [item for item in plan["candidates"] if item["kind"] == "TS_search_candidate"]
    profiles = {item["method"]: _annotate(item, context, ranked, threshold) for item in searches}
    eligible = [item for item in searches if item["status"] == "CONSIDER_FOR_REVIEW" and not item["blocking_conditions"]]
    comparative = bool(eligible) and (len(eligible) < len(searches)
                                     or len({profiles[item["method"]] for item in eligible}) > 1)
    plan["ranking_type"] = "evidence_supported_priority"
    plan["ranking_uncertainty"] = (["causal_evidence_missing_no_TS_ranking"]
                                   if context["assessment"]["diagnosis"]["causal_status"] == "unknown" else [])
    if not comparative:
        for item in eligible:
            item["uncertainty"].append("no_comparative_priority_evidence")
        return plan
    order = sorted(eligible, key=lambda item: profiles[item["method"]], reverse=True)
    tiers = sorted({profiles[item["method"]] for item in eligible}, reverse=True)
    for item in order:
        item["rank"] = tiers.index(profiles[item["method"]]) + 1
        item["reasons"].append("priority_by_template_match_then_known_resource_limits_after_existing_checks")
    identities = {id(item) for item in eligible}
    replacements = iter(order)
    plan["candidates"] = [next(replacements) if id(item) in identities else item for item in plan["candidates"]]
    plan["ranking"] = "EVIDENCE_SUPPORTED_PRIORITY"
    return plan
