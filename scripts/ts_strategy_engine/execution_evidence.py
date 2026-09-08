from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import (
    load_json_object,
    sha256_file,
    source_file_manifest_valid,
)
from scripts.scheduler_evidence import validate_stored_lsf_evidence


TRUSTED_ARTIFACTS = {
    "geometry": ("neb_path_geometry_diagnosis", "scripts.neb_agent.diagnose_path_geometry"),
    "analysis": ("neb_output_analysis", "scripts.neb_agent.analyze_neb_outputs"),
    "path_quality": ("neb_path_quality_evidence", "scripts.neb_agent.path_quality_control"),
}


def load_bound_evidence(
    request_path: Path,
    request: dict[str, Any],
    name: str,
    bindings: dict[str, dict[str, str]],
    *,
    required: bool = False,
) -> dict[str, Any] | None:
    value = request.get(f"{name}_file")
    if not value:
        if required:
            raise ValueError(f"gate request missing: {name}_file")
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (request_path.parent / path).resolve()
    if not path.is_file():
        raise ValueError(f"gate evidence file not found: {path}")
    bindings[name] = {"path": str(path), "sha256": sha256_file(path)}
    return _load_source(path, name)


def source_bindings_valid(
    evidence: dict[str, Any],
    required: tuple[str, ...],
) -> bool:
    bindings = evidence.get("source_bindings", {})
    for name in required:
        binding = bindings.get(name, {})
        path = Path(str(binding.get("path", "")))
        if not path.is_file() or binding.get("sha256") != sha256_file(path):
            return False
        try:
            current = _load_source(path, name)
        except (OSError, ValueError, yaml.YAMLError):
            return False
        if current != evidence.get(name):
            return False
        if name == "scheduler":
            try:
                validate_stored_lsf_evidence(current)
            except ValueError:
                return False
        expected = TRUSTED_ARTIFACTS.get(name)
        if expected and (
            current.get("document_kind") != expected[0]
            or current.get("producer") != expected[1]
            or not source_file_manifest_valid(current)
        ):
            return False
    return True


def warning_reason_codes(
    geometry: dict[str, Any],
    analysis: dict[str, Any],
    quality: dict[str, Any],
) -> list[str]:
    flags = (
        (
            analysis.get("scf_warning") and not analysis.get("scf_failure"),
            "TRANSIENT_SCF_EXHAUSTION_WARNING",
        ),
        (
            bool(analysis.get("high_force_warnings")),
            "EARLY_OR_NONPERSISTENT_HIGH_FORCE_WARNING",
        ),
        (
            bool(analysis.get("internal_minimum_warning")),
            "TRANSIENT_INTERNAL_MINIMUM_WARNING",
        ),
        (geometry.get("status") == "REVIEW", "GEOMETRY_REVIEW_WARNING"),
    )
    reasons = [*quality.get("REASON_CODES", [])]
    reasons.extend(reason for active, reason in flags if active)
    return sorted(set(reasons))


def validated_ts(validation: dict[str, Any]) -> bool:
    source_method = str(validation.get("source_method", "")).lower()
    frequency_hash_valid = validation.get("frequency_structure_hash_valid") or (
        validation.get("source_saddle_sha256")
        and validation.get("source_saddle_sha256")
        == validation.get("frequency_poscar_sha256")
    )
    connectivity_valid = source_method == "dimer" or validation.get(
        "bidirectional_connectivity_valid"
    ) or (
        validation.get("connectivity_status") == "PASS"
        and validation.get("connects_to_is") is True
        and validation.get("connects_to_fs") is True
    )
    dimer_acceptance_valid = (
        source_method != "dimer"
        or validation.get("dimer_technical_acceptance") is True
    )
    return bool(
        validation.get("frequency_grade", validation.get("grade")) == "A"
        and frequency_hash_valid
        and connectivity_valid
        and dimer_acceptance_valid
    )


def authorized_actions(
    evidence: dict[str, Any],
    *other: str,
    stop_eligible: bool = False,
    required_sources: tuple[str, ...] = (),
) -> tuple[str, ...]:
    scheduler = evidence.get("scheduler", {})
    stop_allowed = scheduler.get("status") in {"PEND", "RUN"} and bool(
        scheduler.get("job_id")
    )
    stop_allowed = (
        stop_allowed
        and stop_eligible
        and source_bindings_valid(evidence, required_sources)
    )
    return (("STOP_JOB",) if stop_allowed else ()) + tuple(other)


def diagnostic_actions(
    evidence: dict[str, Any],
    *,
    stop_eligible: bool = False,
    required_sources: tuple[str, ...] = (),
) -> tuple[str, ...]:
    preflight = evidence["preflight"]
    ready = preflight.get("passed") and preflight.get("kind") == "diagnostic_static"
    return authorized_actions(
        evidence,
        *(("SUBMIT_DIAGNOSTIC_VASP",) if ready else ()),
        stop_eligible=stop_eligible,
        required_sources=required_sources,
    )


def _load_source(path: Path, name: str) -> dict[str, Any]:
    if name == "thresholds":
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("threshold evidence must be an object")
        return value
    return load_json_object(path)
