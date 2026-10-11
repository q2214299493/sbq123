"""Bounded review-order experiments. Local immutable artifacts, no execution authority."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.artifact_io import load_json_object, require_sha256, sha256_file, sha256_json, write_json_exclusive

from .learning_evidence import exact_keys, observe, validate_files
from .next_review import recommend_next_reviews, review_field_orders
from .strategy_learning import POLICY


METHOD = "paired_saved_review_traces_v1"
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


def _engine() -> dict:
    return {"policy_sha256": sha256_file(POLICY), "advice_sha256": sha256_file(Path(__file__).with_name("next_review.py")),
            "loop_sha256": sha256_file(Path(__file__)), "orders": review_field_orders()}


def _path(store: Path, kind: str, identity: str) -> Path:
    require_sha256(identity, label="workflow artifact identity")
    return store / kind / f"{identity}.json"


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if sha256_json(_load(path)) != sha256_json(payload):
            raise ValueError("conflicting immutable workflow artifact")
        return
    write_json_exclusive(path, payload)


@contextmanager
def _writing(store: Path):
    """Serialize local mutations, including competing sibling accept decisions."""
    store.mkdir(parents=True, exist_ok=True)
    lock = store / ".write.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink()


def _advice(inputs: dict) -> dict:
    exact_keys(inputs, {"public", "answers"})
    public = _source(inputs["public"])
    _source(inputs["answers"])
    with TemporaryDirectory(prefix="workflow-advice-") as directory:
        return recommend_next_reviews(Path(inputs["public"]["path"]), Path(inputs["answers"]["path"]),
                                      Path(directory) / "advice.json", sha256_json(public))


def _baseline_sources(record: dict) -> None:
    _advice(record["inputs"])
    _observations(record["observations"])
    public = _source(record["inputs"]["public"])
    for case in public["cases"]:
        for evidence in case["evidence"]:
            if not any(item["sha256"] == evidence["source_sha256"] and item["pointer"] == evidence["pointer"]
                       and sha256_json(item["value"]) == sha256_json(evidence["value"])
                       for item in record["observations"]):
                raise ValueError("public evidence lacks an original-source observation")


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


def _change(parent_orders: dict, changes: dict) -> dict:
    if not isinstance(changes, dict) or len(changes) != 1:
        raise ValueError("exactly one review order must change")
    failure_class, order = next(iter(changes.items()))
    old = parent_orders.get(failure_class)
    if old is None or not isinstance(order, list) or any(not isinstance(field, str) for field in order) \
            or len(order) != len(old) or set(order) != set(old) or order == old:
        raise ValueError("change must be a nontrivial permutation of existing review fields")
    return {**parent_orders, failure_class: order}


def _policy(store: Path, identity: str, ancestors: tuple = ()) -> dict:
    if identity in ancestors or len(ancestors) >= 32:
        raise ValueError("invalid or excessively deep policy ancestry")
    record = _load(_path(store, "policies", identity))
    if sha256_json(record) != identity or record.get("schema_version") != 1 or type(record["schema_version"]) is not int:
        raise ValueError("policy identity/schema mismatch")
    if record.get("engine") != _engine():
        raise ValueError("stale workflow policy engine binding")
    _text(record["scope"])
    if record["provenance"] not in {"saved_real", "synthetic"}:
        raise ValueError("explicit provenance required")
    common = {"schema_version", "kind", "engine", "scope", "provenance", "inputs", "orders", "observations"}
    if record["kind"] == "baseline":
        exact_keys(record, common)
        if record["orders"] != review_field_orders():
            raise ValueError("baseline is not the existing advice order")
        _baseline_sources(record)
    elif record["kind"] == "candidate":
        exact_keys(record, common | {"parent_id", "changes", "rationale", "evaluation_contract"})
        parent = _policy(store, record["parent_id"], (*ancestors, identity))
        if parent["kind"] == "candidate":
            _accepted(store, record["parent_id"], parent)
        if any(record[key] != parent[key] for key in ("scope", "provenance", "inputs")) \
                or record["orders"] != _change(parent["orders"], record["changes"]):
            raise ValueError("candidate differs from parent scope/input/order binding")
        _text(record["rationale"])
        _observations(record["observations"])
        _contract(record["evaluation_contract"], record["inputs"])
    else:
        raise ValueError("unsupported workflow policy kind")
    return record


def create_baseline(store: Path, request: dict) -> dict:
    exact_keys(request, {"scope", "provenance", "inputs", "observations"})
    record = {"schema_version": 1, "kind": "baseline", "engine": _engine(),
              "orders": review_field_orders(), **request}
    _text(record["scope"])
    if record["provenance"] not in {"saved_real", "synthetic"}:
        raise ValueError("explicit provenance required")
    _baseline_sources(record)
    identity = sha256_json(record)
    with _writing(store):
        _save(_path(store, "policies", identity), record)
    return policy_status(store, identity)


def _current_parent(store: Path, identity: str, excluding: str | None = None) -> None:
    for path in (store / "decisions").glob("*.json"):
        decision = _load(path)
        if decision.get("decision") == "ACCEPT" and path.stem != excluding:
            candidate = _load(_path(store, "policies", path.stem))
            if candidate.get("parent_id") == identity:
                accepted = _policy(store, path.stem)
                _accepted(store, path.stem, accepted)
                raise ValueError("stale parent: an accepted successor already exists")


def _unique_order(store: Path, identity: str, record: dict) -> None:
    for path in (store / "policies").glob("*.json"):
        other = _load(path)
        if path.stem != identity and other.get("parent_id") == record["parent_id"] and other.get("orders") == record["orders"]:
            raise ValueError("duplicate candidate order for this parent; retain the existing candidate")


def propose_policy(store: Path, request: dict) -> dict:
    exact_keys(request, {"parent_id", "scope", "changes", "rationale", "observations", "evaluation_contract"})
    with _writing(store):
        parent = _policy(store, request["parent_id"])
        if parent["kind"] == "candidate":
            _accepted(store, request["parent_id"], parent)
        if request["scope"] != parent["scope"]:
            raise ValueError("proposal scope differs from parent")
        _current_parent(store, request["parent_id"])
        orders = _change(parent["orders"], request["changes"])
        _text(request["rationale"])
        _observations(request["observations"])
        _contract(request["evaluation_contract"], parent["inputs"])
        record = {"schema_version": 1, "kind": "candidate", "engine": parent["engine"],
                  "provenance": parent["provenance"], "inputs": parent["inputs"], "orders": orders, **request}
        identity = sha256_json(record)
        _unique_order(store, identity, record)
        _save(_path(store, "policies", identity), record)
    return policy_status(store, identity)


def _expected_advice(store: Path, record: dict, identity: str) -> dict:
    advice = _advice(record["inputs"])
    for row in advice["recommendations"]:
        row["ts_strategy_fields_to_review"] = (record["orders"].get(row["failure_class"], [])
                                                if row["causal_status"] != "unknown" else [])
    advice["workflow_strategy"] = {"policy_id": identity, "scope": record["scope"],
                                   "mode": "offline_evaluation", "provenance": record["provenance"]}
    return advice


def _trace(reference: dict, task: dict, record: dict, identity: str, contract_hash: str, expected: dict) -> dict:
    trace = _source(reference)
    exact_keys(trace, {"schema_version", "provenance", "policy_id", "scope", "contract_sha256", "case_id",
                       "task_id", "input_sha256", "advice", "actions", "checks"})
    if type(trace["schema_version"]) is not int or trace["schema_version"] != 1 \
            or any(trace[key] != value for key, value in {
                "policy_id": identity, "scope": record["scope"], "provenance": record["provenance"],
                "contract_sha256": contract_hash, **{key: task[key] for key in ("case_id", "task_id", "input_sha256")}
            }.items()):
        raise ValueError("review trace task/version/contract identity mismatch")
    if sha256_json(_source(trace["advice"])) != sha256_json(expected):
        raise ValueError("review trace advice is not the frozen policy/input output")
    row = next(row for row in expected["recommendations"] if row["case_id"] == task["case_id"])
    actions, fields, events = trace["actions"], [], set()
    if not isinstance(actions, list):
        raise ValueError("recorded review actions must be a list")
    for action in actions:
        exact_keys(action, {"event_id", "field", "observation"})
        _text(action["event_id"])
        if action["event_id"] in events or action["field"] not in row["ts_strategy_fields_to_review"]:
            raise ValueError("duplicate review event or forbidden review field")
        events.add(action["event_id"])
        _observations([action["observation"]])
        if action["field"] not in fields:
            fields.append(action["field"])
    checks = trace["checks"]
    if not isinstance(checks, list):
        raise ValueError("recorded checks must be a list")
    verdicts = {}
    for check in checks:
        exact_keys(check, {"check_id", "observation"})
        if check["check_id"] in verdicts or check["check_id"] not in task["required_checks"]:
            raise ValueError("unexpected or duplicate required check")
        _observations([check["observation"]])
        value = check["observation"]["value"]
        if value is not None and type(value) is not bool:
            raise ValueError("required-check observation must be boolean or unmeasured null")
        verdicts[check["check_id"]] = value
    complete = fields == row["ts_strategy_fields_to_review"] and set(verdicts) == set(task["required_checks"]) \
        and all(value is not None for value in verdicts.values())
    if fields != row["ts_strategy_fields_to_review"][:len(fields)]:
        raise ValueError("review trace did not follow the selected field order")
    return {"review_actions": len(actions), "checks": verdicts, "complete": complete}


def _task_verdict(measurements: dict, complete: bool) -> str:
    if not complete:
        return "NEEDS_MORE_EVIDENCE"
    if not all(all(value["checks"].values()) for value in measurements.values()):
        return "REQUIRED_CHECK_FAILED"
    before, after = measurements["parent"]["review_actions"], measurements["candidate"]["review_actions"]
    if after > before:
        return "REGRESSION"
    return "IMPROVED" if after < before else "UNCHANGED"


def _compare(store: Path, identity: str, record: dict, request: dict) -> dict:
    exact_keys(request, {"schema_version", "candidate_id", "parent_id", "scope", "contract_sha256", "provenance", "pairs"})
    contract = record["evaluation_contract"]
    contract_hash = sha256_json(contract)
    if type(request["schema_version"]) is not int or request["schema_version"] != 1 \
            or any(request[key] != value for key, value in {
                "candidate_id": identity, "parent_id": record["parent_id"], "scope": record["scope"],
                "provenance": record["provenance"], "contract_sha256": contract_hash}.items()):
        raise ValueError("evaluation binding differs from predeclared experiment")
    if not isinstance(request["pairs"], list):
        raise ValueError("paired trace sources required")
    parent = _policy(store, record["parent_id"])
    expected = {"parent": _expected_advice(store, parent, record["parent_id"]),
                "candidate": _expected_advice(store, record, identity)}
    tasks = {task["case_id"]: task for task in contract["tasks"]}
    rows, seen, gaps = [], set(), []
    for pair in request["pairs"]:
        exact_keys(pair, {"case_id", "parent", "candidate"})
        if pair["case_id"] not in tasks or pair["case_id"] in seen:
            raise ValueError("wrong or duplicate evaluation case")
        seen.add(pair["case_id"])
        measurements = {}
        for name, strategy, policy_id in (("parent", parent, record["parent_id"]), ("candidate", record, identity)):
            measurements[name] = (None if pair[name] is None else
                                  _trace(pair[name], tasks[pair["case_id"]], strategy, policy_id, contract_hash, expected[name]))
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


def _evaluation(store: Path, identity: str, record: dict) -> tuple[str, dict] | None:
    path = _path(store, "evaluations", identity)
    if not path.exists():
        return None
    saved = _load(path)
    exact_keys(saved, {"schema_version", "source", "comparison"})
    if type(saved["schema_version"]) is not int or saved["schema_version"] != 1:
        raise ValueError("invalid evaluation schema")
    comparison = _compare(store, identity, record, _source(saved["source"]))
    if sha256_json(comparison) != sha256_json(saved["comparison"]) or comparison["evidence_gaps"]:
        raise ValueError("saved evaluation identity/comparison mismatch")
    return sha256_json(saved), comparison


def bind_evaluation(store: Path, source: dict) -> dict:
    request = _source(source)
    identity = request["candidate_id"]
    with _writing(store):
        record = _policy(store, identity)
        if record["kind"] != "candidate":
            raise ValueError("evaluation requires a candidate")
        if _path(store, "decisions", identity).exists():
            raise ValueError("candidate already has a human decision")
        comparison = _compare(store, identity, record, request)
        if comparison["evidence_gaps"]:
            return {"policy_id": identity, "evaluation_id": None, **comparison}
        saved = {"schema_version": 1, "source": source, "comparison": comparison}
        _save(_path(store, "evaluations", identity), saved)
    return policy_status(store, identity)


def _decision(store: Path, identity: str, record: dict) -> dict | None:
    path = _path(store, "decisions", identity)
    if not path.exists():
        return None
    decision = _load(path)
    exact_keys(decision, {"schema_version", "candidate_id", "evaluation_id", "decision", "reviewer", "reason", "actor_kind"})
    if type(decision["schema_version"]) is not int or decision["schema_version"] != 1 \
            or decision["candidate_id"] != identity or decision["decision"] not in {"ACCEPT", "REJECT"}:
        raise ValueError("invalid decision identity")
    _text(decision["reviewer"])
    _text(decision["reason"])
    actor = "synthetic_fixture" if record["provenance"] == "synthetic" else "human"
    if decision["actor_kind"] != actor:
        raise ValueError("decision provenance/actor mismatch")
    evaluation = _evaluation(store, identity, record)
    if decision["evaluation_id"] != (evaluation[0] if evaluation else None):
        raise ValueError("decision is bound to a different evaluation")
    if decision["decision"] == "ACCEPT" and (evaluation is None or evaluation[1]["status"] != "AWAITING_HUMAN_REVIEW"):
        raise ValueError("accept requires complete nonregressing evidence supporting improvement")
    return decision


def _accepted(store: Path, identity: str, record: dict) -> None:
    decision = _decision(store, identity, record)
    if decision is None or decision["decision"] != "ACCEPT":
        raise ValueError("workflow candidate is not human-accepted")


def record_decision(store: Path, request: dict) -> dict:
    exact_keys(request, {"candidate_id", "evaluation_id", "decision", "reviewer", "reason", "actor_kind"})
    identity = request["candidate_id"]
    with _writing(store):
        record = _policy(store, identity)
        if record["kind"] != "candidate":
            raise ValueError("decision requires a candidate")
        payload = {"schema_version": 1, **request}
        # Validate before publishing, using the same read-side validator below.
        evaluation = _evaluation(store, identity, record)
        if request["evaluation_id"] != (evaluation[0] if evaluation else None):
            raise ValueError("wrong evaluation identity")
        _text(request["reviewer"])
        _text(request["reason"])
        if request["actor_kind"] != ("synthetic_fixture" if record["provenance"] == "synthetic" else "human"):
            raise ValueError("decision provenance/actor mismatch")
        if request["decision"] == "ACCEPT":
            if evaluation is None or evaluation[1]["status"] != "AWAITING_HUMAN_REVIEW":
                raise ValueError("no eligible evaluation for acceptance")
            _current_parent(store, record["parent_id"], excluding=identity)
        elif request["decision"] != "REJECT":
            raise ValueError("human decision must be ACCEPT or REJECT")
        _save(_path(store, "decisions", identity), payload)
    return policy_status(store, identity)


def policy_status(store: Path, identity: str) -> dict:
    record = _policy(store, identity)
    evaluation = _evaluation(store, identity, record) if record["kind"] == "candidate" else None
    decision = _decision(store, identity, record) if record["kind"] == "candidate" else None
    status = "BASELINE" if record["kind"] == "baseline" else "WAITING_FOR_EVALUATION"
    if evaluation:
        status = evaluation[1]["status"]
    if decision:
        status = "ACCEPTED" if decision["decision"] == "ACCEPT" else "REJECTED"
    return {"policy_id": identity, "policy_path": str(_path(store, "policies", identity).resolve()),
            "scope": record["scope"], "provenance": record["provenance"], "status": status,
            "evaluation_id": evaluation[0] if evaluation else None, "comparison": evaluation[1] if evaluation else None,
            "decision": decision, "decision_id": sha256_json(decision) if decision else None, "orders": record["orders"],
            "contract_sha256": sha256_json(record["evaluation_contract"]) if record["kind"] == "candidate" else None}


def select_policy(store: Path | None, identity: str | None, scope: str | None, public: dict,
                  answers_path: Path, offline: bool) -> tuple[dict, dict]:
    if store is None or identity is None or scope is None:
        raise ValueError("workflow selection requires explicit store, policy and scope")
    record = _policy(store, identity)
    if record["scope"] != scope or sha256_json(_source(record["inputs"]["public"])) != sha256_json(public) \
            or record["inputs"]["answers"]["sha256"] != sha256_file(answers_path):
        raise ValueError("workflow selection scope/task/input identity mismatch")
    if record["provenance"] == "synthetic" and not offline:
        raise ValueError("synthetic policy is usable only in explicit offline evaluation")
    decision = _decision(store, identity, record) if record["kind"] == "candidate" else None
    if decision and decision["decision"] == "REJECT":
        raise ValueError("rejected policy cannot be selected")
    if record["kind"] == "candidate" and not offline:
        _accepted(store, identity, record)
    selection = {"policy_id": identity, "scope": scope,
                 "mode": "offline_evaluation" if offline else ("accepted_review" if decision else "baseline_review"),
                 "provenance": record["provenance"]}
    if not offline and decision:
        selection.update({"decision_id": sha256_json(decision), "evaluation_id": decision["evaluation_id"]})
    return record["orders"], selection
