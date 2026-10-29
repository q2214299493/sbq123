"""Stable goal/evidence/hypothesis/options contract, independent of failure classes."""
from __future__ import annotations

from jsonschema import Draft202012Validator

from scripts.ts_strategy_engine.diagnostic_advice import array_schema, object_schema

from .tools import SPECS


VERSION = "project_research_assistant_v2"
LEGACY_VERSION = "project_research_assistant_v1"
TEXT = {"type": "string", "minLength": 1, "maxLength": 2400}
IDS = {"type": "array", "items": {"type": "string"}, "uniqueItems": True, "maxItems": 16}
ITEM = object_schema({"statement": TEXT, "evidence_ids": IDS})


def answer_schema(version=VERSION):
    cost = object_schema({"status": {"enum": ["unknown", "estimate", "known"]},
                          "value": {"type": ["number", "null"], "minimum": 0},
                          "unit": {"type": ["string", "null"]}, "basis": TEXT, "evidence_ids": IDS})
    option = object_schema({"id": TEXT, "proposal": TEXT, "evidence_ids": IDS,
                            "conditions": array_schema(TEXT, 1, 5), "cost": cost,
                            "risks": array_schema(TEXT, 0, 5), "acceptance_conditions": array_schema(TEXT, 1, 5)})
    if version != LEGACY_VERSION:
        option["properties"]["blocking_gaps"] = array_schema(object_schema({"question": TEXT, "needed_artifact": TEXT, "evidence_ids": IDS}), 0, 6)
        option["required"].append("blocking_gaps")
    value = object_schema({
        "intent": {"enum": ["diagnose", "compare", "plan"]}, "goal": TEXT,
        "facts": array_schema(ITEM, 1, 8),
        "uncertainties": array_schema(object_schema({"question": TEXT,
            "availability": {"enum": ["provided", "withheld", "not_found", "not_generated", "unknown"]},
            "scope_and_basis": TEXT, "evidence_ids": IDS}), 0, 8),
        "hypotheses": array_schema(object_schema({"claim": TEXT, "supporting_evidence_ids": IDS,
            "opposing_evidence_ids": IDS, "discriminating_check": TEXT}), 0, 4),
        "options": array_schema(option, 0, 4),
        "evidence_and_calculation_plan": array_schema(object_schema({"step": TEXT,
            "prerequisites": array_schema(TEXT, 0, 6), "evidence_ids": IDS,
            "outputs_needed": array_schema(TEXT, 1, 6), "acceptance_conditions": array_schema(TEXT, 1, 6),
            "requires_owner_review": {"enum": [True]}}), 0, 8),
        "recommended_next": object_schema({"action": TEXT, "rationale": TEXT, "evidence_ids": IDS,
            "outcomes": array_schema(object_schema({"if": TEXT, "then": TEXT}), 1, 4)}),
        "new_information": array_schema(ITEM, 1, 8),
        "draft_evidence_ids": IDS, "scientific_limits": TEXT,
    })
    if version != LEGACY_VERSION:
        progress = object_schema({
            "changes": array_schema(object_schema({"previous_ref": TEXT,
                "assessment": {"enum": ["strengthened", "weakened", "unchanged", "invalidated", "pending_revalidation"]},
                "statement": TEXT, "evidence_ids": IDS}), 1, 8),
            "completed_checks": array_schema(ITEM, 0, 8), "remaining_checks": array_schema(ITEM, 0, 8), "next_product": TEXT})
        value["properties"]["progress"] = {"anyOf": [progress, {"type": "null"}]}
        value["required"].append("progress")
    return value


def response_schema(version=VERSION):
    request = object_schema({"tool": {"enum": list(SPECS)},
                             "target_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                             "query": {"type": "string", "maxLength": 2000},
                             "limit": {"type": "integer", "minimum": 1, "maximum": 40}})
    return object_schema({"kind": {"enum": ["request", "final"]},
                          "requests": array_schema(request, 0, 4),
                          "answer": {"anyOf": [answer_schema(version), {"type": "null"}]}})


def portable_schema(value):
    omitted = {"uniqueItems", "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum"}
    if isinstance(value, dict):
        return {key: portable_schema(item) for key, item in value.items() if key not in omitted}
    if isinstance(value, list):
        return [portable_schema(v) for v in value]
    return value


def citations(value):
    if isinstance(value, dict):
        found = set()
        for key, item in value.items():
            found.update(item if key.endswith("evidence_ids") else citations(item))
        return found
    if isinstance(value, list):
        return set().union(*(citations(v) for v in value))
    return set()


def _validate_non_generation(uncertainties, results):
    for row in uncertainties:
        if row["availability"] == "not_generated" and not any(
                results[identity].get("availability") == "not_generated" for identity in row["evidence_ids"]):
            raise ValueError("non-generation requires an explicit host production-state observation")


def validate_response(value, results, expected_intent, *, version=VERSION):
    Draft202012Validator(response_schema(version)).validate(value)
    if value["kind"] == "request":
        if value["answer"] is not None or not value["requests"]:
            raise ValueError("request requires host actions and no answer")
        return
    if value["requests"] or value["answer"] is None:
        raise ValueError("final requires answer only")
    answer = value["answer"]
    if expected_intent != "auto" and answer["intent"] != expected_intent:
        raise ValueError("answer intent differs from user intent")
    if not results or not citations(answer) <= set(results):
        raise ValueError("answer cites evidence never obtained by a host tool")
    for row in answer["facts"] + answer["new_information"] + [answer["recommended_next"]]:
        if not row["evidence_ids"]:
            raise ValueError("facts/new information/next step require obtained evidence")
    _validate_non_generation(answer["uncertainties"], results)
    for option in answer["options"]:
        if not option["evidence_ids"]:
            raise ValueError("candidate options require an evidence basis")
        cost = option["cost"]
        if cost["status"] == "unknown" and (cost["value"] is not None or cost["unit"] is not None):
            raise ValueError("unknown cost must remain unknown")
        if cost["status"] != "unknown" and (cost["value"] is None or not cost["unit"] or not cost["evidence_ids"]):
            raise ValueError("measured/estimated cost requires quantity/unit/source")
    for identity in answer["draft_evidence_ids"]:
        data = results[identity].get("data")
        if not isinstance(data, dict) or data.get("draft", {}).get("status") not in {"UNAPPROVED_CANDIDATE_NOT_EXECUTABLE", "UNAPPROVED_REVIEW_DRAFT"}:
            raise ValueError("draft not produced by registered workflow")
        branch = data["draft"].get("option_id")
        if branch and branch not in {row["id"] for row in answer["options"]}:
            raise ValueError("review draft must bind an actual candidate branch")
