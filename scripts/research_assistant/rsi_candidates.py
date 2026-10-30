"""Archive all observations; surface at most one new reviewable proposal per run."""
from copy import deepcopy

from scripts.artifact_io import sha256_json

from .policies import utc_now


COMPLETE_FIELDS = ("problem", "previous_behavior", "behavior_change", "applicability", "limitations",
                   "expected_help", "added_burden", "validation_task", "evaluation")


def _candidate_key(candidate):
    # Exact content equality only. Similar wording remains a separate proposal
    # with explicit related_ids, never a claimed semantic deduplication.
    return sha256_json({k: candidate[k] for k in (*COMPLETE_FIELDS, "changes_policy_id")})


def _validate(candidate, allowed, config, state):
    if candidate["source_type"] not in config["candidate_sources"]:
        return "source type disabled"
    if not candidate["source_refs"] or not set(candidate["source_refs"]) <= allowed:
        return "unrecorded or absent source references"
    if any(not isinstance(candidate[k], str) or not candidate[k].strip() for k in COMPLETE_FIELDS):
        return "incomplete behavior or validation proposal; retained as observation"
    if candidate["changes_policy_id"] and candidate["changes_policy_id"] not in {r["definition"]["policy_id"] for r in state["policies"]}:
        return "unrecorded changed policy"
    ids = {row["candidate_id"] for row in state["candidates"]}
    if candidate["existing_candidate_id"] and candidate["existing_candidate_id"] not in ids:
        return "unrecorded existing candidate"
    if not set(candidate["related_ids"]) <= ids | {r["definition"]["policy_id"] for r in state["policies"]}:
        return "unrecorded related proposal/policy"
    return None


def _archive(state, candidate, raw_ref, allowed, config, presented, source_records):
    failure = _validate(candidate, allowed, config, state)
    if failure:
        return {"status": "quarantined_observation", "reason": failure, "raw_ref": raw_ref, "proposal": deepcopy(candidate)}
    key = _candidate_key(candidate)
    duplicate = next((r for r in state["candidates"] if r["exact_key"] == key), None)
    requested = candidate["existing_candidate_id"]
    if requested and (duplicate is None or duplicate["candidate_id"] != requested):
        return {"status": "quarantined_observation", "reason": "equivalence not established; retain related_ids instead", "raw_ref": raw_ref,
                "proposal": deepcopy(candidate)}
    occurrence = {"recorded_at": utc_now(), "raw_ref": raw_ref, "source_refs": list(candidate["source_refs"]),
                  "bound_sources": [source_records[ref] for ref in candidate["source_refs"]]}
    if duplicate:
        duplicate["occurrences"].append(occurrence)
        return {"status": "existing_candidate_source_added", "candidate_id": duplicate["candidate_id"], "raw_ref": raw_ref}
    if presented >= config["max_presented_candidates"]:
        return {"status": "deferred_observation", "reason": "one new expanded proposal per research run", "raw_ref": raw_ref, "proposal": deepcopy(candidate)}
    changed = [r["definition"]["version"] for r in state["policies"] if r["definition"]["policy_id"] == candidate["changes_policy_id"]]
    row = {"candidate_id": "candidate:" + key[:24], "exact_key": key, "status": "candidate", "proposer": "assistant",
           "proposed_at": utc_now(), "proposal": deepcopy(candidate), "occurrences": [occurrence],
           "proposed_policy_version": max(changed) + 1 if changed else 1}
    state["candidates"].append(row)
    return {"status": "candidate", "candidate_id": row["candidate_id"], "proposal": deepcopy(candidate), "raw_ref": raw_ref}


def archive_contributions(store, contributions, selection, actions, config):
    # Each record was captured in its own model turn. Later tool results cannot
    # retroactively validate an earlier candidate's invented source reference.
    outcomes, presented = [], 0
    pending_rows = [*selection["pending_feedback"], *selection["pending_observations"]]
    pending = {row["source_id"] for row in pending_rows}
    sources = {row["evidence_id"]: {"path": row["result_path"], "sha256": row["result_sha256"]} for row in actions}
    sources.update({row["source_id"]: row["reference"] for row in pending_rows})
    with store.transaction() as state:
        for contribution in contributions:
            raw_ref = store.freeze_source(contribution["raw_ref"])
            allowed = pending | set(contribution["available_action_refs"])
            source_records = {ref: store.freeze_source(sources[ref]) for ref in allowed if ref in sources}
            for observation in contribution["rsi"]["observations"]:
                valid = bool(observation["observation"].strip()) and bool(observation["source_refs"]) and set(observation["source_refs"]) <= allowed
                row = {"status": "observation" if valid else "quarantined_observation", "raw_ref": raw_ref,
                       "observation": deepcopy(observation), "recorded_at": utc_now(),
                       "source_id": "observation:" + sha256_json({"raw": raw_ref, "observation": observation}),
                       "intent": selection["task"]["intent"], "candidate_ids": [],
                       "bound_sources": [source_records[ref] for ref in observation["source_refs"] if ref in source_records]}
                state["observations"].append(row)
                outcomes.append(row)
            for candidate in contribution["rsi"]["improvement_candidates"]:
                result = _archive(state, candidate, raw_ref, allowed, config, presented, source_records)
                result.update({"source_id": "observation:" + sha256_json({"raw": raw_ref, "candidate": candidate}),
                               "intent": selection["task"]["intent"], "candidate_ids": []})
                outcomes.append(result)
                presented += result["status"] == "candidate"
                state["observations"].append(deepcopy(result))
                if result.get("candidate_id"):
                    for feedback in [*state["feedback"], *state["observations"]]:
                        if feedback["source_id"] in candidate["source_refs"]:
                            feedback["candidate_ids"] = sorted({*feedback["candidate_ids"], result["candidate_id"]})
    return outcomes
