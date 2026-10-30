"""Bounded, per-source isolation for the derived dashboard; no scientific parser."""
from copy import deepcopy
from itertools import islice
import json
import math
from pathlib import Path

from jsonschema import ValidationError

from scripts.artifact_io import load_json_object, sha256_file, sha256_json
from scripts.ts_strategy_engine.review_evidence import _no_links
from scripts.scientific_validation import validate_finite_tree

from .catalog import blocked
from .policies import checked_reference
from .policy_selection import model_context
from .rsi_application import _action_map, pointer
from .usage_sources import feedback_source, comparison_source


MAX_BYTES = 8 * 1024 * 1024
MAX_SOURCES = 200


def reference(path):
    return {"path": str(path.absolute()), "sha256": sha256_file(path)}


def read_json(path, expected=None):
    path = Path(path).absolute()
    _no_links(path)
    if blocked(path) or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("source excluded, missing or larger than 8 MiB")
    if expected:
        checked_reference(expected)
    result = load_json_object(path)
    validate_finite_tree(result, "dashboard source")
    if expected and sha256_file(path) != expected["sha256"]:
        raise ValueError("source changed while reading")
    return result


def bound(reference_value):
    return read_json(Path(reference_value["path"]), reference_value)


class Sources:
    def __init__(self):
        self.errors = []

    def attempt(self, role, source, operation):
        try:
            return operation()
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, ValidationError) as exc:
            self.errors.append({"role": role, "source": deepcopy(source), "error": f"{type(exc).__name__}: {exc}"})
            return None


def bounded_paths(iterator):
    paths = list(islice(iterator, MAX_SOURCES + 1))
    if len(paths) > MAX_SOURCES:
        raise ValueError("source count exceeds dashboard bound of 200")
    return sorted(paths)


def files(folder, pattern):
    _no_links(folder.absolute(), missing_ok=True)
    return bounded_paths(folder.glob(pattern))


def read_additions(run, sources):
    feedback, comparisons, index_errors = [], [], []
    for path in files(run / "feedback", "*.json"):
        def load_feedback():
            read_json(path)
            value = feedback_source(run, path)
            return {"reference": reference(path), **value}
        value = sources.attempt("feedback", str(path), load_feedback)
        if value:
            feedback.append(value)
    for path in files(run / "feedback", "index-error-*.txt"):
        value = sources.attempt("feedback_index", str(path), lambda: read_json(path))
        if value:
            index_errors.append({"reference": reference(path), **value})
    for path in files(run / "comparisons", "*.json"):
        value = sources.attempt("comparison_binding", str(path), lambda: comparison_source(run, path))
        if value and value not in comparisons:
            comparisons.append(value)
    return sorted(feedback, key=lambda r: r.get("recorded_at", "")), comparisons, index_errors


def costs(receipt):
    names = ("model_turns_started", "host_tool_requests", "host_tool_executions", "repeated_requests_reused",
             "host_actions_reused_from_parent", "elapsed_seconds")
    result = {key: receipt.get(key) if type(receipt.get(key)) in {int, float} and math.isfinite(receipt[key]) and receipt[key] >= 0 else None for key in names}
    raw = receipt.get("tokens")
    total = raw.get("total", {}).get("totalTokens") if isinstance(raw, dict) and isinstance(raw.get("total"), dict) else None
    result.update({"tokens_total": total if type(total) is int and total >= 0 else None, "tokens_raw": raw,
                   "token_basis": "receipt.tokens.total.totalTokens; no notification accumulation or fee conversion"})
    return result


def actions_from(result, sources):
    rows = []
    for action in result.get("evidence_actions", []):
        def validate_action():
            bound({"path": action["result_path"], "sha256": action["result_sha256"]})
            return _action_map([action])
        data = sources.attempt("host_action", action.get("result_path"), validate_action)
        if not data:
            continue
        _, value = data[action["evidence_id"]]
        rows.append({"evidence_id": action["evidence_id"], "request": action["request"], "status": value.get("status"),
            "executed": action.get("executed"), "reused_from": action.get("reused_from"), "reused_from_parent": action.get("reused_from_parent"),
            "reference": {"path": action["result_path"], "sha256": action["result_sha256"]}, "sources": value.get("sources", []),
            "error": value.get("error")})
    return rows


def selected_from(app, sources):
    frozen = {r["definition"]["policy_id"]: r for r in app.get("selection", {}).get("selected_policies", [])}
    selected = []
    for row in app.get("selected_policies", []):
        def validate():
            original = frozen[row["policy_id"]]
            definition = original["definition"]
            if row["content_sha256"] != sha256_json(definition) or row["version"] != definition["version"]:
                raise ValueError("frozen policy identity/hash differs")
            for ref in row.get("model_inputs", []):
                value = bound({k: ref[k] for k in ("path", "sha256")})
                if value.get("rsi_context") != model_context(app["selection"]):
                    raise ValueError("submitted model input does not match frozen selection")
            if row.get("provided") is True and not row.get("model_inputs"):
                raise ValueError("provided policy lacks submitted input references")
            return {**row, "status_at_run": original["status"], "definition": definition, "source_verified": True}
        value = sources.attempt("selected_policy", row.get("policy_id"), validate)
        selected.append(value if value else {**row, "provided": None, "source_verified": False, "status_at_run": "unknown"})
    return selected


def applications_from(app, selected, actions, answer, sources):
    valid_policies = {p["policy_id"] for p in selected if p["source_verified"]}
    actual = {a["evidence_id"]: a for a in actions}
    rows = []
    for row in app.get("applications", []):
        def validate():
            if row["policy_id"] not in valid_policies:
                raise ValueError("application policy not verified in this run")
            if not set(row.get("action_refs", [])) <= actual.keys():
                raise ValueError("application refers to missing or invalid actions")
            outputs = [{"pointer": ref, "content": pointer(answer, ref)} for ref in row.get("output_refs", [])]
            return {**row, "action_details": [actual[ref] for ref in row.get("action_refs", [])], "outputs": outputs, "source_verified": True}
        value = sources.attempt("application", row.get("policy_id"), validate)
        rows.append(value if value else {**row, "source_verified": False, "host_status": "unverified_source", "outputs": [], "action_details": []})
    return rows


def answer_text(answer):
    return json.dumps({"recommended_next": answer.get("recommended_next"), "options": answer.get("options")}, ensure_ascii=False, indent=2)
