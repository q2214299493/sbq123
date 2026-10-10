"""Replay saved artifact snapshots; never read merged outcomes or execute actions."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.artifact_io import load_json_object, require_sha256, sha256_file, sha256_json, write_json_exclusive

from .learning_cases import MAX_SOURCE_BYTES
from .learning_evidence import exact_keys, observe, validate_costs, validate_files
from .next_review import recommend_next_reviews
from .strategy_learning import policy


def _observe(item: dict[str, Any]) -> dict[str, Any]:
    exact_keys(item, {"path", "sha256", "pointer", "value"})
    if Path(item["path"]).stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("replay needs small saved JSON snapshots")
    observe([item])
    return item


def _identity(item: dict[str, Any]) -> tuple[str, str]:
    return str(Path(item["path"]).resolve()), item["sha256"]


def _time(item: dict[str, Any]) -> datetime:
    _observe(item)
    if not isinstance(item["value"], str):
        raise ValueError("event timestamp must be a saved string")
    value = datetime.fromisoformat(item["value"])
    if value.utcoffset() is None:
        raise ValueError("event timestamp needs an explicit timezone")
    return value


def _event(event: dict[str, Any], seen: set[str]) -> datetime:
    exact_keys(event, {"event_id", "at", "job", "fact"})
    name = event["event_id"]
    if not isinstance(name, str) or not name.strip() or name in seen:
        raise ValueError("duplicate or empty replay event ID")
    seen.add(name)
    at = _time(event["at"])
    for key in ("job", "fact"):
        _observe(event[key])
        if _identity(event[key]) != _identity(event["at"]):
            raise ValueError("event facts and identity must belong to its timestamped snapshot")
    if not isinstance(event["job"]["value"], str) or not event["job"]["value"].strip():
        raise ValueError("event job identity must be nonempty")
    return at


def _pre_evidence(trace: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    selected = trace["evidence"]
    if not isinstance(selected, list) or not selected:
        raise ValueError("missing decision-time evidence")
    visible = {item["evidence_id"]: item for item in case["evidence"]}
    seen = set()
    for item in selected:
        exact_keys(item, {"evidence_id", "source", "links"})
        name, source = item["evidence_id"], _observe(item["source"])
        if name in seen or name not in visible:
            raise ValueError("missing, fabricated or repeated replay evidence ID")
        seen.add(name)
        public = visible[name]
        if public != {"evidence_id": name, "pointer": source["pointer"],
                      "value": source["value"], "source_sha256": source["sha256"]}:
            raise ValueError("replay source differs from frozen public evidence")
        parent = _identity(trace["decision"]["at"])
        if not isinstance(item["links"], list):
            raise ValueError("availability links must be a list")
        for index, link in enumerate(item["links"]):
            _observe(link)
            if _identity(link) != parent:
                raise ValueError("evidence lacks a decision-time hash witness")
            require_sha256(link["value"], label="availability binding")
            # The next link supplies the child path; its bytes must match the witnessed hash.
            child = item["links"][index + 1] if index + 1 < len(item["links"]) else source
            parent = (str(Path(child["path"]).resolve()), link["value"])
        if parent != _identity(source):
            raise ValueError("source was not hash-bound at the decision cutoff")
    if seen != set(visible):
        raise ValueError("every public evidence item needs a historical availability witness")
    return selected


def _classification(trace: dict[str, Any], case: dict[str, Any], sources: list[dict[str, Any]]) -> str | None:
    item = trace["recorded_classification"]
    if item is None:
        return None
    _observe(item)
    record = load_json_object(Path(item["path"]))
    # Existing saved import requests are retrospective comparisons, never decision inputs.
    if item["pointer"] != "/outcome/failure_class" or record.get("task_id") != case["group_id"] \
            or record["outcome"].get("status") != "failure":
        raise ValueError("historical classification belongs to a different task")
    hashes = {source["source"]["sha256"] for source in sources}
    if not any(obs.get("sha256") in hashes for obs in record["outcome"]["observations"]):
        raise ValueError("historical classification lacks this failure's source binding")
    if item["value"] not in policy()["failure_routes"]:
        raise ValueError("unknown historical failure class")
    return item["value"]


def _aftermath(trace: dict[str, Any], cutoff: datetime, task: str, seen: set[str]) -> dict[str, Any]:
    action = trace["action"]
    action_time = _event(action, seen)
    parent, action_task = _observe(trace["action_parent"]), _observe(trace["action_task"])
    if action_time <= cutoff or _identity(parent) != _identity(action["at"]) \
            or parent["value"] != trace["decision"]["at"]["sha256"] \
            or _identity(action_task) != _identity(action["at"]) or action_task["value"] != task:
        raise ValueError("action is not a later, hash-linked event for this task")
    authorized = False
    if trace["authorization"] is not None:
        authorization = trace["authorization"]
        exact_keys(authorization, {"event", "binding", "task"})
        auth_time = _event(authorization["event"], seen)
        binding, auth_task = _observe(authorization["binding"]), _observe(authorization["task"])
        authorized = (auth_time <= action_time and authorization["event"]["fact"]["value"] is True
                      and authorization["event"]["job"]["value"] == trace["decision"]["job"]["value"]
                      and _identity(binding) == _identity(action["at"])
                      and binding["value"] == authorization["event"]["at"]["sha256"]
                      and _identity(auth_task) == _identity(authorization["event"]["at"])
                      and auth_task["value"] == task)
    previous = action_time
    for event in trace["after"]:
        at = _event(event, seen)
        if at <= previous or event["job"]["value"] != action["job"]["value"]:
            raise ValueError("subsequent observation is out of order or belongs to another job")
        previous = at
    costs = {}
    for item in trace["costs"]:
        _observe(item)
        if _identity(item) not in {_identity(event["at"]) for event in trace["after"]}:
            raise ValueError("cost must come from a subsequent observation snapshot")
        name = item["pointer"].rsplit("/", 1)[-1]
        if name in costs:
            raise ValueError("duplicate cost observation")
        costs[name] = item["value"]
    validate_costs(costs, trace["costs"])
    return {"recorded_next_action": action, "recorded_authorization_verified": authorized,
            "subsequent_observations": trace["after"], "verified_costs": costs}


def _trace(trace: dict[str, Any], case: dict[str, Any], recommendation: dict[str, Any],
           seen: set[str], earlier: list[dict[str, Any]]) -> dict[str, Any]:
    exact_keys(trace, {"case_id", "decision", "task", "failure_job", "request", "evidence", "action", "action_parent",
                       "action_task", "authorization", "after", "costs", "recorded_classification"})
    if not isinstance(trace["after"], list) or not isinstance(trace["costs"], list):
        raise ValueError("subsequent observations and costs must be lists")
    if trace["decision"] is None or trace["action"] is None or not trace["after"]:
        return {"case_id": trace["case_id"], "status": "UNREPLAYABLE",
                "evidence_gaps": ["missing timestamped decision, action or subsequent observation"]}
    cutoff = _event(trace["decision"], seen)
    sources = _pre_evidence(trace, case)
    task, request, job = _observe(trace["task"]), _observe(trace["request"]), _observe(trace["failure_job"])
    if task["value"] != case["group_id"] or _identity(task) not in {_identity(s["source"]) for s in sources} \
            or _identity(request) != _identity(trace["decision"]["at"]) or _identity(job) != _identity(task) \
            or job["value"] != trace["decision"]["job"]["value"]:
        raise ValueError("decision task or request belongs to an unbound source")
    require_sha256(request["value"], label="recorded request")
    if earlier and cutoff <= datetime.fromisoformat(earlier[-1]["decision_at"]):
        raise ValueError("replay decisions must be in strict chronological order")
    aftermath = _aftermath(trace, cutoff, case["group_id"], seen)
    recorded_class = _classification(trace, case, sources)
    matches = None if recorded_class is None else recommendation["next_review"] == policy()["failure_routes"][recorded_class]
    prior = [row["case_id"] for row in earlier if row["task_id"] == case["group_id"]
             and row["request_sha256"] == request["value"]]
    gaps = ["exact runtime/input retry identity not established", "action-to-route semantic equivalence needs owning review"]
    if not aftermath["verified_costs"]:
        gaps.append("no verifiable cost observations")
    if recorded_class is None:
        gaps.append("no bound retrospective failure classification")
    if not aftermath["recorded_authorization_verified"]:
        gaps.append("recorded action lacks a verified authorization binding")
    row = {"case_id": trace["case_id"], "status": "REPLAYABLE", "task_id": case["group_id"],
           "decision_at": cutoff.isoformat(), "decision": trace["decision"], "decision_before_evidence": sources,
           "task_source": task, "failure_job_source": job, "request_source": request,
           "request_sha256": request["value"], "next_review": recommendation["next_review"],
           "saved_advice_fields_to_review": recommendation["ts_strategy_fields_to_review"],
           "ts_strategy_fields_to_review": recommendation["ts_strategy_fields_to_review"] if matches is True else [],
           "recorded_classification": trace["recorded_classification"], "route_matches_recorded_classification": matches,
           "prior_same_request_cases": prior, "exact_retry_condition_verified": False,
           "authorization": trace["authorization"], "action_parent": trace["action_parent"],
           "requires_further_review": True, "evidence_gaps": gaps, **aftermath}
    earlier.append(row)
    return row


def _unreplayable(item: dict[str, Any], seen: set[str]) -> dict[str, Any]:
    exact_keys(item, {"case_id", "evidence_gaps"}, {"sources"})
    name, gaps, sources = item["case_id"], item["evidence_gaps"], item.get("sources", [])
    if not isinstance(name, str) or not name.strip() or name in seen \
            or not isinstance(gaps, list) or not gaps \
            or any(not isinstance(gap, str) or not gap.strip() for gap in gaps) or not isinstance(sources, list):
        raise ValueError("duplicate or unexplained unreplayable case")
    for source in sources:
        exact_keys(source, {"path", "sha256"})
    validate_files({str(index): source for index, source in enumerate(sources)})
    seen.add(name)
    return {**item, "sources": sources, "status": "UNREPLAYABLE"}


def replay_history(spec_path: Path, report_path: Path, expected_spec_sha256: str) -> dict[str, Any]:
    """Verify a caller-frozen manifest, Phase 3B advice and saved temporal witnesses."""
    if sha256_file(spec_path) != require_sha256(expected_spec_sha256, label="expected replay manifest SHA-256"):
        raise ValueError("replay manifest differs from its explicitly supplied identity")
    if spec_path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("replay manifest exceeds the snapshot size limit")
    spec = load_json_object(spec_path)
    exact_keys(spec, {"schema_version", "public", "answers", "advice", "traces", "unreplayable"})
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise ValueError("unsupported replay manifest")
    if not isinstance(spec["traces"], list) or not spec["traces"] or not isinstance(spec["unreplayable"], list):
        raise ValueError("replay needs a nonempty trace list and an unreplayable list")
    for name in ("public", "answers", "advice"):
        exact_keys(spec[name], {"path", "sha256"})
    validate_files({name: spec[name] for name in ("public", "answers", "advice")})
    if any(Path(spec[name]["path"]).stat().st_size > MAX_SOURCE_BYTES for name in ("public", "answers", "advice")):
        raise ValueError("replay input exceeds the snapshot size limit")
    public = load_json_object(Path(spec["public"]["path"]))
    advice = load_json_object(Path(spec["advice"]["path"]))
    with TemporaryDirectory(prefix="ts-replay-validation-") as temporary:
        current = recommend_next_reviews(Path(spec["public"]["path"]), Path(spec["answers"]["path"]),
                                         Path(temporary) / "advice.json", sha256_json(public))
    if sha256_json(current) != sha256_json(advice):
        raise ValueError("saved advice is stale or differs from existing Phase 3B validation")
    cases = {case["case_id"]: case for case in public["cases"]}
    recommendations = {row["case_id"]: row for row in advice["recommendations"]}
    rows, seen_cases, seen_events, earlier = [], set(), set(), []
    for trace in spec["traces"]:
        name = trace["case_id"]
        if name in seen_cases or name not in cases:
            raise ValueError("duplicate or unknown replay case")
        seen_cases.add(name)
        rows.append(_trace(trace, cases[name], recommendations[name], seen_events, earlier))
    if seen_cases != set(cases):
        raise ValueError("replay traces must cover exactly the frozen advice cases")
    for item in spec["unreplayable"]:
        rows.append(_unreplayable(item, seen_cases))
    report = {"schema_version": 1, "status": "ADVISORY_ONLY_NOT_AUTHORIZED",
              "spec_sha256": sha256_file(spec_path), "advice_sha256": spec["advice"]["sha256"],
              "replayable_count": len(earlier), "records": rows, "automatic_execution": False,
              "scientific_claims_validated": False, "counterfactual_benefits_established": False}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(report_path, report)
    return report
