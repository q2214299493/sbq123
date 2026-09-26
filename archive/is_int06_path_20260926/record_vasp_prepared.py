"""Record actual prepared-but-unsubmitted state after the SSH precheck failed."""
from datetime import datetime, timezone

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.submission import submission_status
from archive.is_int06_path_20260926.prepare_vasp import ROOT, RUN


def main():
    assert submission_status(RUN)["status"] == "NOT_RESERVED"
    assert load_json_object(RUN / "remote_submission_precheck.json")["status"] == "FAILED"
    event_path = ROOT / "modules/state_handoff/events/task-is-a-int06-gpu1802-vasp-prepared-ssh-blocked-20260926.json"
    if event_path.exists():
        raise FileExistsError("Preserve immutable state event")
    now = datetime.now(timezone.utc).isoformat()
    event = load_json_object(ROOT / "modules/state_handoff/events/task-is-a-int06-gpu1802-returned-20260926.json")
    event.update(event_id=event_path.stem, occurred_at=now, recorded_at=now,
                 summary="Full GPU1802 path reviewed and ordinary VASP NEB authorized/preflight-passed; SSH public-key handshake stalls, no upload/reservation/submission occurred.",
                 supersedes=[event["event_id"]])
    paths = [(RUN / name, authority) for name, authority in (
        ("path_review.json", "module_validation"), ("work_review_evidence.json", "structure_output"),
        ("execution_gate_decision.json", "module_validation"), ("submission_preflight.json", "module_validation"),
        ("remote_submission_precheck.json", "repository_document"),
        ("user_execution_request.json", "user_authorization"))]
    event["evidence"] = [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                          "authority": authority, "observed_at": now} for p, authority in paths]
    event["payload"].update(
        phase="blocked", objective="Submit the reviewed GPU1802 complete IS-A9725473 -> INT06_9748648 path as one ordinary VASP coarse NEB.",
        current_evidence=[
            "User authorized review then coarse NEB; full11-image GPU1802 path reviewed numerically and in top/side/profile views.",
            "H50 changes neighboring Fe coordination continuously; C2HO/originalCH remain intact, no new OH/CH bond. Three ML peaks remain predictions, not accepted TS/intermediates.",
            "Exact GPU snapshots copied without interpolation; locked PBE/ENCUT400/Gamma5x5x1/SIGMA0.20/Fe2.2 branch, Fast/EDIFF1e-5/EDIFFG-0.05/NSW300/no-climb/no-restraints.",
            "Nine interiors require rank/image/NPAR divisibility;108ranks=9x12,NPAR4. No pilot added. Geometry/VTST movie11frames/input custodian and canonical preflight pass; current gate lists SUBMIT_VASP.",
            "Bounded live SSH check exit255 timed out after connection/handshake; verbose read-only check stalled at public-key offer. No remote output/POTCAR verification obtained.",
            "Canonical submission state NOT_RESERVED: no executor reservation, upload,bsub or jobID. Submission authority remains available for this exact package, not consumed."],
        one_executable_step="When sunboquan-codex SSH authentication responds, rerun a new bounded read-only POTCAR/duplicate-job precheck, revalidate the existing gate and submit this exact authorized ordinary NEB once through the canonical executor.",
        submission_boundary="User already authorized one reviewed coarse NEB. No pilot, duplicate submission, automatic retry, CI,Dimer,training or changes to accepted intervals.",
        done_when=["One actual ordinary NEB submission receipt and scheduler checkpoint are recorded, or a bounded remote precheck failure is truthfully retained without claiming submission."],
        authoritative_references=[p.relative_to(ROOT).as_posix() for p, _ in paths])
    write_json(event_path, event)
    print(event_path)


if __name__ == "__main__":
    main()
