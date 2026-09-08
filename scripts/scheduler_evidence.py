from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from scripts.aqcat25_ts_schema import validate_document
from scripts.artifact_io import sha256_text
from scripts.execution_backends import load_execution_backends, require_vasp_backend


LSF_QUERY_TIMEOUT_SECONDS = 60


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_lsf_bjobs(stdout: str, expected_job_id: str) -> str:
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == str(expected_job_id):
            status = fields[2].upper()
            if status not in {"PEND", "RUN", "DONE", "EXIT"}:
                raise ValueError(f"unsupported live LSF status: {status}")
            return status
    raise ValueError(f"live bjobs output does not contain job {expected_job_id}")


def query_lsf_job(job_id: str, *, stage: str = "vasp_force_label") -> dict[str, Any]:
    job_id = str(job_id).strip()
    if not job_id:
        raise ValueError("LSF job_id is required")
    backend = load_execution_backends().vasp
    argv = ["ssh", backend.server_alias, "bjobs", "-a", job_id]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=LSF_QUERY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"live LSF query timed out for {job_id} after "
            f"{LSF_QUERY_TIMEOUT_SECONDS} seconds"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"live LSF query failed for {job_id}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    status = _parse_lsf_bjobs(completed.stdout, job_id)
    payload = {
        "schema_version": 1,
        "document_kind": "scheduler_job_evidence",
        "stage": stage,
        "scheduler": backend.name,
        "server_alias": backend.server_alias,
        "job_id": job_id,
        "status": status,
        "checked_at": _utc_now(),
        "source_command": f"ssh {backend.server_alias} bjobs -a {job_id}",
        "query": {
            "argv": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "stdout_sha256": sha256_text(completed.stdout),
        },
    }
    return validate_document(payload, expected_kind="scheduler_job_evidence")


def verify_lsf_evidence_live(
    evidence: dict[str, Any],
    *,
    required_status: str,
    live_query: Callable[..., dict[str, Any]] = query_lsf_job,
) -> dict[str, Any]:
    validate_stored_lsf_evidence(evidence, required_status=required_status)
    live = live_query(str(evidence["job_id"]), stage=str(evidence["stage"]))
    validate_document(live, expected_kind="scheduler_job_evidence")
    require_vasp_backend(live.get("server_alias"), live.get("scheduler"))
    if live["job_id"] != evidence["job_id"] or live["status"] != required_status:
        raise ValueError("live LSF state does not confirm the required terminal status for this job")
    return live


def validate_stored_lsf_evidence(
    evidence: dict[str, Any],
    *,
    required_status: str | None = None,
) -> None:
    validate_document(evidence, expected_kind="scheduler_job_evidence")
    require_vasp_backend(evidence.get("server_alias"), evidence.get("scheduler"))
    query = evidence["query"]
    if sha256_text(query["stdout"]) != query["stdout_sha256"]:
        raise ValueError("stored LSF stdout hash mismatch")
    parsed_status = _parse_lsf_bjobs(query["stdout"], str(evidence["job_id"]))
    if parsed_status != evidence["status"]:
        raise ValueError("stored LSF status does not match its raw bjobs output")
    if required_status is not None and evidence["status"] != required_status:
        raise ValueError(f"stored LSF state is not {required_status}")
