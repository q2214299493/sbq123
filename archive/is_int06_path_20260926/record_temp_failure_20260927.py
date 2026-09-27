"""Read-only reconciliation evidence; never retry or remove reservations."""
from datetime import datetime, timezone
import subprocess

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.submission import submission_status
from archive.is_int06_path_20260926.prepare_vasp import ROOT, RUN


def main():
    assert submission_status(RUN)["status"] == "UNKNOWN_NEEDS_RECONCILIATION"
    receipt = RUN / "temporary_upload_failure_reconciliation_20260927.json"
    event_path = ROOT / "modules/state_handoff/events/task-is-a-int06-temp-upload-blocked-20260927.json"
    if receipt.exists() or event_path.exists():
        raise FileExistsError("Preserve immutable recovery evidence")
    remote = load_json_object(RUN / "submission_attempt.json")["remote_dir"]
    command = (
        "printf 'RESERVATION\\n'; "
        f"test -d {remote}.submission-reservation && cat {remote}.submission-reservation/reservation_id; "
        "printf 'TARGET_EXISTS\\n'; "
        f"if test -e {remote}; then ls -ld {remote}; find {remote} -maxdepth 2 -type f -print | head -n 20; "
        "else printf 'NO_TARGET_DIRECTORY\\n'; fi; "
        "printf 'SCHEDULER_CHECKPOINT\\n'; bjobs -a -w 2>&1 | head -c 4000"
    )
    result = subprocess.run(["ssh", "sunboquan-cdj1-temp", command],
                            capture_output=True, timeout=45)
    now = datetime.now(timezone.utc).isoformat()
    write_json(receipt, {"observed_at": now, "command": command,
                        "server_alias": "sunboquan-cdj1-temp", "exit_code": result.returncode,
                        "stdout": result.stdout.decode("utf-8", errors="replace"),
                        "stderr": result.stderr.decode("utf-8", errors="replace"),
                        "failed_stage": "SCP_UPLOAD_BEFORE_BSUB",
                        "failure": "scp: Received message too long 220204320; non-interactive shell banner",
                        "resolution": "Human confirmation required; preserve both local and remote reservations. No automatic retry."})
    prior = load_json_object(ROOT / "modules/state_handoff/events/task-is-a-int06-vasp-ssh-recheck-failed-20260926.json")
    paths = [(RUN / name, authority) for name, authority in (
        ("temporary_backend_precheck_retry1_20260927.json", "repository_document"),
        ("temporary_execution_gate_decision_20260927.json", "module_validation"),
        ("user_temporary_backend_request_20260927.json", "user_authorization"),
        ("submission_attempt.json", "repository_document"),
        ("submission_record.json", "repository_document"),
        (receipt.name, "repository_document"))]
    prior.update(event_id=event_path.stem, occurred_at=now, recorded_at=now,
                 summary="Authorized temporary account authenticated; VTST and exact POTCAR pass. SCP banner broke upload before bsub; preserve unresolved reservation and require operator recovery review.",
                 supersedes=[prior["event_id"]],
                 evidence=[{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                            "authority": authority, "observed_at": now} for p, authority in paths])
    prior["payload"].update(
        phase="blocked",
        current_evidence=[
            "User authorized temporary 10.68.0.103:22/nsgkx_cdj1 account for this existing coarse NEB only; separate alias sunboquan-cdj1-temp. Default backend unchanged.",
            "Login ycn03/LSF/VTST executable and Intel environment verified. Fe/C/O/H POTCAR assembled remotely from existing licensed datasets, exact original SHA256 e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85.",
            "Scientific/input bundle unchanged:108 ranks,9 interiors,NPAR4,Fast,EDIFF1e-5,EDIFFG-0.05,NSW300,SIGMA0.20,no pilot or restraints. New target-bound gate lists SUBMIT_VASP.",
            "Resolved legitimate mapped HOME path by canonical comparison while retaining symlink guards;51 related backend/submission/gate tests passed.",
            "Canonical executor created local/remote reservation, then SCP failed: Received message too long 220204320 because login banner contaminated transfer. bsub stage not reached; no new job ID obtained.",
            "Canonical status UNKNOWN_NEEDS_RECONCILIATION retained; read-only reservation/directory/scheduler evidence saved. Never remove marker or automatically retry."],
        one_executable_step="Review read-only upload-failure recovery evidence with the operator; obtain explicit confirmation of no matching job and authority for a new submission, then repair banner-safe transport without altering scientific inputs.",
        submission_boundary="No new submission or deletion of reservations until explicit human recovery confirmation. Keep default sunboquan-codex and accepted other reaction intervals unchanged.",
        authoritative_references=[p.relative_to(ROOT).as_posix() for p, _ in paths])
    write_json(event_path, prior)
    print(event_path)


if __name__ == "__main__":
    main()
