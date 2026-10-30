"""Project-owned, atomic file store for policies, independent reviews and feedback."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil

from jsonschema import Draft202012Validator

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_atomic, write_json_exclusive
from scripts.ts_strategy_engine.review_evidence import _no_links

from .catalog import blocked
from .rsi_contract import DEFINITION


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def checked_reference(reference):
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        raise ValueError("RSI source requires an exact path/hash reference")
    path = Path(reference["path"]).absolute()
    _no_links(path)
    if blocked(path) or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("RSI source is excluded, missing or oversized")
    if sha256_file(path) != reference["sha256"]:
        raise ValueError("RSI source hash differs")
    return path


def _review_binding(record):
    if record["status"] == "candidate" and not record["reviews"]:
        return
    if not record["reviews"]:
        raise ValueError("policy status lacks an independent review")
    last = record["reviews"][-1]
    keys = ("policy_id", "version", "content_sha256", "status", "reviewer", "validation_scope", "validation_refs", "reason")
    original = load_json_object(checked_reference(last["request_ref"]))
    if original != {key: last[key] for key in keys} or last["status"] != record["status"] \
            or last["content_sha256"] != record["content_sha256"] \
            or (last["policy_id"], last["version"]) != (record["definition"]["policy_id"], record["definition"]["version"]):
        raise ValueError("policy status/review binding differs")
    if last["status"] in {"accepted", "trial"} and (not last["frozen_validation_refs"] or not last["validation_scope"].strip()):
        raise ValueError("policy review lacks bound validation scope")
    if [ref["sha256"] for ref in last["validation_refs"]] != [ref["sha256"] for ref in last["frozen_validation_refs"]]:
        raise ValueError("policy validation source binding differs")
    for reference in last["frozen_validation_refs"]:
        checked_reference(reference)


class PolicyStore:
    def __init__(self, root, project):
        self.root, self.project = Path(root).absolute(), str(Path(project).resolve())
        _no_links(self.root, missing_ok=True)
        if blocked(self.root) or self.root == Path(self.root.anchor):
            raise ValueError("invalid project RSI store")

    def read(self):
        path = self.root / "state.json"
        if not path.exists():
            return {"schema_version": 1, "project": self.project, "policies": [], "candidates": [], "feedback": [], "observations": []}
        _no_links(path)
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("RSI store exceeds bounded file storage; archive review required")
        value = load_json_object(path)
        if value.get("schema_version") != 1 or value.get("project") != self.project:
            raise ValueError("RSI store belongs to a different project or schema")
        seen = set()
        for record in value["policies"]:
            definition = record["definition"]
            Draft202012Validator(DEFINITION).validate(definition)
            key = (definition["policy_id"], definition["version"])
            if key in seen or record["content_sha256"] != sha256_json(definition):
                raise ValueError("duplicate or changed policy version")
            seen.add(key)
            if record["status"] not in {"candidate", "trial", "accepted", "disabled"}:
                raise ValueError("invalid policy status")
            _review_binding(record)
        return value

    @contextmanager
    def transaction(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / "write.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError("RSI store locked; inspect prior write before retry") from exc
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(utc_now())
            value = self.read()
            yield value
            write_json_atomic(self.root / "state.json", value)
        finally:
            lock.unlink(missing_ok=True)

    def freeze_source(self, reference):
        source = checked_reference(reference)
        folder = self.root / "sources" / reference["sha256"]
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / source.name
        _no_links(target, missing_ok=True)
        if not target.exists():
            with source.open("rb") as original, target.open("xb") as frozen:
                shutil.copyfileobj(original, frozen)
        if sha256_file(target) != reference["sha256"] or sha256_file(source) != reference["sha256"]:
            raise ValueError("RSI source changed during freeze")
        return {"path": str(target), "sha256": reference["sha256"]}

    def propose(self, definition, candidate_id=None):
        Draft202012Validator(DEFINITION).validate(definition)
        if str(Path(definition["scope"]["project"]).resolve()) != self.project:
            raise ValueError("policy scope does not match project")
        with self.transaction() as state:
            candidate = next((row for row in state["candidates"] if row["candidate_id"] == candidate_id), None) if candidate_id else None
            if candidate_id:
                if candidate is None or candidate.get("policy_refs"):
                    raise ValueError("candidate is missing or already bound to a policy proposal")
                if definition["behavior_change"] != candidate["proposal"]["behavior_change"] \
                        or not {ref["sha256"] for ref in definition["source_refs"]} & {row["raw_ref"]["sha256"] for row in candidate["occurrences"]}:
                    raise ValueError("policy proposal must preserve candidate behavior and a raw proposal source")
            key = (definition["policy_id"], definition["version"])
            if any((r["definition"]["policy_id"], r["definition"]["version"]) == key for r in state["policies"]):
                raise ValueError("policy version already exists; inspect before retry")
            frozen = [self.freeze_source(ref) for ref in definition["source_refs"]]
            record = {"definition": definition, "content_sha256": sha256_json(definition), "status": "candidate",
                      "frozen_sources": frozen, "reviews": [], "registered_at": utc_now(), "origin_candidate_id": candidate_id}
            state["policies"].append(record)
            if candidate is not None:
                candidate["policy_refs"] = [{"policy_id": definition["policy_id"], "version": definition["version"], "content_sha256": record["content_sha256"]}]
        return record

    def review(self, request, request_ref):
        required = {"policy_id", "version", "content_sha256", "status", "reviewer", "validation_scope", "validation_refs", "reason"}
        if set(request) != required or request["status"] not in {"trial", "accepted", "disabled"} \
                or any(not isinstance(request[k], str) or not request[k].strip() for k in ("reviewer", "validation_scope", "reason")):
            raise ValueError("independent policy review requires reviewer, validation scope and reason")
        if request["status"] in {"trial", "accepted"} and not request["validation_refs"]:
            raise ValueError("trial/acceptance requires bound validation evidence")
        with self.transaction() as state:
            rows = [r for r in state["policies"] if r["definition"]["policy_id"] == request["policy_id"]
                    and r["definition"]["version"] == request["version"] and r["content_sha256"] == request["content_sha256"]]
            if len(rows) != 1:
                raise ValueError("review does not bind an existing exact policy version")
            evidence = [self.freeze_source(ref) for ref in request["validation_refs"]]
            review = {**request, "recorded_at": utc_now(), "request_ref": self.freeze_source(request_ref), "frozen_validation_refs": evidence}
            rows[0]["reviews"].append(review)
            rows[0]["status"] = request["status"]
            for candidate in state["candidates"]:
                if candidate["candidate_id"] == rows[0].get("origin_candidate_id"):
                    candidate["status"] = request["status"]
        return review

    def index_feedback(self, reference, receipt):
        with self.transaction() as state:
            identity = "feedback:" + reference["sha256"]
            if not any(row["source_id"] == identity for row in state["feedback"]):
                state["feedback"].append({"source_id": identity, "reference": self.freeze_source(reference),
                    "goal": receipt["goal"], "intent": receipt["intent"], "recorded_at": utc_now(), "candidate_ids": []})
        return identity


def write_record(folder, name, payload):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    write_json_exclusive(path, payload)
    return {"path": str(path), "sha256": sha256_file(path)}
