"""Read-only next-review advice from saved schema-2 diagnostic answers.

Advice does not approve a cause, revise a strategy, or authorize execution.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, require_sha256, sha256_file, sha256_json, write_json_exclusive

from .learning_cases import DIAGNOSIS_KEYS, SCHEMA_VERSION, diagnosis_error
from .learning_evidence import exact_keys
from .strategy_learning import POLICY, policy


_REVIEW_FOCUS = {
    "unknown": "collect_cause_specific_evidence",
    "hypothesis": "test_specific_causal_claim",
    "confirmed": "review_scope_of_claim_and_evidence",
}
_TS_FIELD_HINTS = {
    "geometry": ("interpolation_strategy", "initial_images"),
    "optimizer": ("candidate_method",),
}


def recommend_next_reviews(public_path: Path, answers_path: Path, report_path: Path,
                           expected_public_sha256: str) -> dict[str, Any]:
    """Validate frozen public identities and answers; write advisory-only output once."""
    public, answers = load_json_object(public_path), load_json_object(answers_path)
    exact_keys(public, {"schema_version", "cases"})
    exact_keys(answers, {"schema_version", "public_sha256", "answers"})
    public_hash = sha256_json(public)
    if public_hash != require_sha256(expected_public_sha256, label="expected public SHA-256"):
        raise ValueError("public evidence differs from the explicitly approved input identity")
    if type(public["schema_version"]) is not int or public["schema_version"] != SCHEMA_VERSION \
            or type(answers["schema_version"]) is not int or answers["schema_version"] != SCHEMA_VERSION \
            or not isinstance(public["cases"], list) or not public["cases"] \
            or not isinstance(answers["answers"], list) \
            or answers["public_sha256"] != public_hash:
        raise ValueError("next-review input requires a matching nonempty schema-2 public/answer pair")

    by_id: dict[str, dict[str, Any]] = {}
    for answer in answers["answers"]:
        exact_keys(answer, {"case_id", "input_sha256"} | DIAGNOSIS_KEYS)
        case_id = answer["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in by_id:
            raise ValueError("next-review answers require unique nonempty case IDs")
        by_id[case_id] = answer

    suggestions = []
    seen: set[str] = set()
    allowed_fields = set(policy()["settings_schema"]["properties"])
    for case in public["cases"]:
        exact_keys(case, {"case_id", "group_id", "question", "evidence", "input_sha256"})
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in seen \
                or not isinstance(case["group_id"], str) or not case["group_id"] \
                or not isinstance(case["question"], str) or not case["question"].strip() \
                or not isinstance(case["evidence"], list) or not case["evidence"]:
            raise ValueError("invalid or repeated public diagnostic case")
        seen.add(case_id)
        if case["input_sha256"] != sha256_json({k: v for k, v in case.items() if k != "input_sha256"}):
            raise ValueError(f"public case identity changed: {case_id}")
        evidence_ids: set[str] = set()
        for item in case["evidence"]:
            exact_keys(item, {"evidence_id", "pointer", "value", "source_sha256"})
            evidence_id = item["evidence_id"]
            if not isinstance(evidence_id, str) or not evidence_id or evidence_id in evidence_ids \
                    or not isinstance(item["pointer"], str) or not item["pointer"].startswith("/") \
                    or isinstance(item["value"], (dict, list)):
                raise ValueError(f"invalid public evidence identity: {case_id}")
            require_sha256(item["source_sha256"], label="public evidence source SHA-256")
            evidence_ids.add(evidence_id)
        answer = by_id.get(case_id)
        if answer is None or answer["input_sha256"] != case["input_sha256"]:
            raise ValueError(f"missing or mismatched answer for {case_id}")
        error = diagnosis_error({key: answer[key] for key in DIAGNOSIS_KEYS}, evidence_ids)
        if error:
            raise ValueError(f"invalid diagnosis for {case_id}: {error}")
        status = answer["causal_status"]
        hints = _TS_FIELD_HINTS.get(answer["failure_class"], ()) if status != "unknown" else ()
        if not set(hints) <= allowed_fields:
            raise ValueError("strategy-review hint conflicts with existing strategy policy")
        suggestions.append({
            "case_id": case_id,
            "group_id": case["group_id"],
            "failure_class": answer["failure_class"],
            "causal_status": status,
            "causal_claim": answer["causal_claim"],
            "causal_evidence_ids": answer["causal_evidence_ids"],
            "next_review": answer["next_review"],
            "review_focus": _REVIEW_FOCUS[status],
            "ts_strategy_fields_to_review": list(hints),
            "requires_owning_review": True,
            "automatic_execution": False,
        })
    if set(by_id) != seen:
        raise ValueError("next-review answers must cover exactly the public case IDs")

    report = {
        "schema_version": 1,
        "status": "ADVISORY_ONLY_NOT_AUTHORIZED",
        "public_sha256": public_hash,
        "answers_sha256": sha256_file(answers_path),
        "policy_sha256": sha256_file(POLICY),
        "public_source_files_reverified": False,
        "causal_claims_scientifically_validated": False,
        "ts_strategy_changes_authorized": False,
        "recommendations": suggestions,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(report_path, report)
    return report
