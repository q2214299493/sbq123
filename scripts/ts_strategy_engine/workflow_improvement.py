"""Bounded review-order experiments. Local immutable artifacts, no execution authority."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path

from scripts.artifact_io import require_sha256, sha256_file, sha256_json, write_json_exclusive

from .learning_evidence import exact_keys
from .next_review_core import build_next_reviews, review_field_orders
from .workflow_evaluation import METHOD as METHOD, RULES as RULES, _text, _load, _source, _observations, _contract, compare_evaluation
from .strategy_learning import POLICY


def _engine() -> dict:
    return {"policy_sha256": sha256_file(POLICY), "advice_sha256": sha256_file(Path(__file__).with_name("next_review.py")),
            "advice_core_sha256": sha256_file(Path(__file__).with_name("next_review_core.py")),
            "evaluation_sha256": sha256_file(Path(__file__).with_name("workflow_evaluation.py")),
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


def _advice(inputs: dict, *, orders: dict | None = None, strategy_identity: dict | None = None) -> dict:
    exact_keys(inputs, {"public", "answers"})
    public = _source(inputs["public"])
    answers = _source(inputs["answers"])
    return build_next_reviews(public, answers, sha256_json(public), inputs["answers"]["sha256"],
                              sha256_file(POLICY), orders=orders, strategy_identity=strategy_identity)


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


def _expected_advice(record: dict, identity: str) -> dict:
    selection = {"policy_id": identity, "scope": record["scope"],
                 "mode": "offline_evaluation", "provenance": record["provenance"]}
    return _advice(record["inputs"], orders=record["orders"], strategy_identity=selection)


def _compare(store: Path, identity: str, record: dict, request: dict) -> dict:
    parent = _policy(store, record["parent_id"])
    expected = {"parent": _expected_advice(parent, record["parent_id"]), "candidate": _expected_advice(record, identity)}
    return compare_evaluation(identity, record, request, expected)


def _evaluation(store: Path, identity: str, record: dict) -> tuple[str, dict] | None:
    path = _path(store, "evaluations", identity)
    if not path.exists():
        return None
    saved = _load(path)
    exact_keys(saved, {"schema_version", "source", "comparison"})
    if type(saved["schema_version"]) is not int or saved["schema_version"] != 2:
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
        saved = {"schema_version": 2, "source": source, "comparison": comparison}
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
