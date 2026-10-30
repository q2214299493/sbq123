"""Declarative RSI data contracts; none of these fields grants tool authority."""
from scripts.ts_strategy_engine.diagnostic_advice import array_schema, object_schema


TEXT = {"type": "string", "maxLength": 2400}
NONEMPTY = {**TEXT, "minLength": 1}
IDS = array_schema({"type": "string", "maxLength": 160}, 0, 16)
SOURCE_TYPES = ["correction", "repeated_work", "confirmed_success", "unmet_goal"]
REFERENCE = object_schema({"path": NONEMPTY, "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}})
SCOPE = object_schema({
    "project": NONEMPTY, "intents": array_schema({"enum": ["auto", "diagnose", "compare", "plan"]}, 1, 4),
    "required_tools": IDS, "goal_terms_any": array_schema(NONEMPTY, 0, 16),
    "excluded_goal_terms_any": array_schema(NONEMPTY, 0, 16), "limitations": NONEMPTY})
CHECKS = object_schema({"ordered_tool_groups": array_schema(array_schema(NONEMPTY, 1, 12), 0, 6),
                        "read_search_hit": {"type": "boolean"}, "require_output_citation": {"type": "boolean"}})
DEFINITION = object_schema({
    "policy_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,79}$"},
    "version": {"type": "integer", "minimum": 1}, "proposed_at": NONEMPTY,
    "proposer": {"enum": ["assistant", "human_seed", "external_proposal", "user"]},
    "source_refs": array_schema(REFERENCE, 1, 16), "scope": SCOPE,
    "previous_behavior": NONEMPTY, "behavior_change": NONEMPTY, "expected_help": NONEMPTY,
    "added_burden": NONEMPTY, "validation_task": NONEMPTY, "evaluation": NONEMPTY,
    "required_checks": array_schema(NONEMPTY, 1, 12), "checks": CHECKS,
    "priority": {"type": "integer", "minimum": 0, "maximum": 100},
    "equivalence_key": TEXT, "conflict_group": TEXT, "supersedes": IDS})


def response_fields():
    # Empty/incomplete proposal text is retained as an observation by host business
    # validation, rather than causing a format-repair research rerun.
    candidate = object_schema({
        "source_type": {"enum": SOURCE_TYPES}, "source_refs": IDS,
        "problem": TEXT, "previous_behavior": TEXT, "behavior_change": TEXT,
        "applicability": TEXT, "limitations": TEXT, "expected_help": TEXT, "added_burden": TEXT,
        "validation_task": TEXT, "evaluation": TEXT, "existing_candidate_id": {"type": ["string", "null"]},
        "changes_policy_id": {"type": ["string", "null"]}, "related_ids": IDS})
    application = object_schema({
        "policy_id": NONEMPTY, "version": {"type": "integer", "minimum": 1},
        "content_sha256": NONEMPTY, "intent": TEXT, "action_refs": IDS, "output_refs": IDS})
    observation = object_schema({"source_type": {"enum": SOURCE_TYPES}, "source_refs": IDS, "observation": TEXT})
    return object_schema({"applications": array_schema(application, 0, 12),
                          "observations": array_schema(observation, 0, 16),
                          "improvement_candidates": array_schema(candidate, 0, 8)})
