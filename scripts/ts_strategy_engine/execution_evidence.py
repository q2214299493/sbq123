from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import (
    load_json_object,
    require_sha256,
    sha256_file,
    sha256_json,
    source_file_manifest_valid,
)
from scripts.scheduler_evidence import validate_stored_lsf_evidence

from .execution_decision import ACTIONS, ScientificReadiness


TRUSTED_ARTIFACTS = {
    "geometry": ("neb_path_geometry_diagnosis", "scripts.neb_agent.diagnose_path_geometry"),
    "analysis": ("neb_output_analysis", "scripts.neb_agent.analyze_neb_outputs"),
    "path_quality": ("neb_path_quality_evidence", "scripts.neb_agent.path_quality_control"),
}

EXECUTION_ACTIONS = frozenset({
    "CONTINUE_JOB", "STOP_JOB", "SUBMIT_DIAGNOSTIC_VASP", "SUBMIT_VASP",
    "ENABLE_CI_NEB", "START_DIMER", "START_VFA",
})


def workdir_identity(workdir: Path) -> str:
    """Canonical directory identity; independent of relative paths and aliases."""
    resolved = workdir.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("execution workdir must be a directory")
    return os.path.normcase(str(resolved))


def execution_evidence_sha256(evidence: dict[str, Any]) -> str:
    """Bind scientific inputs without a circular hash through authorization."""
    payload = {key: value for key, value in evidence.items() if key != "authorization"}
    payload["source_bindings"] = {
        key: value for key, value in evidence.get("source_bindings", {}).items()
        if key != "authorization"
    }
    return sha256_json(payload)


@dataclass(frozen=True)
class EvidenceBinding:
    workdir_identity: str
    bundle_sha256: str
    evidence_sha256: str


@dataclass(frozen=True)
class ExecutionAuthorization:
    action: str
    target_json: str
    binding: EvidenceBinding
    source_path: str
    source_sha256: str
    potcar_json: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": json.loads(self.target_json),
            "binding": asdict(self.binding),
            "source": {"path": self.source_path, "sha256": self.source_sha256},
            "potcar": json.loads(self.potcar_json),
        }


def require_execution_authorization(evidence: dict[str, Any]) -> ExecutionAuthorization:
    """Validate an explicit, file-bound scope; a scientific PASS grants no authority."""
    auth = evidence.get("authorization", {})
    if (
        auth.get("schema_version") != 1
        or auth.get("document_kind") != "user_execution_authorization"
        or auth.get("action") not in EXECUTION_ACTIONS
        or not auth.get("authorized_at")
    ):
        raise ValueError("explicit execution authorization is missing or invalid")
    binding = EvidenceBinding(
        workdir_identity(Path(auth["workdir_identity"])),
        require_sha256(auth["bundle_sha256"], label="authorized bundle"),
        require_sha256(auth["evidence_sha256"], label="authorized evidence"),
    )
    if binding.workdir_identity != auth["workdir_identity"]:
        raise ValueError("authorization workdir identity is not canonical")
    if binding.evidence_sha256 != execution_evidence_sha256(evidence):
        raise ValueError("execution authorization evidence is stale")
    preflight = evidence.get("preflight", {})
    if preflight and binding.bundle_sha256 != preflight.get("bundle_sha256"):
        raise ValueError("execution authorization bundle mismatch")
    required = tuple(
        name for name in ("geometry", "analysis", "thresholds", "path_quality",
                          "preflight", "validation", "scheduler", "authorization")
        if evidence.get(name) or name in {"thresholds", "authorization"}
    )
    if not source_bindings_valid(evidence, required):
        raise ValueError("execution evidence binding is missing or stale")
    target = auth["target"]
    if not isinstance(target, dict) or not target.get("server_alias") or not target.get("remote_dir"):
        raise ValueError("execution authorization target is incomplete")
    source = auth["source"]
    source_path = Path(source["path"])
    source_digest = require_sha256(source["sha256"], label="authorization source")
    if not source_path.is_absolute() or sha256_file(source_path) != source_digest:
        raise ValueError("authorization source is missing or changed")
    potcar = auth.get("potcar", {})
    if auth["action"] not in {"STOP_JOB", "CONTINUE_JOB"}:
        if not preflight or not potcar.get("source"):
            raise ValueError("submission authorization needs a preflight and POTCAR identity")
        require_sha256(potcar["sha256"], label="authorized POTCAR")
        require_sha256(potcar["spec_sha256"], label="authorized POTCAR.spec")
        if potcar["spec_sha256"] != preflight.get("files", {}).get("POTCAR.spec"):
            raise ValueError("POTCAR identity does not bind the bundle specification")
    else:
        if str(target.get("job_id")) != str(evidence.get("scheduler", {}).get("job_id")):
            raise ValueError("authorization target does not bind the scheduler job")
    return ExecutionAuthorization(
        auth["action"], json.dumps(target, sort_keys=True), binding,
        str(source_path), source_digest, json.dumps(potcar, sort_keys=True),
    )


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
    """Legacy summary predicate only; scientific_claims owns claim application."""
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


def bind_execution(decision: dict[str, Any]) -> dict[str, Any]:
    readiness = ScientificReadiness(
        decision["DECISION"], tuple(decision["REASON_CODES"]),
        tuple(decision["ALLOWED_ACTIONS"]),
    )
    decision["scientific_readiness"] = {
        "decision": readiness.decision,
        "reason_codes": list(readiness.reason_codes),
        "eligible_actions": list(readiness.eligible_actions),
    }
    authorization = None
    try:
        authorization = require_execution_authorization(decision["EVIDENCE"])
    except (KeyError, TypeError, AttributeError, OSError, ValueError) as exc:
        decision["execution_authorization_error"] = str(exc)
    else:
        decision["execution_authorization_error"] = None
    decision["execution_authorization"] = authorization.as_dict() if authorization else None
    decision["evidence_binding"] = (
        decision["execution_authorization"]["binding"] if authorization else None
    )
    allowed = [
        action for action in readiness.eligible_actions
        if action not in EXECUTION_ACTIONS or (authorization and authorization.action == action)
    ]
    decision["ALLOWED_ACTIONS"] = allowed
    decision["FORBIDDEN_ACTIONS"] = [action for action in ACTIONS if action not in allowed]
    decision["SUBMISSION_ALLOWED"] = bool(set(allowed) & (EXECUTION_ACTIONS - {"STOP_JOB", "CONTINUE_JOB"}))
    decision["CI_NEB_ALLOWED"] = "ENABLE_CI_NEB" in allowed
    decision["DIMER_ALLOWED"] = "START_DIMER" in allowed
    decision["VFA_ALLOWED"] = "START_VFA" in allowed
    return decision
