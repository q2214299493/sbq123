"""Explicit, source-revalidated continuation; old judgments never become new facts."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.ts_strategy_engine.review_evidence import _no_links

from .catalog import blocked
from .cache_state import dependency_proof, dependencies_match, rebind_result


def previous_header(folder):
    _no_links(folder.absolute())
    if blocked(folder.absolute()):
        raise ValueError("excluded previous-run path")
    return load_json_object(folder / "run_receipt.json"), load_json_object(folder / "catalog.initial.json")


def _snapshot(path, root, output):
    _no_links(path.absolute())
    if not path.resolve().is_relative_to(root.resolve()) or blocked(path) or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("invalid/oversized previous artifact")
    digest = sha256_file(path)
    target = output / "parent" / digest / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(path, target)
    if sha256_file(target) != digest or sha256_file(path) != digest:
        raise ValueError("parent artifact changed during collection")
    return {"path": str(path), "sha256": digest, "snapshot": str(target)}


def _sources(result, parent, bound, output):
    refs = []
    for source in result.get("sources", []):
        if source.get("kind") == "derived_corpus_receipt":
            path = Path(source["path"])
            if not path.resolve().is_relative_to((parent / "tools").resolve()) or sha256_file(path) != source["sha256"]:
                raise ValueError("parent search corpus differs")
            bound.append(_snapshot(path, parent, output))
            refs.extend(load_json_object(path)["sources"])
        else:
            refs.append(source)
    return refs


def _freshness(reference, catalog, memo):
    key = (reference["path"], reference["sha256"])
    if key not in memo:
        path = Path(reference["path"])
        try:
            if not path.exists():
                state = "missing_in_current_location"
            else:
                catalog.check(path)
                state = "unchanged" if sha256_file(path) == reference["sha256"] else "changed"
        except (OSError, ValueError):
            state = "out_of_scope_or_unreadable"
        memo[key] = {"path": str(path), "previous_sha256": reference["sha256"], "current_state": state}
    return memo[key]


def _snapshots_intact(refs, parent):
    try:
        for reference in refs:
            snapshot = Path(reference["snapshot"])
            _no_links(snapshot.absolute())
            if not snapshot.resolve().is_relative_to((parent / "sources").resolve()) or sha256_file(snapshot) != reference["sha256"]:
                return False
    except (OSError, ValueError):
        return False
    return True


def _prepare_cache(action, parent, registry, bound, output, memo, scopes_match):
    path = Path(action["result_path"])
    if not path.resolve().is_relative_to((parent / "tools").resolve()) or sha256_file(path) != action["result_sha256"]:
        raise ValueError("previous host action differs from its binding")
    bound.append(_snapshot(path, parent, output))
    old = load_json_object(path)["result"]
    issue = None
    try:
        refs = _sources(old, parent, bound, output)
        states = [_freshness(reference, registry.catalog, memo) for reference in refs]
    except (OSError, ValueError, KeyError) as exc:
        refs, states, issue = [], [], str(exc)
    implementation_matches = action.get("implementation_sha256") == registry.implementation_sha256
    proof = dependency_proof(registry, action["request"], refresh=True)
    dependency_matches = dependencies_match(old, proof)
    eligible = bool(refs) and scopes_match and implementation_matches and dependency_matches \
        and _snapshots_intact(refs, parent) and old["status"] in {"OK", "PARTIAL"} \
        and all(row["current_state"] == "unchanged" for row in states)
    if eligible:
        try:
            current = rebind_result(old, refs, registry, parent)
            origin = {"run": str(parent), "evidence_id": old["evidence_id"], "result_sha256": action["result_sha256"]}
            current.update({"reused_from_parent": origin, "cache_lineage": [*old.get("cache_lineage", []), origin]})
            registry.cache[registry.fingerprint(action["request"])] = current
        except (OSError, ValueError, KeyError) as exc:
            eligible, issue = False, str(exc)
    return {"previous_evidence_id": action["evidence_id"], "tool": action["request"]["tool"],
            "implementation_compatible": implementation_matches, "dependencies_compatible": dependency_matches,
            "sources": states, "source_binding_issue": issue, "reuse_eligible": eligible, "needs_revalidation": not eligible}


def load_continuation(parent, registry, output, update):
    parent = parent.absolute()
    receipt, inventory = previous_header(parent)
    if registry.catalog.mode != "daily" or receipt["mode"] != "daily":
        raise ValueError("continuation is daily use, not a frozen blind evaluation")
    result = load_json_object(parent / "research_result.json")
    bound = []
    for name in ("run_receipt.json", "catalog.initial.json", "research_result.json"):
        bound.append(_snapshot(parent / name, parent, output))
    feedback = []
    for path in sorted((parent / "feedback").glob("*.json"))[:20]:
        bound.append(_snapshot(path, parent, output))
        value = load_json_object(path)
        if value["run_receipt_sha256"] != sha256_file(parent / "run_receipt.json"):
            raise ValueError("feedback belongs to a different run receipt")
        feedback.append(value)
    rows, memo = [], {}
    scopes_match = inventory["scopes"] == [str(p) for p in registry.catalog.scopes[:len(inventory["scopes"])]]
    for action in result["evidence_actions"]:
        rows.append(_prepare_cache(action, parent, registry, bound, output, memo, scopes_match))
    answer = result["answer"]
    claims = [{"ref": f"F{i + 1:03d}", **row} for i, row in enumerate(answer["facts"])]
    claims += [{"ref": "option:" + row["id"], "statement": row["proposal"], "evidence_ids": row["evidence_ids"]} for row in answer["options"]]
    context = {"question_id": receipt.get("question_id", sha256_json({"goal": receipt["goal"], "origin": str(parent)})),
               "parent_run": str(parent), "original_goal": receipt["goal"], "update": update,
               "previous_claims": claims, "previous_options": answer["options"],
               "previous_uncompleted_checks": {"recommended_next": answer["recommended_next"],
                    "uncertainties": answer["uncertainties"], "plan": answer["evidence_and_calculation_plan"]},
               "feedback": feedback, "source_revalidation": rows, "unique_source_hash_checks": len(memo),
               "checked_at": datetime.now(timezone.utc).isoformat(),
               "authority": "previous model synthesis, not new evidence; current E citations require host results, including explicitly revalidated cache returns"}
    document = {"schema_version": 1, "context": context, "bound_parent_artifacts": list(bound)}
    write_json_exclusive(output / "continuation.json", document)
    return context


def validate_progress(answer, context):
    progress = answer.get("progress")
    if context is None:
        if progress is not None:
            raise ValueError("progress cannot invent a previous research round")
        return
    if progress is None:
        raise ValueError("continuation must explain changed judgments, completed checks and next product")
    allowed = {row["ref"] for row in context["previous_claims"]}
    if any(row["previous_ref"] not in allowed for row in progress["changes"]):
        raise ValueError("progress refers to an unrecorded previous judgment")
    required = [*progress["completed_checks"], *[row for row in progress["changes"] if row["assessment"] != "pending_revalidation"]]
    if any(not row["evidence_ids"] for row in required):
        raise ValueError("completed/revalidated checks require current host evidence")
