"""Record one explicitly authorized environment-only GPU retry, not submit it."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from scripts.artifact_io import load_json_object, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_is_a_int06_path_20260926/gpu_execution_20260926"


def main() -> None:
    destination = PACKAGE / "submission_record_retry1.json"
    if destination.exists():
        raise FileExistsError("Existing retry record must be preserved")
    job_id = (PACKAGE / "submission_retry1_slurm_job_id.txt").read_text(encoding="utf-8").strip()
    if not job_id.isdecimal():
        raise ValueError("Invalid Slurm submission receipt")
    scheduler_path = PACKAGE / f"scheduler_retry1_{job_id}.txt"
    scheduler = scheduler_path.read_text(encoding="utf-8")
    if f"JobId={job_id} " not in scheduler:
        raise ValueError("Scheduler job mismatch")
    state = re.search(r"\bJobState=(\w+)", scheduler)
    if not state or state.group(1) != "RUNNING":
        raise ValueError("This initial registration requires the observed RUNNING snapshot")
    request_sha = sha256_file(PACKAGE / "request.json")
    preflight = load_json_object(PACKAGE / "remote_preflight_retry1.json")
    if preflight["status"] != "PASS" or preflight["request_sha256"] != request_sha:
        raise ValueError("Stale remote preflight")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = {"schema_version": 1, "document_kind": "dual_model_gpu_submission_retry",
              "gpu_slurm_job_id": job_id, "previous_gpu_job_id": "1793", "request_sha256": request_sha,
              "scheduler_state_at_checkpoint": state.group(1), "scheduler_evidence_sha256": sha256_file(scheduler_path),
              "user_authorization_sha256": sha256_file(PACKAGE / "user_authorization_retry1.md"),
              "remote_preflight_sha256": sha256_file(PACKAGE / "remote_preflight_retry1.json"),
              "remote_root": "/home/sbq/sbq/aqcat25_ts_pilot/handoffs/h_migration_is_a_int06_gpu_20260926",
              "remote_output": "/home/sbq/sbq/aqcat25_ts_pilot/handoffs/h_migration_is_a_int06_gpu_20260926/output/run2",
              "environment_change": {"TMPDIR": "/home/sbq/sbq/aqcat25/tmp"}, "scientific_input_changes": [],
              "optimizer_progress": "not_yet_verified_at_initial_scheduler_checkpoint", "automatic_retry": False,
              "automatic_vasp_submission": False, "observed_at": now}
    write_json(destination, record)
    report = ROOT / "docs/reviews/is_a_int06_gpu1802_retry1_submitted_20260926.md"
    event = {"schema_version": 1, "occurred_at": now, "recorded_at": now,
             "event_id": "task-is-a-int06-gpu1802-retry1-submitted-20260926", "event_type": "task_updated",
             "entity": {"kind": "task", "id": "task-current", "module": "transition_state_search"},
             "summary": "User-authorized TMPDIR-only GPU retry1802 is RUNNING; scientific request unchanged and prior failure outputs preserved.",
             "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                           "authority": authority, "observed_at": now} for p, authority in
                          ((destination, "module_validation"), (scheduler_path, "scheduler"), (report, "repository_document"))],
             "review": {"required": False, "reason_codes": [], "status": "not_required"},
             "payload": {"objective": "Optimize the reviewed IS-A9725473 to INT06_9748648 H surface migration with MatRIS and AQCat25 audit before VASP coarse NEB.",
                         "phase": "active", "current_evidence": [
                             "Authorized retry1802 submitted once; scheduler RUNNING on MZ73.",
                             "TMPDIR is explicitly contained; request checksum check after wrapper environment setup passed.",
                             "Exact 11-image request6011d0a9 unchanged; MatRIS epoch6 ordinary ML-NEB plus AQCat25 fixed-path audit, max400 steps/fmax0.10.",
                             "Prior GPU1793/output/run1 preserved; no VASP, fine-tuning, ML-CI or added reaction-coordinate restraints.",
                             "Optimizer progress/convergence not yet verified at initial checkpoint; other processes leave6–8GB GPU memory, peak requirement unverified."],
                         "one_executable_step": "Collect GPU1802 runtime/producer completion or failure, then review the complete path geometry, peaks and exact AQCat25 audit before preparing VASP.",
                         "submission_boundary": "One retry was explicitly authorized and submitted. No automatic additional GPU rerun, fine-tuning or VASP submission.",
                         "done_when": ["GPU1802 produces reviewed complete-path evidence and audit, or a bounded failure with its first/last valid structures preserved."],
                         "constraints": ["Keep accepted INT06-MID and MID-FS segments unchanged.", "Preserve request/checkpoint hashes, atom order, fixed Fe0-17 and SIGMA0.20 compatibility.", "GPU predictions cannot establish a TS or electronic barrier."],
                         "authoritative_references": [report.relative_to(ROOT).as_posix(), destination.relative_to(ROOT).as_posix(),
                                                      (PACKAGE / "request.json").relative_to(ROOT).as_posix()]},
             "supersedes": ["task-is-a-int06-gpu1793-bootstrap-failed-20260926-v2"]}
    write_json(ROOT / "modules/state_handoff/events/task-is-a-int06-gpu1802-retry1-submitted-20260926.json", event)
    print(f"Recorded GPU{job_id} RUNNING checkpoint; no convergence claim.")


if __name__ == "__main__":
    main()
