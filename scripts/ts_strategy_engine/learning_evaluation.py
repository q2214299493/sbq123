"""Deterministic scoring of saved diagnostic answers against a frozen case bundle."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import artifact_io
from scripts.artifact_io import load_json_object, require_sha256, sha256_file, sha256_json, write_json_exclusive

from . import learning_cases, learning_evidence, strategy_learning
from .learning_cases import PRIVATE_FORMAT_VERSION, ROOT_STATUSES, SCHEMA_VERSION, validate_built_case
from .learning_evidence import exact_keys
from .strategy_learning import POLICY, policy


ANSWER_KEYS = {"case_id", "input_sha256", "failure_class", "root_cause_status",
               "next_review", "evidence_ids"}


def _load_bundle(bundle: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    marker = load_json_object(bundle / "manifest.json")
    public = load_json_object(bundle / "public.json")
    private = load_json_object(bundle / "private.json")
    exact_keys(marker, {"schema_version", "public_sha256", "private_sha256"})
    exact_keys(public, {"schema_version", "cases"})
    if type(private.get("bundle_format_version")) is not int \
            or private["bundle_format_version"] != PRIVATE_FORMAT_VERSION:
        raise ValueError("legacy case bundle lacks source-scope validation; rebuild it")
    exact_keys(private, {"schema_version", "bundle_format_version", "allowed_root", "public_sha256",
                         "policy_sha256", "builder_sha256", "cases"})
    if any(type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION
           for value in (marker, public, private)) \
            or marker["public_sha256"] != sha256_json(public) \
            or marker["private_sha256"] != sha256_json(private):
        raise ValueError("case bundle has an invalid completion marker or changed bytes")
    if private.get("public_sha256") != marker["public_sha256"]:
        raise ValueError("case bundle versions or identities disagree")
    if private.get("policy_sha256") != sha256_file(POLICY):
        raise ValueError("learning policy changed since case construction")
    if not isinstance(public["cases"], list) or not isinstance(private["cases"], list) \
            or len(public["cases"]) != len(private["cases"]):
        raise ValueError("public/private case counts disagree")
    if not isinstance(private["allowed_root"], str):
        raise ValueError("bundle allowed_root must be a canonical directory")
    root = Path(private["allowed_root"])
    if not root.is_absolute() or not root.is_dir() or root.resolve() != root:
        raise ValueError("bundle allowed_root must be a canonical directory")
    require_sha256(private["builder_sha256"], label="builder sha256")
    seen: set[str] = set()
    for public_case, private_case in zip(public["cases"], private["cases"]):
        validate_built_case(public_case, private_case, root)
        case_id = public_case["case_id"]
        if case_id in seen:
            raise ValueError(f"duplicate case_id in case bundle: {case_id}")
        seen.add(case_id)
    return marker, public, private


def _answer_error(answer: Any, public_case: dict[str, Any]) -> str | None:
    try:
        exact_keys(answer, ANSWER_KEYS)
        if answer["case_id"] != public_case["case_id"] or answer["input_sha256"] != public_case["input_sha256"]:
            return "input_identity_mismatch"
        if answer["failure_class"] not in policy()["failure_routes"] \
                or answer["root_cause_status"] not in ROOT_STATUSES \
                or answer["next_review"] != policy()["failure_routes"][answer["failure_class"]]:
            return "invalid_diagnosis_fields"
        ids = answer["evidence_ids"]
        allowed = {item["evidence_id"] for item in public_case["evidence"]}
        if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids) \
                or len(ids) != len(set(ids)) or not set(ids) <= allowed:
            return "invalid_evidence_ids"
    except (ValueError, KeyError, TypeError):
        return "invalid_answer_shape"
    return None


def evaluate_cases(bundle: Path, answers_path: Path, report_path: Path) -> dict[str, Any]:
    """Score all scorable cases; missing and invalid answers remain in the denominator."""
    marker, public, private = _load_bundle(bundle)
    answers = load_json_object(answers_path)
    try:
        exact_keys(answers, {"schema_version", "public_sha256", "answers"})
        if type(answers["schema_version"]) is not int or answers["schema_version"] != SCHEMA_VERSION \
                or answers["public_sha256"] != marker["public_sha256"] \
                or not isinstance(answers["answers"], list):
            raise ValueError("answer set does not match the public case version")
    except ValueError:
        answer_set_error = "invalid_answer_set_version_or_shape"
    else:
        answer_set_error = None
    by_id: dict[str, list[Any]] = {}
    malformed = 0
    for answer in (answers["answers"] if answer_set_error is None else []):
        if not isinstance(answer, dict) or not isinstance(answer.get("case_id"), str):
            malformed += 1
            continue
        by_id.setdefault(answer["case_id"], []).append(answer)
    expected_ids = {case["case_id"] for case in public["cases"]}
    extra_ids = sorted(set(by_id) - expected_ids)
    rows = []
    matched = 0
    scorable = 0
    valid_statuses = {"match", "diagnosis_mismatch", "reference_unavailable"}
    for public_case, private_case in zip(public["cases"], private["cases"]):
        case_id = public_case["case_id"]
        reference = private_case["reference"]
        candidates = by_id.get(case_id, [])
        if reference is not None:
            scorable += 1
        if answer_set_error is not None:
            status = answer_set_error
        elif not candidates:
            status = "missing_answer"
        elif len(candidates) != 1:
            status = "duplicate_answer"
        elif error := _answer_error(candidates[0], public_case):
            status = error
        elif reference is None:
            status = "reference_unavailable"
        else:
            answer = candidates[0]
            expected = reference["expected"]
            fields = ("failure_class", "root_cause_status", "next_review", "evidence_ids")
            status = "match" if all(
                set(answer[key]) == set(expected[key]) if key == "evidence_ids"
                else answer[key] == expected[key] for key in fields
            ) else "diagnosis_mismatch"
            matched += status == "match"
        rows.append({"case_id": case_id, "group_id": public_case["group_id"],
                     "provenance": private_case["provenance"],
                     "reference_status": "available" if reference is not None else "unavailable",
                     "status": status})
    integrity_ok = answer_set_error is None and not extra_ids and not malformed and all(
        row["status"] in valid_statuses for row in rows
    )
    counts = {"total": len(rows), "scorable": scorable, "matched": matched,
              "groups": len({row["group_id"] for row in rows}),
              "reference_unavailable": len(rows) - scorable,
              "missing_or_invalid": sum(row["status"] not in valid_statuses for row in rows),
              "unknown_case_ids": extra_ids, "malformed_answers": malformed}
    code_hashes = {
        "learning_evaluation": sha256_file(Path(__file__)),
        "learning_cases": sha256_file(Path(learning_cases.__file__)),
        "learning_evidence": sha256_file(Path(learning_evidence.__file__)),
        "strategy_learning": sha256_file(Path(strategy_learning.__file__)),
        "artifact_io": sha256_file(Path(artifact_io.__file__)),
    }
    report = {"schema_version": SCHEMA_VERSION, "public_sha256": marker["public_sha256"],
              "private_sha256": marker["private_sha256"],
              "policy_sha256": private["policy_sha256"],
              "builder_sha256": private["builder_sha256"],
              "evaluator_sha256": code_hashes["learning_evaluation"],
              "evaluation_code_sha256": sha256_json(code_hashes),
              "answers_sha256": sha256_file(answers_path), "counts": counts, "cases": rows,
              "answer_set_error": answer_set_error,
              "integrity_ok": integrity_ok,
              "comparison_ready": integrity_ok and scorable == len(rows) and bool(rows),
              "real_task_improvement_established": False}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(report_path, report)
    return report
