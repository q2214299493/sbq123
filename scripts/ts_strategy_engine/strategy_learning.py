"""Bounded strategy variants and evidence-backed attempts; no job or model execution."""
from __future__ import annotations

from scripts.runtime_resources import resource_path

import copy
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from scripts.artifact_io import load_json_object, sha256_file, sha256_json
from scripts.vasp_result_gate import read_incar_values

from .learning_evidence import ATTEMPT_KINDS, attempt_input_hashes, bind_files, exact_keys, input_key, observe, validate_costs, validate_files
from .learning_store import append_event, get_event, history_token, read_events, save_event
from .registry import open_registry
from .templates import load_templates

POLICY = resource_path('configs/ts_strategy_engine/learning.yaml')


def policy() -> dict[str, Any]:
    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))


def reference_methods() -> dict[str, Any]:
    return policy()["reference_methods"]


def capture_baseline(database: Path, spec: dict[str, Any]) -> str:
    exact_keys(spec, {"task_id", "settings", "sources", "cases", "attempt_budget"})
    _validate_settings(spec["settings"])
    cases = spec["cases"]
    if not isinstance(cases, list) or not cases or any(not isinstance(v, str) or not v.strip() for v in cases):
        raise ValueError("cases must contain nonempty task IDs")
    if len(cases) != len(set(cases)) or spec["task_id"] not in cases:
        raise ValueError("cases must be unique and include the baseline task")
    if type(spec["attempt_budget"]) is not int or spec["attempt_budget"] < 1:
        raise ValueError("attempt_budget must be a positive integer, not execution authorization")
    record = {
        **spec, "schema_version": 1, "parent_id": None,
        "sources": bind_files(spec["sources"]), "policy_sha256": sha256_file(POLICY),
        "changes": {}, "rationale": "Capture existing workflow without restarting calculations",
        "observations": [], "automatic_submission": False,
    }
    return save_event(database, "variant", sha256_json(record), record)


def capture_workdir(database: Path, workdir: Path, task_id: str, sources: dict[str, str], budget: int = 5) -> str:
    """Warm-start from actual NEB inputs; absent state is not reconstructed from chat."""
    report_path = workdir / "path_generation_report.json"
    report = load_json_object(report_path)
    incar = read_incar_values(workdir / "INCAR")
    count = int(incar["IMAGES"])
    if count != report["interior_images"]:
        raise ValueError("INCAR and path report disagree on image count")
    source_paths = dict(sources)
    for relative in ("configs/execution_backends.yaml", "configs/true_fe110_production.yaml",
                     "configs/ts_strategy_engine/families.yaml", "configs/ts_strategy_engine/learning.yaml",
                     "scripts/ts_strategy_engine/strategy.py", "scripts/ts_strategy_engine/workflow.py",
                     "scripts/ts_strategy_engine/execution_gate.py", "scripts/neb_agent/submission.py"):
        source_paths[f"workflow:{relative}"] = str(resource_path(relative))
    for name in ("INCAR", "KPOINTS", "POTCAR.spec", "script.lsf", "path_generation_report.json"):
        source_paths[f"input:{name}"] = str(workdir / name)
    for index in range(count + 2):
        source_paths[f"image:{index:02d}"] = str(workdir / f"{index:02d}" / "POSCAR")
    return capture_baseline(database, {
        "task_id": task_id, "cases": [task_id], "attempt_budget": budget, "sources": source_paths,
        "settings": {
            "candidate_method": "ci_neb" if incar.get("LCLIMB", "").strip(".").lower() == "true" else "ordinary_neb",
            "initial_images": count, "interpolation_strategy": report["method_used"],
        },
    })


def _validate_settings(settings: dict[str, Any]) -> None:
    try:
        jsonschema.validate(settings, policy()["settings_schema"])
    except jsonschema.ValidationError as exc:
        raise ValueError(f"unsupported strategy setting: {exc.message}") from exc


def propose_variant(database: Path, parent_id: str, changes: dict[str, Any], rationale: str,
                    observations: list[dict[str, Any]]) -> str:
    token = history_token(database)
    parent = get_event(database, "variant", parent_id)
    validate_files(parent["sources"])
    if parent["policy_sha256"] != sha256_file(POLICY):
        raise ValueError("learning policy changed; capture a new baseline")
    if not isinstance(changes, dict) or not 1 <= len(changes) <= policy()["max_changed_fields_per_proposal"]:
        raise ValueError("each proposal must change one supported strategy field")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("an explicit causal rationale is required")
    settings = {**parent["settings"], **changes}
    _validate_settings(settings)
    if all(parent["settings"].get(key) == value for key, value in changes.items()):
        raise ValueError("proposal has no effective change")
    record = {**parent, "parent_id": parent_id, "settings": settings, "changes": changes,
              "rationale": rationale, "observations": observe(observations)}
    identity = sha256_json(record)
    variants = read_events(database, "variant")
    siblings = [v for v in variants.values() if v["parent_id"] == parent_id]
    if identity not in variants and len(siblings) >= policy()["max_candidates_per_parent"]:
        raise ValueError("candidate budget exhausted for this parent")
    return save_event(database, "variant", identity, record, expected_history=token)


