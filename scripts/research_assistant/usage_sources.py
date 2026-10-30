"""Shared strict readers for immutable RSI usage and additive feedback sources."""
import math
from pathlib import Path
from datetime import datetime

from scripts.ts_strategy_engine.review_evidence import _no_links
from .catalog import blocked

from scripts.artifact_io import load_json_object, sha256_file

from .policies import checked_reference


def application_source(run, receipt=None):
    receipt = receipt or load_json_object(run / "run_receipt.json")
    reference = receipt.get("rsi_application")
    if not reference:
        return {"status": "LEGACY_RUN_NO_RSI_RECORD"}
    return load_json_object(checked_reference(reference))


def feedback_source(run, path):
    _no_links(path.absolute())
    value = load_json_object(path)
    if value["run_receipt_sha256"] != sha256_file(run / "run_receipt.json"):
        raise ValueError("usage feedback receipt binding differs")
    usage = value["usage_feedback"]
    if not isinstance(usage, dict):
        raise ValueError("usage feedback must be an object")
    if not isinstance(value.get("recorded_at"), str):
        raise ValueError("feedback recording time is missing or malformed")
    datetime.fromisoformat(value["recorded_at"])
    validate_feedback_request(run, {**usage, "scientific_result_reference": value.get("scientific_result_reference")}, load_json_object(run / "run_receipt.json"))
    return value


def comparison_source(run, path):
    _no_links(path.absolute())
    binding = load_json_object(path)
    if binding.get("run_receipt_sha256") != sha256_file(run / "run_receipt.json"):
        raise ValueError("comparison belongs to a different immutable run receipt")
    checked_reference(binding["comparison_reference"])
    return binding["comparison_reference"]


def later_feedback(path, value):
    reference = {"path": str(path), "sha256": sha256_file(path)}
    return [{"feedback_ref": reference, "recorded_at": value["recorded_at"], "user_report": item}
            for item in value["usage_feedback"].get("rsi_feedback", [])]


def validate_feedback_request(run, value, receipt):
    from .policy_cli import validate_usage_feedback
    required = {"adopted", "evidence_effectiveness", "repeated_checks", "followup_notes", "scientific_result_reference"}
    if not required <= set(value) or set(value) - required - {"human_review_seconds", "adopted_option_ids", "rsi_feedback", "human_preparation_seconds", "human_correction_seconds"} \
            or (value["adopted"] is not None and type(value["adopted"]) is not bool):
        raise ValueError("feedback requires separate adoption/evidence/repetition/followup/scientific-reference fields")
    if not isinstance(value["evidence_effectiveness"], list) or not isinstance(value["repeated_checks"], list) \
            or not isinstance(value["followup_notes"], str):
        raise ValueError("invalid usage feedback types")
    known = {p.stem for p in (run / "tools").glob("E[0-9][0-9][0-9].json")}
    for item in value["evidence_effectiveness"]:
        if set(item) != {"evidence_id", "effective", "reason"} or item["evidence_id"] not in known \
                or (item["effective"] is not None and type(item["effective"]) is not bool) or not isinstance(item["reason"], str):
            raise ValueError("feedback must refer to actual host actions and explicit unknown/boolean effectiveness")
    if not set(value["repeated_checks"]) <= known:
        raise ValueError("unrecorded repeated check")
    result = value["scientific_result_reference"]
    if result is not None and (not isinstance(result, dict) or set(result) != {"path", "sha256"}
                               or blocked(Path(result["path"])) or sha256_file(Path(result["path"])) != result["sha256"]):
        raise ValueError("scientific result reference must be a real separately checked owner artifact")
    if result is not None:
        _no_links(Path(result["path"]).absolute())
    for key in ("human_review_seconds", "human_preparation_seconds", "human_correction_seconds"):
        seconds = value.get(key)
        if seconds is not None and (type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds < 0):
            raise ValueError("human time must be explicitly measured or unknown")
    selected = value.get("adopted_option_ids", [])
    options = {row["id"] for row in load_json_object(run / "research_result.json")["answer"]["options"]} if selected else set()
    if not isinstance(selected, list) or any(not isinstance(v, str) or v not in options for v in selected) or (selected and value["adopted"] is not True):
        raise ValueError("adopted branches require explicit adoption of existing option IDs")
    validate_usage_feedback(run, value, receipt)
