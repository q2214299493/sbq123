"""Deterministic current-state selection, shared by new runs and continuations."""
from copy import deepcopy
import json
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_json

from .policies import PolicyStore, checked_reference, utc_now
from .rsi_contract import SOURCE_TYPES


DEFAULTS = {"mode": "accepted", "max_active_policies": 2, "max_policy_chars": 10000,
            "max_presented_candidates": 1, "candidate_sources": SOURCE_TYPES, "show_usage": True,
            "max_pending_feedback": 4, "max_feedback_chars": 5000, "trial_policy_ids": [],
            "exclude_policy_ids": [], "include_pending_feedback": True}


def settings(project, value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {*DEFAULTS, "store"}:
        raise ValueError("unsupported RSI configuration")
    config = {**deepcopy(DEFAULTS), "store": str(Path(project).resolve() / "data" / "research_assistant_rsi"), **deepcopy(value)}
    if config["mode"] not in {"accepted", "off"}:
        raise ValueError("RSI mode must be accepted or off")
    for key, upper in (("max_active_policies", 20), ("max_policy_chars", 40000), ("max_presented_candidates", 1),
                       ("max_pending_feedback", 20), ("max_feedback_chars", 16000)):
        if type(config[key]) is not int or not 0 <= config[key] <= upper:
            raise ValueError("invalid RSI budget: " + key)
    for key in ("show_usage", "include_pending_feedback"):
        if type(config[key]) is not bool:
            raise ValueError("invalid RSI boolean: " + key)
    for key in ("candidate_sources", "trial_policy_ids", "exclude_policy_ids"):
        if not isinstance(config[key], list) or any(not isinstance(v, str) or not v for v in config[key]):
            raise ValueError("invalid RSI list: " + key)
    if not set(config["candidate_sources"]) <= set(SOURCE_TYPES) or not isinstance(config["store"], str) or not config["store"]:
        raise ValueError("invalid RSI sources/store")
    if not Path(config["store"]).is_absolute():
        raise ValueError("RSI store must have an explicit absolute path")
    config["store"] = str(Path(config["store"]).absolute())
    return config


def _current(state, config):
    latest = {}
    for row in state["policies"]:
        definition = row["definition"]
        eligible = row["status"] in {"accepted", "disabled"} or (row["status"] == "trial" and definition["policy_id"] in config["trial_policy_ids"])
        if eligible and definition["version"] > latest.get(definition["policy_id"], {"definition": {"version": 0}})["definition"]["version"]:
            latest[definition["policy_id"]] = row
    replaced = {identity for row in latest.values() if row["status"] in {"accepted", "trial"} for identity in row["definition"]["supersedes"]}
    return [row for identity, row in latest.items() if identity not in replaced]


def _reason(row, task, config):
    definition, scope = row["definition"], row["definition"]["scope"]
    if row["status"] == "disabled":
        return "disabled", None
    if definition["policy_id"] in config["exclude_policy_ids"]:
        return "experimental_exclusion", None
    if str(Path(scope["project"]).resolve()) != task["project"] or task["intent"] not in scope["intents"]:
        return "project_or_intent_mismatch", None
    if not set(scope["required_tools"]) <= set(task["available_tools"]):
        return "required_capability_unavailable", None
    text = (task["goal"] + "\n" + task["update"]).casefold()
    matched = [v for v in scope["goal_terms_any"] if v.casefold() in text]
    if any(v.casefold() in text for v in scope["excluded_goal_terms_any"]) or (scope["goal_terms_any"] and not matched):
        return "trigger_not_matched", None
    return None, {"basis": "literal user goal/update and registered capabilities; content applicability still needs review",
                  "matched_terms": matched, "feature_sources": ["current_user_goal", "current_update"], "specificity": len(matched)}


def _feedback(state, task, config):
    if not config["include_pending_feedback"] or task["mode"] == "evaluation" or not config["max_pending_feedback"] or not config["max_feedback_chars"]:
        return []
    selected, used = [], 0
    for row in sorted(state["feedback"], key=lambda v: v["recorded_at"], reverse=True):
        if row["candidate_ids"] or (task["intent"] != "auto" and row["intent"] not in {task["intent"], "auto"}):
            continue
        checked_reference(row["reference"])
        value = load_json_object(Path(row["reference"]["path"]))
        entry = {**row, "usage_feedback": value["usage_feedback"], "authority": "later user feedback; interpretation, not research fact or accepted policy"}
        size = len(json.dumps(entry, ensure_ascii=False))
        if used + size <= config["max_feedback_chars"] and len(selected) < config["max_pending_feedback"]:
            selected.append(entry)
            used += size
    return selected


def _observations(state, task, config):
    if not config["include_pending_feedback"] or task["mode"] == "evaluation" or not config["max_pending_feedback"] or not config["max_feedback_chars"]:
        return []
    selected, used = [], 0
    for row in reversed(state["observations"]):
        if row["status"] not in {"observation", "deferred_observation"} or row.get("candidate_ids") \
                or (task["intent"] != "auto" and row.get("intent") not in {task["intent"], "auto"}):
            continue
        checked_reference(row["raw_ref"])
        entry = {"source_id": row["source_id"], "reference": row["raw_ref"],
                 "observation": row.get("observation", row.get("proposal")), "authority": "unaccepted earlier observation"}
        size = len(json.dumps(entry, ensure_ascii=False))
        if used + size <= config["max_feedback_chars"] and len(selected) < config["max_pending_feedback"]:
            selected.append(entry)
            used += size
    return selected


def model_context(selection):
    # Keep experiment exclusions, disabled IDs and other unselected policy text
    # host-only. Even a descriptive excluded policy ID could leak a baseline rule.
    return {"selected_policies": selection["selected_policies"], "pending_feedback": selection["pending_feedback"],
            "pending_observations": selection["pending_observations"],
            "max_presented_candidates": selection["config"]["max_presented_candidates"], "authority": selection["authority"]}


def select_policies(task, store: PolicyStore, config):
    state = store.read()
    selected, skipped, pool = [], [], []
    if config["mode"] != "off":
        for row in _current(state, config):
            reason, basis = _reason(row, task, config)
            if reason:
                skipped.append({"policy_id": row["definition"]["policy_id"], "reason": reason})
            else:
                pool.append({**deepcopy(row), "selection_reason": basis})
    groups = {}
    for row in pool:
        group = row["definition"]["conflict_group"]
        if group:
            groups.setdefault(group, []).append(row["definition"]["policy_id"])
    used, equivalents = 0, set()
    for row in sorted(pool, key=lambda v: (-v["selection_reason"]["specificity"], -v["definition"]["priority"], v["definition"]["policy_id"])):
        definition = row["definition"]
        size = len(json.dumps(row, ensure_ascii=False))
        equivalent = definition["equivalence_key"] or ("exact:" + sha256_json({k: definition[k] for k in ("scope", "behavior_change", "checks")}))
        reason = ("unresolved_explicit_conflict" if len(groups.get(definition["conflict_group"], [])) > 1 else
                  "explicit_or_exact_duplicate" if equivalent in equivalents else
                  "policy_budget" if len(selected) >= config["max_active_policies"] or used + size > config["max_policy_chars"] else None)
        if reason:
            skipped.append({"policy_id": definition["policy_id"], "reason": reason})
            continue
        for reference in row["frozen_sources"]:
            checked_reference(reference)
        selected.append(row)
        equivalents.add(equivalent)
        used += size
    feedback = _feedback(state, task, config)
    remaining = {**config, "max_pending_feedback": config["max_pending_feedback"] - len(feedback),
                 "max_feedback_chars": max(0, config["max_feedback_chars"] - sum(len(json.dumps(row, ensure_ascii=False)) for row in feedback))}
    return {"schema_version": 1, "frozen_at": utc_now(), "task": deepcopy(task), "config": deepcopy(config),
            "selected_policies": selected, "not_selected": skipped, "pending_feedback": feedback,
            "pending_observations": _observations(state, task, remaining),
            "authority": "optional behavioral advice only; scientific protocols and execution boundaries remain mandatory"}
