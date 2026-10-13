"""Source-bound next-step planning. Reads existing history; never changes a strategy or gate."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, require_sha256, sha256_file, sha256_json
from scripts.execution_backends import DEFAULT_CONFIG as BACKEND_CONFIG
from scripts.runtime_resources import resource_path
from scripts.scientific_validation import finite_number
from .contract import load_contract
from .execution_gate import validate_decision
from .fingerprint import build_fingerprint
from .learning_cases import diagnosis_error
from .learning_evidence import attempt_input_hashes, exact_keys, input_key, observe, validate_costs, validate_files
from .learning_store import get_event, history_token, read_events
from .next_review_core import review_field_orders
from .strategy import compose_strategy
from .template_reference import reference_report, template_references, template_snapshot
from .strategy_learning import POLICY, _validate_settings, compare_variants, policy, retry_assessment, task_lessons


COST_FIELDS = ("vasp_core_hours", "gpu_hours", "force_calls")


def _budget(value):
    if value is None:
        return {"remaining_attempts": None, **dict.fromkeys(COST_FIELDS)}
    exact_keys(value, {"remaining_attempts", *COST_FIELDS})
    for key, limit in value.items():
        if limit is not None:
            if type(limit) not in {int, float}:
                raise ValueError(f"{key} must be a JSON number or null")
            finite_number(limit, key, nonnegative=True)
            if key in {"remaining_attempts", "force_calls"} and type(limit) is not int:
                raise ValueError(f"{key} must be an integer or null")
    return value


def _assessment(reference, task_id, variant_id, key):
    validate_files({"assessment": reference})
    assessment = load_json_object(Path(reference["path"]))
    exact_keys(assessment, {"task_id", "variant_id", "input_key", "provenance", "diagnosis", "evidence",
                            "path_evidence_ids", "prerequisites", "method_support"})
    if (assessment["task_id"], assessment["variant_id"], assessment["input_key"]) != (task_id, variant_id, key):
        raise ValueError("assessment task, strategy version or input identity mismatch")
    if assessment["provenance"] not in {"synthetic", "reviewed_real", "incomplete"}:
        raise ValueError("assessment provenance must be explicit")
    evidence = {}
    if not isinstance(assessment["evidence"], list) or not assessment["evidence"]:
        raise ValueError("nonempty raw diagnostic evidence required")
    for item in assessment["evidence"]:
        exact_keys(item, {"evidence_id", "path", "sha256", "pointer", "value"})
        identity = item["evidence_id"]
        if not isinstance(identity, str) or not identity.strip() or identity in evidence:
            raise ValueError("evidence IDs must be unique nonempty strings")
        if isinstance(item["value"], (dict, list)):
            raise ValueError("raw evidence must select a scalar, with its exact JSON type")
        observe([{k: v for k, v in item.items() if k != "evidence_id"}])
        source = load_json_object(Path(item["path"]))
        if source.get("task_id") != task_id or source.get("input_key") != key:
            raise ValueError("raw evidence task or input identity mismatch")
        evidence[identity] = item
    if error := diagnosis_error(assessment["diagnosis"], set(evidence)):
        raise ValueError(f"invalid diagnosis: {error}")
    _review_links(assessment, evidence)
    return assessment, evidence


def _review_links(assessment, evidence):
    """Validate source links, including method-specific reasons and prerequisite checks."""
    def ids(values):
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values) \
                or len(values) != len(set(values)) or not set(values) <= evidence.keys():
            raise ValueError("evidence references must be unique known IDs")
    ids(assessment["path_evidence_ids"])
    if not isinstance(assessment["prerequisites"], dict) or not isinstance(assessment["method_support"], dict):
        raise ValueError("prerequisites and method support must be objects")
    requirements = {name for method in policy()["reference_methods"].values() for name in method["prerequisites"]}
    if not assessment["prerequisites"].keys() <= requirements:
        raise ValueError("prerequisites must come from existing reference methods")
    for name, identity in assessment["prerequisites"].items():
        if not isinstance(name, str) or not name.strip() or not isinstance(identity, str) or identity not in evidence \
                or evidence[identity]["value"] is not None and type(evidence[identity]["value"]) is not bool:
            raise ValueError("prerequisites require bound boolean/null observations")
    allowed = policy()["settings_schema"]["properties"]["candidate_method"]["enum"]
    for method, support in assessment["method_support"].items():
        if method not in allowed:
            raise ValueError("unsupported candidate method")
        exact_keys(support, {"rationale", "evidence_ids"})
        ids(support["evidence_ids"])
        if not support["evidence_ids"] or not isinstance(support["rationale"], str) or not support["rationale"].strip():
            raise ValueError("method consideration requires a specific rationale and evidence")
        if not set(support["evidence_ids"]) & set(assessment["diagnosis"]["causal_evidence_ids"]):
            raise ValueError("method consideration must cite evidence for the specific causal claim")


def _history(database, task_id, key):
    outcomes = read_events(database, "outcome")
    rows = []
    for identity, attempt in read_events(database, "attempt").items():
        outcome = outcomes.get(identity)
        status, costs = "NOT_RECORDED", dict.fromkeys(COST_FIELDS, "NOT_MEASURED")
        if outcome is not None:
            status = "current_source_verified"
            try:
                observe(outcome["observations"])
                validate_costs(outcome["costs"], outcome["observations"])
                costs.update(outcome["costs"])
            except (OSError, ValueError):
                status = "NEEDS_REVIEW"
        rows.append({"attempt_id": identity, "task_id": attempt["task_id"], "kind": attempt["kind"],
                     "variant_id": attempt["variant_id"], "input_key": attempt["input_key"],
                     "scope": "same_input" if attempt["input_key"] == key else
                              "same_task" if attempt["task_id"] == task_id else "other_task",
                     "same_task": attempt["task_id"] == task_id,
                     "outcome": outcome, "evidence_status": status, "observed_costs": costs})
    return rows


def _prerequisite_status(name, assessment, evidence):
    """Bind the supported raw checks map to its owning prerequisite, not an arbitrary ID."""
    item = evidence.get(assessment["prerequisites"].get(name))
    if item is None:
        return "NOT_SUPPLIED"
    if item["pointer"] != f"/checks/{name}":
        return "SOURCE_CHECK_IDENTITY_MISMATCH"
    return "PASS" if item["value"] is True else "CHECK_NOT_TRUE"


def _resource_ownership(strategy, backends):
    """Resolve existing family/reference metadata through the owning backend contract."""
    hours = {"aqcat_gpu": "gpu_hours", "vasp": "vasp_core_hours"}
    primary = backends["dual_model_ts_path_acceleration"]["primary_model"]
    result = {}
    for method in strategy["neb_settings"].get("candidate_methods", []):
        # compose_strategy's family candidates are the existing VASP routes.
        owner = "vasp" if backends["backends"]["vasp"]["role"] == "authoritative_first_principles_calculation" else None
        result[method] = {"backend": owner, "hour_budget_field": hours.get(owner)}
    for method, reference in strategy["reference_methods"].items():
        capability = reference.get("backend_capability")
        if capability is None and reference.get("model") == f"current_{primary}_checkpoint":
            capability = f"{primary}_energy_force_inference"
        owners = [name for name, settings in backends["backends"].items()
                  if capability is not None and capability in settings.get("allowed", [])]
        owner = owners[0] if len(owners) == 1 else None
        result[method] = {"backend": owner, "hour_budget_field": hours.get(owner)}
    return result


def _method_candidates(context):
    """Methods are taken from existing composition/schema; prerequisites from their owners."""
    assessment, strategy = context["assessment"], context["strategy"]
    gate, budget, evidence = context["gate"], context["budget"], context["evidence"]
    permitted = set(strategy["neb_settings"].get("candidate_methods", [])) | set(strategy["reference_methods"])
    candidates = []
    for method, support in assessment["method_support"].items():
        if method not in permitted:
            continue
        reference = strategy["reference_methods"].get(method)
        if reference is not None:
            required = reference["prerequisites"]
            checks = {name: _prerequisite_status(name, assessment, evidence) for name in required}
            missing = [name for name, status in checks.items() if status != "PASS"]
            prerequisites = {name: assessment["prerequisites"].get(name) for name in required}
        else:
            # Translate existing method identities to the owning gate, without new scientific rules.
            action = {"ordinary_neb": "SUBMIT_VASP", "ci_neb": "ENABLE_CI_NEB",
                      "gpu_ml_neb_vasp_validated_triad": "PREPARE_DIMER_HANDOFF"}[method]
            ready = gate is not None and action in gate["scientific_readiness"]["eligible_actions"]
            missing = [] if ready else ["owning_gate_scientific_prerequisites"]
            prerequisites = {"owning_gate_action": action}
            checks = {"owning_gate_scientific_prerequisites": "PASS" if ready else "CHECK_NOT_TRUE"}
        ownership = context["resource_ownership"][method]
        hour_field = ownership["hour_budget_field"]
        missing.extend(["backend_resource_ownership_unknown"] if hour_field is None else [])
        blockers = [name for name in ("remaining_attempts", "force_calls") if budget[name] == 0]
        blockers.extend(["variant_attempts_remaining"] if context["variant_attempts_remaining"] == 0 else [])
        blockers.extend([hour_field] if hour_field is not None and budget[hour_field] == 0 else [])
        exhausted = bool(blockers)
        proposal = None
        if not missing and not exhausted and method != context["variant_settings"]["candidate_method"]:
            proposal = {"parent_id": context["request"]["variant_id"], "changes": {"candidate_method": method},
                        "rationale": support["rationale"], "observations": [
                            {k: v for k, v in evidence[identity].items() if k != "evidence_id"}
                            for identity in support["evidence_ids"]]}
        candidates.append({"kind": "TS_search_candidate", "method": method,
            "rationale": support["rationale"], "evidence_ids": support["evidence_ids"],
            "prerequisites": prerequisites, "missing_prerequisites": missing,
            "prerequisite_checks": checks, **ownership, "budget_blockers": blockers,
            "status": "NEEDS_MORE_EVIDENCE" if missing else "BUDGET_EXHAUSTED" if exhausted else "CONSIDER_FOR_REVIEW",
            "future_cost": dict.fromkeys(COST_FIELDS, "NOT_MEASURED"), "budget_fit": "NOT_ESTABLISHED",
            "result_class": reference["result_class"] if reference else "requires_existing_TS_validation",
            "requires_human_review": True, "automatic_execution": False,
            "proposal": proposal, "proposal_recorded": False,
            "requires_fresh_input_manifest_and_retry_check": True})
    return candidates


def build_plan(context):
    """Pure decisions on verified data; ordering expresses prerequisites, never invented scores."""
    spec, assessment, strategy = context["request"], context["assessment"], context["strategy"]
    diagnosis = assessment["diagnosis"]
    failure, certainty = diagnosis["failure_class"], diagnosis["causal_status"]
    gate, budget = context["gate"], context["budget"]
    gaps = []
    candidates = []
    stop = gate is not None and gate["DECISION"].startswith("STOP")
    if gate is None:
        gaps.append("current_execution_gate_missing")
    if any(value is None for value in budget.values()):
        gaps.append("budget_limits_missing_or_partial")
    if not context["history"]:
        gaps.append("historical_results_not_recorded")
    if any(row["evidence_status"] != "current_source_verified" for row in context["history"]):
        gaps.append("historical_sources_or_results_need_review")
    mandatory = ([{"kind": "preserve_STOP_and_complete_owning_gate_review", "decision": gate["DECISION"],
                   "next_required_check": gate["NEXT_REQUIRED_CHECK"]}] if stop else [])
    mandatory.append({"kind": "diagnostic_review", "next_review": diagnosis["next_review"],
                  "causal_status": certainty, "claim": diagnosis["causal_claim"],
                  "evidence_ids": diagnosis["evidence_ids"], "automatic_execution": False})
    if context["retry"]["status"] != "NO_KNOWN_FAILURE":
        mandatory.append({"kind": "retry_review", **context["retry"], "unchanged_retry_permitted": False})
    elif context["pending_same_input"]:
        mandatory.append({"kind": "wait_for_existing_attempt", "attempt_ids": context["pending_same_input"],
                          "unchanged_retry_permitted": False})
    if failure in {"runtime", "input", "scf"}:
        gaps.append("resolve_upstream_failure_before_TS_method_review")
    elif certainty == "unknown":
        mandatory.append({"kind": "collect_cause_specific_evidence", "automatic_execution": False})
        gaps.append("causal_evidence_missing")
    elif failure in context["review_fields"]:
        if not assessment["path_evidence_ids"]:
            mandatory.append({"kind": "collect_path_geometry_periodic_mapping_and_coverage_evidence",
                              "automatic_execution": False})
            gaps.append("path_evidence_missing")
        else:
            for field in context["review_fields"][failure]:
                candidates.append({"kind": "strategy_field_review", "field": field,
                    "evidence_ids": assessment["path_evidence_ids"], "new_value": "NOT_PROPOSED",
                    "reason": diagnosis["causal_claim"], "requires_human_review": True})
            if failure == "optimizer" and not stop and not strategy["status"].startswith("STOP"):
                candidates.extend(_method_candidates(context))
    if strategy["status"].startswith("STOP"):
        gaps.append(strategy["status"])
    searches = [candidate for candidate in candidates if candidate["kind"] == "TS_search_candidate"]
    if searches:
        gaps.append("future_computational_cost_not_measured")
    return {"schema_version": 1, "status": "ADVISORY_ONLY_NOT_AUTHORIZED",
            "task_id": spec["task_id"], "variant_id": spec["variant_id"], "input_key": context["input_key"],
            "diagnosis": copy.deepcopy(diagnosis), "provenance": assessment["provenance"],
            "mandatory_first": mandatory, "candidates": candidates,
            "ranking": "UNRANKED_NO_COMPARATIVE_EVIDENCE", "evidence_gaps": gaps,
            "historical_attempts": context["history"], "task_lessons": context["lessons"],
            "existing_variant_comparison": context["comparison"],
            "unchanged_retry": {**context["retry"], "pending_attempts": context["pending_same_input"],
                                "history_clear": context["retry"]["status"] == "NO_KNOWN_FAILURE" and not context["pending_same_input"],
                                "execution_permitted_by_planner": False},
            "budget": budget, "composed_strategy": strategy, "current_gate": copy.deepcopy(gate),
            "current_strategy_settings": context["variant_settings"],
            "variant_attempts_remaining": context["variant_attempts_remaining"],
            "current_STOP_preserved": stop, "requires_human_review": True,
            "automatic_submission": False, "automatic_promotion": False, "execution_permissions_changed": False,
            "causal_claims_scientifically_validated": False,
            "history_semantics": "latest_reviewed_outcomes_not_past_decision_time",
            "future_cost": dict.fromkeys(COST_FIELDS, "NOT_MEASURED")}


def _current_gate(reference, assessment):
    """Retain the existing owner validation and current task/input evidence binding."""
    if reference is None:
        return None
    validate_files({"gate": reference})
    gate = load_json_object(Path(reference["path"]))
    validate_decision(gate)
    bindings = gate["EVIDENCE"].get("source_bindings", {})
    if not bindings:
        raise ValueError("current gate must bind its raw evidence")
    validate_files(bindings)
    if not any(source == assessment for source in bindings.values()):
        raise ValueError("gate does not bind the current task/input assessment")
    return gate


def plan_next(database: Path, request_path: Path, expected_request_sha256: str, *,
              use_templates: bool = False, expected_template_snapshot_sha256: str | None = None):
    """Read-only adapter; request and history must be explicitly frozen by the caller."""
    if database is None:
        raise ValueError("plan-next requires an explicit --database; production defaults are forbidden")
    if sha256_file(request_path) != require_sha256(expected_request_sha256, label="request SHA-256"):
        raise ValueError("planner request identity mismatch")
    spec = load_json_object(request_path)
    exact_keys(spec, {"schema_version", "task_id", "variant_id", "variant_sha256", "history_sha256", "kind",
                      "inputs", "assessment", "gate", "budget"})
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise ValueError("unsupported planner request version")
    for name in ("task_id", "variant_id"):
        if not isinstance(spec[name], str) or not spec[name].strip():
            raise ValueError("nonempty task and strategy identities required")
    token = history_token(database)
    if token != require_sha256(spec["history_sha256"], label="history SHA-256"):
        raise ValueError("history version mismatch")
    variant = get_event(database, "variant", spec["variant_id"])
    if sha256_json(variant) != spec["variant_sha256"] or spec["variant_id"] != spec["variant_sha256"] \
            or variant["policy_sha256"] != sha256_file(POLICY):
        raise ValueError("strategy version or policy identity mismatch")
    if spec["task_id"] not in variant["cases"]:
        raise ValueError("task is outside the strategy's frozen scope")
    _validate_settings(variant["settings"])
    validate_files(variant["sources"])
    if not isinstance(spec["inputs"], dict) or "contract" not in spec["inputs"]:
        raise ValueError("current input manifest must include a bound reaction contract")
    validate_files(spec["inputs"])
    hashes = attempt_input_hashes(spec["kind"], spec["inputs"])
    key = input_key(spec["kind"], hashes)
    contract = load_contract(Path(spec["inputs"]["contract"]["path"]))
    if contract["reaction_id"] != spec["task_id"]:
        raise ValueError("reaction contract task mismatch")
    assessment, evidence = _assessment(spec["assessment"], spec["task_id"], spec["variant_id"], key)
    gate = _current_gate(spec["gate"], spec["assessment"])
    families = resource_path("configs/ts_strategy_engine/families.yaml")
    current_fingerprint = build_fingerprint(contract)
    rules = yaml.safe_load(families.read_text(encoding="utf-8"))
    ranked, snapshot, template_errors = template_references(database, current_fingerprint, expected_template_snapshot_sha256,
                                                          enabled=use_templates)
    strategy = compose_strategy(current_fingerprint, ranked, rules)
    resources = _resource_ownership(strategy, yaml.safe_load(BACKEND_CONFIG.read_text(encoding="utf-8")))
    history = _history(database, spec["task_id"], key)
    context = {"request": spec, "assessment": assessment, "evidence": evidence, "input_key": key,
               "gate": gate, "budget": _budget(spec["budget"]), "strategy": strategy, "history": history,
               "comparison": compare_variants(database, variant["parent_id"], spec["variant_id"]) if variant["parent_id"] else None,
               "variant_settings": variant["settings"],
               "review_fields": review_field_orders(),
               "resource_ownership": resources,
               "variant_attempts_remaining": max(0, variant["attempt_budget"] - sum(
                   row["task_id"] == spec["task_id"] and row["variant_id"] is not None for row in history)),
               "retry": retry_assessment(database, spec["kind"], hashes), "lessons": task_lessons(database, spec["task_id"]),
               "pending_same_input": [row["attempt_id"] for row in history
                                      if row["input_key"] == key and row["outcome"] is None]}
    if history_token(database) != token:
        raise ValueError("history changed during planning; review a new snapshot")
    result = build_plan(context)
    if use_templates:
        if template_snapshot(database)["snapshot_sha256"] != snapshot["snapshot_sha256"]:
            raise ValueError("template registry changed during planning; capture a new snapshot")
        result["template_reference"] = reference_report(ranked, snapshot, template_errors, strategy, rules)
    result["bindings"] = {"request_sha256": expected_request_sha256, "history_sha256": token,
                          "variant_sha256": spec["variant_sha256"], "assessment": spec["assessment"],
                          "inputs": spec["inputs"], "learning_policy_sha256": sha256_file(POLICY),
                          "execution_backends_sha256": sha256_file(BACKEND_CONFIG),
                          "family_rules_sha256": sha256_file(families)}
    return result
