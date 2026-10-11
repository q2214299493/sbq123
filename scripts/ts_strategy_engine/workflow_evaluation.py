"""Source-bound paired review traces, version 2. No policy lifecycle or execution."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, require_sha256, sha256_json
from .learning_evidence import exact_keys, observe, validate_files


METHOD = "paired_saved_review_traces_v2"
RULES = {"all_required_checks_pass": True, "no_per_task_regression": True,
         "strictly_fewer_review_actions_on_at_least_one_task": True}


def _text(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty text required")



def _load(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"missing workflow artifact: {path}")
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("workflow JSON artifact exceeds 1 MiB")
    return load_json_object(path)



def _source(reference: dict) -> dict:
    exact_keys(reference, {"path", "sha256"})
    require_sha256(reference["sha256"], label="workflow source SHA-256")
    validate_files({"source": reference})
    return _load(Path(reference["path"]))



def _observations(items: list) -> None:
    # Only scalars: the existing exact-type observer can verify every JSON value.
    if not isinstance(items, list) or not items or any(
            not isinstance(item, dict) or isinstance(item.get("value"), (dict, list)) for item in items):
        raise ValueError("nonempty scalar source observations required")
    for item in items:
        _source({key: item[key] for key in ("path", "sha256")})
    observe(items)



def _contract(contract: dict, inputs: dict) -> None:
    exact_keys(contract, {"method", "rules", "tasks"})
    if contract["method"] != METHOD or sha256_json(contract["rules"]) != sha256_json(RULES):
        raise ValueError("unsupported workflow evaluation method or rules")
    tasks = contract["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("evaluation tasks required")
    expected = {case["case_id"]: case for case in _source(inputs["public"])["cases"]}
    seen = set()
    for task in tasks:
        exact_keys(task, {"case_id", "task_id", "input_sha256", "required_checks"})
        case = expected.get(task["case_id"])
        if case is None or task["case_id"] in seen or task["task_id"] != case["group_id"] \
                or task["input_sha256"] != case["input_sha256"]:
            raise ValueError("evaluation task/input identity mismatch")
        seen.add(task["case_id"])
        checks = task["required_checks"]
        if not isinstance(checks, list) or not checks or any(not isinstance(c, str) or not c.strip() for c in checks) \
                or len(checks) != len(set(checks)):
            raise ValueError("unique predeclared required checks needed for every task")
    if seen != expected.keys():
        raise ValueError("evaluation must cover the frozen task set exactly")


def _identity(task: dict, record: dict, identity: str, contract_hash: str) -> dict:
    return {"policy_id": identity, "scope": record["scope"], "provenance": record["provenance"],
            "contract_sha256": contract_hash, **{key: task[key] for key in ("case_id", "task_id", "input_sha256")}}


def _identified(document: dict, expected: dict) -> None:
    if type(document["schema_version"]) is not int or document["schema_version"] != 2 \
            or any(document[key] != value for key, value in expected.items()):
        raise ValueError("version-2 review source/trace task/version/contract identity mismatch")


def _raw_source(reference: dict, expected: dict, fields: list, required_checks: list) -> dict:
    """One frozen source log per trace; arrays establish event identity and order."""
    raw = _source(reference)
    exact_keys(raw, {"schema_version", "actions", "checks"} | expected.keys())
    _identified(raw, expected)
    if not isinstance(raw["actions"], list) or not isinstance(raw["checks"], list):
        raise ValueError("raw review events and checks must be lists")
    seen_events, seen_checks = set(), set()
    for index, action in enumerate(raw["actions"]):
        exact_keys(action, {"event_id", "sequence", "field", "result"})
        _text(action["event_id"])
        if action["event_id"] in seen_events or action["field"] not in fields \
                or type(action["sequence"]) is not int or action["sequence"] != index \
                or isinstance(action["result"], (dict, list)):
            raise ValueError("invalid/duplicate raw action identity, field or sequence")
        seen_events.add(action["event_id"])
    for check in raw["checks"]:
        exact_keys(check, {"check_id", "result"})
        if check["check_id"] not in required_checks or check["check_id"] in seen_checks \
                or (check["result"] is not None and type(check["result"]) is not bool):
            raise ValueError("invalid/duplicate raw required check or boolean type")
        seen_checks.add(check["check_id"])
    return raw


def _event_observation(item: dict, source: dict, pointer: str) -> None:
    exact_keys(item, {"path", "sha256", "pointer", "value"})
    if item["sha256"] != source["sha256"] or item["pointer"] != pointer:
        raise ValueError("observation is not the bound original event at its recorded position")
    # A byte-identical path alias remains the same event, never another action.
    _observations([item])


def _actions(actions: list, raw: dict, source: dict) -> list:
    if not isinstance(actions, list) or len(actions) > len(raw["actions"]):
        raise ValueError("duplicate/invented review actions or invalid list")
    fields = []
    for index, action in enumerate(actions):
        exact_keys(action, {"event_id", "field", "observation"})
        original = raw["actions"][index]
        if action["event_id"] != original["event_id"] or action["field"] != original["field"]:
            raise ValueError("review action identity/field differs from the original event")
        _event_observation(action["observation"], source, f"/actions/{index}/result")
        if action["field"] not in fields:
            fields.append(action["field"])
    return fields


def _checks(checks: list, raw: dict, source: dict) -> dict:
    if not isinstance(checks, list) or len(checks) > len(raw["checks"]):
        raise ValueError("duplicate/invented review checks or invalid list")
    verdicts = {}
    for index, check in enumerate(checks):
        exact_keys(check, {"check_id", "observation"})
        if check["check_id"] != raw["checks"][index]["check_id"]:
            raise ValueError("required check identity differs from the original event")
        _event_observation(check["observation"], source, f"/checks/{index}/result")
        verdicts[check["check_id"]] = check["observation"]["value"]
    return verdicts


def _trace(reference: dict, task: dict, record: dict, identity: str, contract_hash: str, expected: dict) -> dict:
    trace = _source(reference)
    context = _identity(task, record, identity, contract_hash)
    exact_keys(trace, {"schema_version", "advice", "source", "actions", "checks"} | context.keys())
    _identified(trace, context)
    if sha256_json(_source(trace["advice"])) != sha256_json(expected):
        raise ValueError("review trace advice is not the frozen policy/input output")
    row = next(row for row in expected["recommendations"] if row["case_id"] == task["case_id"])
    order = row["ts_strategy_fields_to_review"]
    raw = _raw_source(trace["source"], context, order, task["required_checks"])
    fields = _actions(trace["actions"], raw, trace["source"])
    verdicts = _checks(trace["checks"], raw, trace["source"])
    if fields != order[:len(fields)]:
        raise ValueError("review trace did not follow the selected field order")
    complete = fields == order and len(trace["actions"]) == len(raw["actions"]) \
        and set(verdicts) == set(task["required_checks"]) and all(value is not None for value in verdicts.values())
    return {"review_actions": len(trace["actions"]), "checks": verdicts, "complete": complete}


def _task_verdict(measurements: dict, complete: bool) -> str:
    if not complete:
        return "NEEDS_MORE_EVIDENCE"
    if not all(all(value["checks"].values()) for value in measurements.values()):
        return "REQUIRED_CHECK_FAILED"
    before, after = measurements["parent"]["review_actions"], measurements["candidate"]["review_actions"]
    if after > before:
        return "REGRESSION"
    return "IMPROVED" if after < before else "UNCHANGED"


def compare_evaluation(identity: str, record: dict, request: dict, expected: dict) -> dict:
    """Compare only source-bound traces under the predeclared contract, per task."""
    exact_keys(request, {"schema_version", "candidate_id", "parent_id", "scope", "contract_sha256", "provenance", "pairs"})
    contract = record["evaluation_contract"]
    contract_hash = sha256_json(contract)
    if type(request["schema_version"]) is not int or request["schema_version"] != 2 \
            or any(request[key] != value for key, value in {
                "candidate_id": identity, "parent_id": record["parent_id"], "scope": record["scope"],
                "provenance": record["provenance"], "contract_sha256": contract_hash}.items()):
        raise ValueError("evaluation binding differs from predeclared version-2 experiment")
    if not isinstance(request["pairs"], list):
        raise ValueError("paired trace sources required")
    tasks = {task["case_id"]: task for task in contract["tasks"]}
    rows, seen, gaps = [], set(), []
    for pair in request["pairs"]:
        exact_keys(pair, {"case_id", "parent", "candidate"})
        if pair["case_id"] not in tasks or pair["case_id"] in seen:
            raise ValueError("wrong or duplicate evaluation case")
        seen.add(pair["case_id"])
        measurements = {}
        for name, policy_id in (("parent", record["parent_id"]), ("candidate", identity)):
            measurements[name] = (None if pair[name] is None else
                                  _trace(pair[name], tasks[pair["case_id"]], record, policy_id, contract_hash, expected[name]))
        complete = all(value is not None and value["complete"] for value in measurements.values())
        if not complete:
            gaps.append(f"{pair['case_id']}: missing/incomplete comparable review trace or required checks")
        rows.append({"case_id": pair["case_id"], "verdict": _task_verdict(measurements, complete), **measurements})
    gaps.extend(f"{case_id}: missing paired traces" for case_id in sorted(tasks.keys() - seen))
    if gaps:
        status = "NEEDS_MORE_EVIDENCE"
    else:
        nonregression = all(row["verdict"] in {"IMPROVED", "UNCHANGED"} for row in rows)
        improvement = any(row["verdict"] == "IMPROVED" for row in rows)
        status = "AWAITING_HUMAN_REVIEW" if nonregression and improvement else "NOT_SUPPORTED"
    return {"status": status, "tasks": rows, "evidence_gaps": gaps,
            "metric": "recorded_review_action_count", "scientific_success": "NOT_EVALUATED",
            "compute_cost": "NOT_MEASURED", "automatic_acceptance": False}
