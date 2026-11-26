"""Deterministic scoring of saved diagnostic answers against a frozen case bundle."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive

from .learning_cases import ROOT_STATUSES, SCHEMA_VERSION
from .learning_evidence import exact_keys, observe
from .strategy_learning import POLICY, policy


ANSWER_KEYS = {"case_id", "input_sha256", "failure_class", "root_cause_status",
               "next_review", "evidence_ids"}


def _load_bundle(bundle: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    marker = load_json_object(bundle / "manifest.json")
    public = load_json_object(bundle / "public.json")
    private = load_json_object(bundle / "private.json")
    exact_keys(marker, {"schema_version", "public_sha256", "private_sha256"})
    if marker["schema_version"] != SCHEMA_VERSION or marker["public_sha256"] != sha256_json(public) \
            or marker["private_sha256"] != sha256_json(private):
        raise ValueError("case bundle has an invalid completion marker or changed bytes")
    if public.get("schema_version") != SCHEMA_VERSION or private.get("schema_version") != SCHEMA_VERSION \
            or private.get("public_sha256") != marker["public_sha256"]:
        raise ValueError("case bundle versions or identities disagree")
    if private.get("policy_sha256") != sha256_file(POLICY):
        raise ValueError("learning policy changed since case construction")
    if len(public.get("cases", [])) != len(private.get("cases", [])):
        raise ValueError("public/private case counts disagree")
    for public_case, private_case in zip(public["cases"], private["cases"]):
        if public_case["case_id"] != private_case["case_id"] \
                or public_case["group_id"] != private_case["group_id"]:
            raise ValueError("public/private case mapping changed")
        identity = {key: value for key, value in public_case.items() if key != "input_sha256"}
        if public_case["input_sha256"] != sha256_json(identity):
            raise ValueError("public case identity changed")
        visible = public_case["evidence"]
        sources = private_case["sources"]
        if len(visible) != len(sources) or any(
            item["evidence_id"] != source["evidence_id"] or item["pointer"] != source["pointer"]
            or item["value"] != source["value"] or item["source_sha256"] != source["sha256"]
            for item, source in zip(visible, sources)
        ):
            raise ValueError("public evidence and private source mapping disagree")
        for source in sources:
            observe([{key: source[key] for key in ("path", "sha256", "pointer", "value")}])
        reference = private_case["reference"]
        if reference is not None:
            observe([{key: reference["source"][key] for key in ("path", "sha256", "pointer", "value")}])
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
    exact_keys(answers, {"schema_version", "public_sha256", "answers"})
    if answers["schema_version"] != SCHEMA_VERSION or answers["public_sha256"] != marker["public_sha256"] \
            or not isinstance(answers["answers"], list):
        raise ValueError("answer set does not match the public case version")
    by_id: dict[str, list[Any]] = {}
    malformed = 0
    for answer in answers["answers"]:
        if not isinstance(answer, dict) or not isinstance(answer.get("case_id"), str):
            malformed += 1
            continue
        by_id.setdefault(answer["case_id"], []).append(answer)
    expected_ids = {case["case_id"] for case in public["cases"]}
    extra_ids = sorted(set(by_id) - expected_ids)
    rows = []
    matched = 0
    scorable = 0
    for public_case, private_case in zip(public["cases"], private["cases"]):
        case_id = public_case["case_id"]
        reference = private_case["reference"]
        candidates = by_id.get(case_id, [])
        if reference is None:
            status = "reference_unavailable"
        else:
            scorable += 1
            if not candidates:
                status = "missing_answer"
            elif len(candidates) != 1:
                status = "duplicate_answer"
            elif error := _answer_error(candidates[0], public_case):
                status = error
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
                     "provenance": private_case["provenance"], "status": status})
    counts = {"total": len(rows), "scorable": scorable, "matched": matched,
              "groups": len({row["group_id"] for row in rows}),
              "reference_unavailable": len(rows) - scorable,
              "missing_or_invalid": sum(row["status"] not in {"match", "diagnosis_mismatch",
                                                               "reference_unavailable"} for row in rows),
              "unknown_case_ids": extra_ids, "malformed_answers": malformed}
    report = {"schema_version": SCHEMA_VERSION, "public_sha256": marker["public_sha256"],
              "answers_sha256": sha256_file(answers_path), "counts": counts, "cases": rows,
              "integrity_ok": not extra_ids and not malformed and
                              all(len(by_id.get(case_id, [])) <= 1 for case_id in expected_ids),
              "real_task_improvement_established": False}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(report_path, report)
    return report