def apply_variant(database: Path, variant_id: str, strategy: dict[str, Any]) -> dict[str, Any]:
    record = get_event(database, "variant", variant_id)
    validate_files(record["sources"])
    if record["policy_sha256"] != sha256_file(POLICY):
        raise ValueError("stale strategy policy")
    _validate_settings(record["settings"])
    result = copy.deepcopy(strategy)
    settings = record["settings"]
    result["neb_settings"]["initial_images"] = settings["initial_images"]
    result["interpolation_strategy"] = settings["interpolation_strategy"]
    result["learning_variant_id"] = variant_id
    result["candidate_method_preference"] = settings["candidate_method"]
    result["reference_methods"] = reference_methods()
    result["variant_status"] = "experimental_requires_existing_gates"
    if settings["candidate_method"] == "aqcat25_ba_sella" and not result["status"].startswith("STOP"):
        result["status"] = "NEEDS_BA_SELLA_CANDIDATE_HANDOFF_REVIEW"
    if settings["candidate_method"] == "matris_ml_neb_sella" and not result["status"].startswith("STOP"):
        result["status"] = "NEEDS_MATRIS_NEB_SELLA_HANDOFF_REVIEW"
    return result


def retry_assessment(database: Path, kind: str, hashes: dict[str, str]) -> dict[str, Any]:
    key = input_key(kind, hashes)
    attempts = read_events(database, "attempt")
    outcomes = read_events(database, "outcome")
    blocked, review = [], []
    for attempt_id, attempt in attempts.items():
        if attempt["input_key"] != key:
            continue
        outcome = outcomes.get(attempt_id)
        if outcome is None or outcome["status"] in {"cancelled", "stage_pass", "ts_validated"}:
            continue
        try:
            observe(outcome["observations"])
        except (OSError, ValueError):
            review.append(attempt_id)
            continue
        if outcome["status"] == "failure" and outcome["deterministic"] and outcome["root_cause_status"] == "confirmed":
            blocked.append(attempt_id)
        else:
            review.append(attempt_id)
    return {"input_key": key, "blocked_attempts": blocked, "review_attempts": review,
            "status": "BLOCKED_KNOWN_FAILURE" if blocked else "NEEDS_REVIEW" if review else "NO_KNOWN_FAILURE"}


def task_lessons(database: Path, task_id: str) -> list[dict[str, Any]]:
    """Task-local advice; similarity alone never authorizes a global method ban."""
    outcomes = read_events(database, "outcome")
    lessons = []
    for attempt_id, attempt in read_events(database, "attempt").items():
        outcome = outcomes.get(attempt_id)
        if attempt["task_id"] != task_id or not outcome or outcome["status"] not in {"failure", "unknown"}:
            continue
        try:
            observe(outcome["observations"])
            evidence_status = "current"
        except (OSError, ValueError):
            evidence_status = "needs_review"
        lessons.append({"attempt_id": attempt_id, "variant_id": attempt["variant_id"],
                        "input_key": attempt["input_key"], "failure_class": outcome["failure_class"],
                        "root_cause_status": outcome["root_cause_status"], "next_review": outcome["next_review"],
                        "evidence_status": evidence_status,
                        "scope": "exact_input_condition_only" if attempt["input_key"] else "advisory_missing_historical_inputs"})
    return lessons


