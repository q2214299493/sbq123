"""Raw/live Slurm scheduler evidence for the explicitly scoped MZ73 labels.

This establishes scheduler state only. Scientific label ingestion must also
validate VASP completion, SCF convergence, structures, forces and provenance.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.execution_backends import DEFAULT_CONFIG
from scripts.neb_agent.mz73_static import (
    BACKEND_ID,
    LAUNCHER,
    canonical_remote_path,
    load_mz73_static_backend,
    require_remote_target,
    ssh_argv,
)
from scripts.ts_strategy_engine.execution_path_rules import require_job_id


QUERY_TIMEOUT_SECONDS = 20
MAX_STDOUT_BYTES = 65536
DOCUMENT_KIND = "slurm_force_label_scheduler_evidence"
_FIELDS = {"JobId", "JobState", "ExitCode", "WorkDir", "Command"}


def parse_scontrol_job(stdout: str, job_id: str) -> dict[str, str]:
    """Parse one native ``scontrol -o show job`` record without status mapping."""
    job_id = require_job_id(job_id)
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > MAX_STDOUT_BYTES:
        raise ValueError("invalid or oversized raw Slurm stdout")
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("Slurm stdout must contain exactly one job record")
    line = lines[0]
    matches = list(re.finditer(r"(?:^|[ \t])([A-Za-z][A-Za-z0-9_]*)=", line))
    fields = {}
    for index, match in enumerate(matches):
        key = match.group(1)
        if key not in _FIELDS:
            continue
        if key in fields:
            raise ValueError(f"duplicate Slurm identity field: {key}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        fields[key] = line[match.end():end].strip()
    if set(fields) != _FIELDS or any(not value for value in fields.values()):
        raise ValueError("missing required Slurm job identity fields")
    if require_job_id(fields["JobId"]) != job_id:
        raise ValueError("raw Slurm output belongs to a different job")
    if not re.fullmatch(r"[A-Z_]+(?:\+)?", fields["JobState"]):
        raise ValueError("invalid native Slurm state")
    if not re.fullmatch(r"[0-9]+:[0-9]+", fields["ExitCode"]):
        raise ValueError("invalid native Slurm exit code")
    return {"job_id": fields["JobId"], "job_state": fields["JobState"],
            "exit_code": fields["ExitCode"], "remote_dir": fields["WorkDir"],
            "command": fields["Command"]}


def _target(job_id, remote_dir, workdir_name, config_path):
    job_id = require_job_id(str(job_id).strip())
    backend = load_mz73_static_backend(workdir_name, config_path=Path(config_path))
    require_remote_target(backend, remote_dir, workdir_name)
    canonical = canonical_remote_path(backend, remote_dir)
    return job_id, backend, canonical


def query_slurm_force_label(
    job_id: str, remote_dir: str, workdir_name: str, *, config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Capture one read-only query; PENDING/RUNNING remain their native states."""
    job_id, backend, _ = _target(job_id, remote_dir, workdir_name, config_path)
    command = f"scontrol -o show job {job_id}"
    argv = ssh_argv(backend, command)
    try:
        completed = subprocess.run(argv, capture_output=True, check=False, timeout=QUERY_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Slurm job {job_id} query timed out; no automatic retry") from error
    if completed.returncode != 0:
        raise RuntimeError(f"Slurm job {job_id} query failed with exit code {completed.returncode}")
    if len(completed.stdout) > MAX_STDOUT_BYTES:
        raise ValueError("oversized raw Slurm stdout")
    stdout, stderr = completed.stdout.decode("utf-8"), completed.stderr.decode("utf-8")
    parsed = parse_scontrol_job(stdout, job_id)
    evidence = {
        "schema_version": 1, "document_kind": DOCUMENT_KIND, "scheduler": "Slurm",
        "backend_id": BACKEND_ID, "backend_config_sha256": backend["config_sha256"],
        "result_class": "scheduler_state_only", "workdir_name": workdir_name,
        "checked_at": datetime.now(timezone.utc).isoformat(), **parsed,
        "query": {"argv": argv, "returncode": completed.returncode, "stdout": stdout,
                  "stderr": stderr, "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest()},
    }
    validate_stored_slurm_force_label(evidence, job_id=job_id, remote_dir=remote_dir,
                                     workdir_name=workdir_name, config_path=config_path, require_completed=False)
    return evidence


def validate_stored_slurm_force_label(
    evidence: dict[str, Any], *, job_id: str, remote_dir: str, workdir_name: str,
    config_path: Path = DEFAULT_CONFIG, require_completed: bool = True,
) -> dict[str, str]:
    """Check cached integrity only; acceptance still requires live verification."""
    job_id, backend, canonical = _target(job_id, remote_dir, workdir_name, config_path)
    if not isinstance(evidence, dict) or (
        evidence.get("schema_version") != 1 or evidence.get("document_kind") != DOCUMENT_KIND
        or evidence.get("scheduler") != "Slurm" or evidence.get("backend_id") != BACKEND_ID
        or evidence.get("result_class") != "scheduler_state_only"
        or evidence.get("backend_config_sha256") != backend["config_sha256"]
        or evidence.get("workdir_name") != workdir_name or evidence.get("job_id") != job_id
    ):
        raise ValueError("stored Slurm evidence identity or configuration mismatch")
    query = evidence.get("query")
    if not isinstance(query, dict) or not isinstance(query.get("stdout"), str) or query.get("returncode") != 0:
        raise ValueError("stored Slurm evidence lacks a successful raw scheduler query")
    if hashlib.sha256(query["stdout"].encode("utf-8")).hexdigest() != query.get("stdout_sha256"):
        raise ValueError("stored Slurm stdout hash mismatch")
    if query.get("argv") != ssh_argv(backend, f"scontrol -o show job {job_id}"):
        raise ValueError("stored Slurm query command does not match the bound backend and job")
    parsed = parse_scontrol_job(query["stdout"], job_id)
    if any(evidence.get(key) != value for key, value in parsed.items()):
        raise ValueError("stored Slurm metadata differs from its raw scheduler record")
    if parsed["remote_dir"] not in {remote_dir, canonical}:
        raise ValueError("Slurm WorkDir does not match the exact authorized label directory")
    if parsed["command"] not in {remote_dir + "/" + LAUNCHER, canonical + "/" + LAUNCHER}:
        raise ValueError("Slurm Command does not match the authorized script.sbatch")
    if require_completed and (parsed["job_state"] != "COMPLETED" or parsed["exit_code"] != "0:0"):
        raise ValueError("Slurm label requires native COMPLETED with ExitCode=0:0")
    return parsed


def verify_slurm_force_label_live(
    evidence: dict[str, Any], *, job_id: str, remote_dir: str, workdir_name: str,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Recheck the same bound job live before accepting cached terminal evidence."""
    arguments = {"job_id": job_id, "remote_dir": remote_dir,
                 "workdir_name": workdir_name, "config_path": config_path}
    if evidence.get("document_kind") == "slurm_native_controller_exit_events":
        from scripts.slurm_controller_events import verify_controller_events_live

        return verify_controller_events_live(evidence, **arguments)
    validate_stored_slurm_force_label(evidence, **arguments)
    live = query_slurm_force_label(**arguments)
    validate_stored_slurm_force_label(live, **arguments)
    return live
