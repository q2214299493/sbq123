"""Record actual GPU bootstrap failure and a non-executable minimal retry plan."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_is_a_int06_path_20260926/gpu_execution_20260926"


def main() -> None:
    if (PACKAGE / "submission_record.json").exists():
        raise FileExistsError("Preserve existing attempt record")
    request = load_json_object(PACKAGE / "request.json")
    request_sha = sha256_file(PACKAGE / "request.json")
    failure_path = PACKAGE / "producer_exit_record.failure.1793.1703571.json"
    failure = load_json_object(failure_path)
    scheduler = (PACKAGE / "scheduler_1793.txt").read_text(encoding="utf-8")
    environment = (PACKAGE / "batch-env-probe-1794.out").read_text(encoding="utf-8")
    if (PACKAGE / "submission_slurm_job_id.txt").read_text(encoding="utf-8").strip() != "1793":
        raise ValueError("Wrong submission job")
    if "JobState=FAILED" not in scheduler or "ExitCode=2:0" not in scheduler or "TMPDIR=/tmp" not in environment:
        raise ValueError("Missing failure/environment evidence")
    if failure["gpu_job_id"] != "1793" or failure["exit_code"] != 2:
        raise ValueError("Wrong producer receipt")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = {"schema_version": 1, "document_kind": "dual_model_gpu_submission_attempt",
              "gpu_slurm_job_id": "1793", "remote_root": "/home/sbq/sbq/aqcat25_ts_pilot/handoffs/h_migration_is_a_int06_gpu_20260926",
              "scheduler_state": "FAILED", "scheduler_evidence_sha256": sha256_file(PACKAGE / "scheduler_1793.txt"),
              "request_sha256": request_sha, "producer_exit_receipt_sha256": sha256_file(failure_path),
              "producer_exit_code": 2, "model_executed": False, "optimizer_steps": 0,
              "primary_checkpoint_sha256": request["models"]["primary"]["checkpoint_sha256"],
              "secondary_checkpoint_sha256": request["models"]["secondary"]["checkpoint_sha256"],
              "diagnostic_cpu_job_id": "1794", "diagnostic_gpu_count": 0,
              "diagnostic_environment_sha256": sha256_file(PACKAGE / "batch-env-probe-1794.out"),
              "failure_class": "batch_environment_write_boundary_TMPDIR", "recorded_at": now,
              "automatic_retry": False, "automatic_vasp_submission": False}
    write_json(PACKAGE / "submission_record.json", record)
    write_json(PACKAGE / "environment_retry_plan.json", {"status": "prepared_requires_user_authorization",
              "request_sha256": request_sha, "change": {"TMPDIR": "/home/sbq/sbq/aqcat25/tmp"},
              "scientific_input_changes": [], "new_output_suffix": "run2",
              "no_model_setup_test": "PASS_exit0", "resubmitted": False, "automatic_retry": False})
    report = ROOT / "docs/reviews/is_a_int06_gpu1793_bootstrap_failure_20260926.md"
    event = {"schema_version": 1, "occurred_at": now, "recorded_at": now,
             "event_id": "task-is-a-int06-gpu1793-bootstrap-failed-20260926-v2", "event_type": "task_updated",
             "entity": {"kind": "task", "id": "task-current", "module": "transition_state_search"},
             "summary": "Authorized GPU1793 failed before model startup; scheduled TMPDIR write-boundary cause confirmed and minimal environment-only retry prepared, not submitted.",
             "evidence": [{"locator": str(p.relative_to(ROOT).as_posix()), "sha256": sha256_file(p),
                           "authority": authority, "observed_at": now} for p, authority in
                          ((report, "repository_document"), (PACKAGE / "submission_record.json", "module_validation"),
                           (PACKAGE / "scheduler_1793.txt", "scheduler"))],
             "review": {"required": False, "reason_codes": [], "status": "not_required"},
             "payload": {"objective": "Accelerate remaining IS-A9725473 to INT06_9748648 H surface migration with MatRIS, audit with AQCat25, then review before VASP coarse NEB.",
                         "phase": "verification",
                         "current_evidence": ["Reviewed 11-image candidate and local/remote model-free input/runtime/checkpoint checks PASS; exact path remains unchanged.",
                                              "Slurm GPU1793 FAILED ExitCode2:0 after2 seconds; wrapper receipt confirms bootstrap failure; zero optimizer steps and no model output.",
                                              "CPU-only environment probe1794 confirms TMPDIR=/tmp; explicit /home/sbq/sbq/aqcat25/tmp passes no-model setup.",
                                              "Environment-only retry prepared; no second GPU model run or VASP submission."],
                         "one_executable_step": "Obtain authorization for one resubmission with explicit contained TMPDIR, unchanged request/checkpoints, fresh output/run2 and no automatic retry.",
                         "submission_boundary": "1793 was submitted once under user authority; it failed before model startup. A separate authorization is needed for the prepared retry; no VASP authorized.",
                         "done_when": ["One GPU run produces a complete reviewed candidate path plus exact AQCat25 audit, or records a bounded diagnosable failure before choosing the next route."],
                         "constraints": ["Keep accepted INT06-MID and MID-FS calculations unchanged.", "No added coordinate restraints, ML-CI, automatic retry/fine-tuning or VASP submission.", "Preserve SIGMA0.20 compatibility and fixed Fe0-17."],
                         "authoritative_references": [str(report.relative_to(ROOT).as_posix()), str((PACKAGE / "request.json").relative_to(ROOT).as_posix()),
                                                      str((PACKAGE / "submission_record.json").relative_to(ROOT).as_posix()),
                                                      str((PACKAGE / "environment_retry_plan.json").relative_to(ROOT).as_posix())]},
             "supersedes": ["task-is-a-int06-path-prepared-20260926"]}
    write_json(ROOT / "modules/state_handoff/events/task-is-a-int06-gpu1793-bootstrap-failed-20260926-v2.json", event)
    print("GPU1793 failure recorded; environment-only retry remains unsubmitted.")


if __name__ == "__main__":
    main()