def start_attempt(database: Path, spec: dict[str, Any]) -> str:
    token = history_token(database)
    exact_keys(spec, {"attempt_id", "variant_id", "task_id", "kind", "inputs", "parent_attempt_id"}, {"source_calculation_id"})
    if any(not isinstance(spec[k], str) or not spec[k].strip() for k in ("attempt_id", "variant_id", "task_id", "kind")):
        raise ValueError("attempt identity fields must be nonempty strings")
    variant = get_event(database, "variant", spec["variant_id"])
    if spec["task_id"] not in variant["cases"]:
        raise ValueError("attempt task is outside the frozen case set")
    inputs = bind_files(spec["inputs"])
    hashes = attempt_input_hashes(spec["kind"], inputs)
    record = {**spec, "inputs": inputs, "input_key": input_key(spec["kind"], hashes), "automatic_submission": False}
    attempts = read_events(database, "attempt")
    calculation_id = spec.get("source_calculation_id")
    if calculation_id is not None:
        with open_registry(database) as connection:
            if not connection.execute("SELECT 1 FROM calculations WHERE calculation_id=?", (calculation_id,)).fetchone():
                raise ValueError("source calculation is not registered")
        if any(a.get("source_calculation_id") == calculation_id and a["variant_id"] != spec["variant_id"] for a in attempts.values()):
            raise ValueError("one calculation cannot demonstrate outcomes of different strategy variants")
    if spec["attempt_id"] in attempts:
        return save_event(database, "attempt", spec["attempt_id"], record)
    same_task = [a for a in attempts.values() if a["task_id"] == spec["task_id"] and a["variant_id"] is not None]
    if len(same_task) >= variant["attempt_budget"]:
        raise ValueError("task attempt budget exhausted; review before starting a new campaign")
    if spec["parent_attempt_id"] is not None:
        parent = get_event(database, "attempt", spec["parent_attempt_id"])
        if parent["task_id"] != spec["task_id"] or "resume_checkpoint" not in inputs:
            raise ValueError("resuming requires the same task and a hash-bound resume_checkpoint")
    check = retry_assessment(database, spec["kind"], hashes)
    if check["status"] != "NO_KNOWN_FAILURE":
        raise ValueError(f"retry refused: {check['status']}")
    outcomes = read_events(database, "outcome")
    if any(a["input_key"] == record["input_key"] and name not in outcomes
           for name, a in attempts.items()):
        raise ValueError("identical attempt has an unresolved outcome")
    return save_event(database, "attempt", spec["attempt_id"], record, expected_history=token)


def _accepted_template(database: Path, template_id: str, task_id: str, calculation_id: str | None) -> dict[str, Any]:
    template = next((t for t in load_templates(database) if t["template_id"] == template_id), None)
    if (not template or not template["evidence_valid"] or template["fingerprint"]["reaction_id"] != task_id
            or not calculation_id or template["source_calculation_id"] != calculation_id):
        raise ValueError("TS success requires an existing evidence-valid Grade-A template for this reaction")
    return template


def record_outcome(database: Path, attempt_id: str, spec: dict[str, Any]) -> str:
    attempt = get_event(database, "attempt", attempt_id)
    record = _outcome_record(database, attempt, spec)
    return save_event(database, "outcome", attempt_id, record)


def revise_outcome(database: Path, attempt_id: str, spec: dict[str, Any], *,
                   previous_sha256: str, reason: str) -> str:
    """Append a reviewed correction; never overwrite the historical outcome."""
    token = history_token(database)
    previous = get_event(database, "outcome", attempt_id)
    if sha256_json(previous) != previous_sha256:
        raise ValueError("outcome changed; review the current outcome before correcting it")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("outcome correction requires a reason")
    attempt = get_event(database, "attempt", attempt_id)
    record = _outcome_record(database, attempt, spec)
    record["outcome_revision"] = {"attempt_id": attempt_id,
                                  "previous_sha256": previous_sha256, "reason": reason}
    revision_id = f"{attempt_id}::review::{sha256_json(record)}"
    return save_event(database, "outcome", revision_id, record, expected_history=token)


