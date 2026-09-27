"""Record an actual submitted job, without promoting convergence or TS status."""
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.submission import submission_status
from scripts.scheduler_evidence import validate_stored_lsf_evidence
from archive.is_int06_path_20260926.prepare_vasp import ROOT, RUN as OLD
from archive.is_int06_path_20260926.prepare_temp_retry_20260928 import RUN


def main():
    assert submission_status(RUN)["status"] == "SUBMITTED"
    scheduler = load_json_object(RUN / "scheduler_checkpoint_submission.json")
    validate_stored_lsf_evidence(scheduler)
    assert scheduler["job_id"] == "9802439"
    old_manifest = load_json_object(OLD / "submission_preflight.json")["files"]
    manifest = load_json_object(RUN / "submission_preflight.json")["files"]
    assert old_manifest.keys() == manifest.keys()
    changed = [name for name in manifest if manifest[name] != old_manifest[name]]
    assert changed == ["path_geometry_diagnosis.json"]
    proof = RUN / "scientific_input_identity.json"
    event_path = ROOT / "modules/state_handoff/events/task-is-a-int06-neb9802439-submission-checkpoint-20260928.json"
    if event_path.exists():
        raise FileExistsError("Preserve immutable submission checkpoint")
    now = datetime.now(timezone.utc).isoformat()
    proof_payload = {"status": "PASS", "old_workdir": str(OLD), "new_workdir": str(RUN),
                       "unchanged_files": [name for name in manifest if name not in changed],
                       "changed_nonphysical_evidence": changed,
                       "reason": "Regenerated geometry parser manifest binds new absolute source paths; POSCARs/INCAR/KPOINTS/script/POTCAR.spec and reviewed path bytes unchanged.",
                       "old_preflight_sha256": sha256_file(OLD / "submission_preflight.json"),
                       "new_preflight_sha256": sha256_file(RUN / "submission_preflight.json")}
    if proof.exists():
        assert load_json_object(proof) == proof_payload
    else:
        write_json(proof, proof_payload)
    event = load_json_object(ROOT / "modules/state_handoff/events/task-is-a-int06-temp-upload-blocked-20260927.json")
    paths = [(RUN / name, authority) for name, authority in (
        ("submission_record.json", "repository_document"),
        ("submission_attempt.json", "repository_document"),
        ("scheduler_checkpoint_submission.json", "scheduler"),
        ("execution_gate_decision.json", "module_validation"),
        ("submission_preflight.json", "module_validation"),
        ("submission_recovery_review.json", "user_authorization"),
        ("user_execution_request.json", "user_authorization"),
        ("scientific_input_identity.json", "repository_document"))]
    event.update(event_id=event_path.stem, occurred_at=now, recorded_at=now,
                 summary="Banner-safe SSH tar transfer verified exact manifest; authorized new attempt submitted as LSF9802439 on temporary account. Scheduler PEND; no ionic/TS result.",
                 supersedes=[event["event_id"]],
                 evidence=[{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                            "authority": authority, "observed_at": now} for p, authority in paths])
    event["payload"].update(
        phase="active", objective="Monitor ordinary coarse NEB9802439 for the remaining IS-A9725473 -> INT06_9748648 H migration.",
        current_evidence=[
            "User continued after upload-failure recovery review; prior unresolved local/remote reservation remains immutable, separate new attempt directory used.",
            "New SSH tar stdin transfer avoids login-banner SCP framing failure. Remote canonical executor verified all input hashes and exact original Fe/C/O/H POTCAR before bsub.",
            "Actual LSF receipt:9802439 on sunboquan-cdj1-temp (10.68.0.103/nsgkx_cdj1), Gkn_normal. Latest hash-bound scheduler checkpoint PEND; VASP progress not yet established.",
            "Canonical initial compact monitor: images01-09 have0 ionic steps and no energy/force values. Missing output is not electronic convergence or TS evidence.",
            "Scientific files byte-identical:11 structures/9 interiors,108ranks/NPAR4,Fast,EDIFF1e-5,EDIFFG-0.05,NSW300,SIGMA0.20,no climb,pilot or restraints. New bundle hash differs only because geometry evidence binds new source paths.",
            "New workdir:calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_is_a_int06_gpu1802_neb_temp_r2_20260928; same basename under ~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/.",
            "54 backend/submission/execution-gate tests and88 scheduler evidence/mutation-boundary tests passed; targeted compilation/Ruff passed. No convergence/barrier/Grade-A claim."],
        one_executable_step="At the next requested checkpoint, query LSF9802439 on sunboquan-cdj1-temp and use the canonical compact NEB monitor; distinguish queue, SCF, ionic force and path states.",
        submission_boundary="One ordinary NEB submitted. No duplicate/retry, pilot, CI,Dimer, stop or parameter change without a fresh current gate and user authority; preserve old failure markers.",
        done_when=["NEB9802439 is monitored with scheduler and per-image evidence; a completed/stopped path is reviewed before any authorized refinement."],
        authoritative_references=[p.relative_to(ROOT).as_posix() for p, _ in paths])
    write_json(event_path, event)
    print(event_path)


if __name__ == "__main__":
    main()