def _outcome_record(database: Path, attempt: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    exact_keys(spec, {"status", "failure_class", "root_cause_status", "deterministic", "reviewer",
                      "observations", "costs", "ts_template_id"})
    if spec["status"] not in {"failure", "unknown", "cancelled", "stage_pass", "ts_validated"}:
        raise ValueError("unsupported outcome; queue DONE is not a scientific success")
    if spec["failure_class"] not in policy()["failure_routes"]:
        raise ValueError("unsupported failure class")
    if spec["root_cause_status"] not in {"confirmed", "hypothesis", "unknown"} or type(spec["deterministic"]) is not bool:
        raise ValueError("root cause and determinism must be explicit")
    if not isinstance(spec["reviewer"], str) or not spec["reviewer"].strip():
        raise ValueError("a named reviewer is required for outcome interpretation")
    observations = observe(spec["observations"])
    validate_costs(spec["costs"], observations)
    if spec["status"] == "ts_validated":
        _accepted_template(database, spec["ts_template_id"], attempt["task_id"], attempt.get("source_calculation_id"))
    elif spec["ts_template_id"] is not None:
        raise ValueError("non-TS outcomes cannot claim a successful TS template")
    if spec["deterministic"] and (spec["status"] != "failure" or spec["root_cause_status"] != "confirmed"
                                  or spec["failure_class"] == "unknown"):
        raise ValueError("deterministic failure requires a confirmed, classified failure")
    return {**spec, "next_review": policy()["failure_routes"][spec["failure_class"]],
            "automatic_submission": False, "authorizes_training": False}


def import_failure(database: Path, spec: dict[str, Any]) -> str:
    """Import source evidence without fabricating the historical strategy or inputs."""
    exact_keys(spec, {"attempt_id", "task_id", "kind", "inputs", "outcome"})
    if any(not isinstance(spec[k], str) or not spec[k].strip() for k in ("attempt_id", "task_id", "kind")):
        raise ValueError("historical attempt identity must be explicit")
    if spec["outcome"].get("status") not in {"failure", "unknown"}:
        raise ValueError("historical import is restricted to failures and unknown outcomes")
    if spec["kind"] not in ATTEMPT_KINDS:
        raise ValueError("unsupported historical attempt kind")
    inputs = bind_files(spec["inputs"]) if spec["inputs"] is not None else None
    key = input_key(spec["kind"], attempt_input_hashes(spec["kind"], inputs)) if inputs else None
    attempt = {"attempt_id": spec["attempt_id"], "task_id": spec["task_id"], "kind": spec["kind"],
               "variant_id": None, "parent_attempt_id": None, "inputs": inputs, "input_key": key,
               "origin": "historical_evidence_only", "automatic_submission": False}
    result = _outcome_record(database, attempt, spec["outcome"])
    with open_registry(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        append_event(connection, "attempt", spec["attempt_id"], attempt)
        append_event(connection, "outcome", spec["attempt_id"], result)
    return spec["attempt_id"]


def compare_variants(database: Path, baseline_id: str, candidate_id: str) -> dict[str, Any]:
    baseline, candidate = (get_event(database, "variant", key) for key in (baseline_id, candidate_id))
    if baseline["cases"] != candidate["cases"] or baseline["sources"] != candidate["sources"]:
        raise ValueError("comparison requires the same frozen cases, model and source baseline")
    if baseline_id == candidate_id:
        raise ValueError("candidate must differ from baseline")
    summaries = [_variant_results(database, key, baseline["cases"]) for key in (baseline_id, candidate_id)]
    old, new = summaries
    regressions = sorted(set(old["validated_tasks"]) - set(new["validated_tasks"]))
    added = sorted(set(new["validated_tasks"]) - set(old["validated_tasks"]))
    complete = not old["unresolved_tasks"] and not new["unresolved_tasks"]
    comparable_costs = all(old["costs"][key] is not None and new["costs"][key] is not None for key in old["costs"])
    cost_improvement = bool(comparable_costs and all(new["costs"][k] <= old["costs"][k] for k in old["costs"])
                            and any(new["costs"][k] < old["costs"][k] for k in old["costs"]))
    improved = bool(added or (new["validated_tasks"] and cost_improvement))
    decision = "ELIGIBLE_FOR_REVIEW" if complete and improved and not regressions else "KEEP_BASELINE"
    if not complete:
        decision = "NEEDS_MORE_EVIDENCE"
    return {"baseline_id": baseline_id, "candidate_id": candidate_id, "cases": baseline["cases"],
            "baseline": old, "candidate": new, "added_validated_tasks": added, "regressions": regressions,
            "cost_improvement": cost_improvement, "decision": decision,
            "automatic_promotion": False, "automatic_submission": False}


def _variant_results(database: Path, variant_id: str, cases: list[str]) -> dict[str, Any]:
    attempts, outcomes = read_events(database, "attempt"), read_events(database, "outcome")
    validated, resolved, stages = set(), set(), set()
    costs = {name: 0.0 for name in ("vasp_core_hours", "gpu_hours", "force_calls")}
    missing_costs: set[str] = set()
    pending, seen = set(), set()
    for attempt_id, attempt in attempts.items():
        if attempt["variant_id"] != variant_id:
            continue
        seen.add(attempt["task_id"])
        outcome = outcomes.get(attempt_id)
        if not outcome:
            pending.add(attempt["task_id"])
            missing_costs.update(costs)
            continue
        try:
            observe(outcome["observations"])
            if outcome["status"] == "ts_validated":
                _accepted_template(database, outcome["ts_template_id"], attempt["task_id"], attempt.get("source_calculation_id"))
                validated.add(attempt["task_id"])
            if outcome["status"] in {"failure", "ts_validated"}:
                resolved.add(attempt["task_id"])
            if outcome["status"] == "stage_pass":
                stages.add(attempt["task_id"])
        except (OSError, ValueError):
            pending.add(attempt["task_id"])
            missing_costs.update(costs)
            continue
        for name in costs:
            if name in outcome["costs"]:
                costs[name] += outcome["costs"][name]
            else:
                missing_costs.add(name)
    if set(cases) - seen:
        missing_costs.update(costs)
    return {"validated_tasks": sorted(validated), "stage_pass_tasks": sorted(stages),
            "unresolved_tasks": sorted((set(cases) - resolved) | pending),
            "costs": {name: None if name in missing_costs else value for name, value in costs.items()}}
