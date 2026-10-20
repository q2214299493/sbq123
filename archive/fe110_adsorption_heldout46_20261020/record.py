"""Record the completed force test, not model promotion or VASP speedup."""
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

from .validate import DEST, PROPOSAL_SHA, ROOT


def main():
    report = load_json_object(DEST / "independent_force_review.json")
    if report["proposal_sha256"] != PROPOSAL_SHA or report["status"] != "FROZEN46_INDEPENDENT_FORCE_TEST_COMPLETE_NOT_PROMOTION":
        raise ValueError("wrong independent force result")
    suites = ET.parse(DEST / "scoped_tests.xml").getroot().findall("testsuite")
    tests = {k: sum(int(s.attrib[k]) for s in suites) for k in ("tests", "errors", "failures", "skipped")}
    if tests["tests"] < 47 or any(tests[k] for k in ("errors", "failures", "skipped")):
        raise ValueError("related software tests did not pass")
    doc = ROOT / "docs/reviews/fe110_adsorption_control_heldout46_20261020.md"
    files = [DEST / n for n in ("validation_request.json", "submission_authorization.json", "preparation_receipt.json",
        "independent_force_review.json", "scoped_tests.xml", "returned/output/producer_exit_record.json",
        "returned/output/baseline_device.json", "returned/output/candidate_device.json",
        "returned/output/baseline_forces.json", "returned/output/candidate_forces.json", "returned/return_manifest.json")]
    files += [doc, Path(__file__), Path(__file__).with_name("validate.py"),
              ROOT / "archive/fe110_adsorption_validation_20261018/runtime.py"]
    receipt = {"status": "FROZEN46_FORCE_TEST_VERIFIED_GEOMETRY_AND_SPEEDUP_UNTESTED", "tests": tests,
        "request_sha256": report["request_sha256"], "proposal_sha256": PROPOSAL_SHA,
        "candidate_sha256": report["models"]["candidate"]["sha256"], "sample_count": 46, "prediction_count": 92,
        "improved_frame_count": report["framewise_adsorbate_RMSE_lower_count"],
        "training_performed": False, "new_VASP": False, "model_promoted": False, "measured_speedup": False,
        "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in files]}
    write_json_exclusive(DEST / "validation_receipt.json", receipt)
    now = datetime.now(timezone.utc).isoformat()
    event_id = "task-fe110-adsorption-control-heldout46-verified-20261020"
    evidence_paths = [doc, DEST / "validation_receipt.json", DEST / "independent_force_review.json"]
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": {"kind": "task", "id": "task-current", "module": "adsorption_workflow"},
        "summary": "Authorized frozen46 baseline/control exact-force validation completed on CUDA;all46 framewise adsorption RMSEs lower.No training,relaxation,VASP,promotion or measured speedup.",
        "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                      "authority": "repository_document", "observed_at": now} for p in evidence_paths],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": ["task-fe110-adsorption-control-candidate-review-20261020"],
        "payload": {"objective": "Review the completed frozencontrol independent force test;prepare no further compute without separate scope authorization.",
            "phase": "verification", "current_evidence": [
                "User request:验证.One force-only batch authorized:46exact structures,92predictions,600s,no retries.",
                "MZ73 physicalGPU1 completed92predictions in10.83s;both model tensors on CUDA,producer exit0.Hash-bound returns verified.",
                "Frozen46 from09_C/10_A23each;excluded from current training/development.Oldobserved16 quarantined;no test-driven model reselection.",
                "Adsorbate vectorRMSE0.2008503->0.0623483eV/A;46/46frames lower.C0.273153->0.085540,O0.306065->0.077458,H0.047502->0.026850.",
                "09_C adsorptionRMSE0.175747->0.047953;10_A0.223147->0.073994eV/A.Two correlated trajectories only,not broad domain certification.",
                "Adsorbate maximum error0.431043->0.163611eV/A;candidate worst movable error0.227754.Nearest-final sampled DFT forces0.0213/0.0215,not converged endpoints.",
                "77related tests passed.No geometric optimization,new VASP,energy ranking,production promotion or measured acceleration."],
            "one_executable_step": "Present a small same-seed pre-relaxation/near-minimum drift comparison for separate authorization before any new GPU or VASP execution.",
            "submission_boundary": "AUTHORIZED46_FORCE_TEST_COMPLETE_ONLY:no further GPU training/relaxation,VASP submission or default-model replacement authorized.",
            "done_when": ["Frozen force results,role/job/tail/near-final behavior and limitations are documented.",
                "Any proposed next geometry or matched VASP benchmark receives separate scope/budget authorization.",
                "Actual geometry retention and matched VASP steps/time are tested before claiming acceleration."],
            "constraints": ["Preserve frozen checkpoint,proposal and raw source bytes;no heldout-driven model reselection.",
                "46frames are two correlated trajectories;mother-job screening and unknown base-pretraining overlap remain disclosed.",
                "C2H3 extrapolation bounded to10_A;10_C high-force rearrangement and TS-domain remain unvalidated.",
                "Current success is force prediction,not optimizer stability or VASP speedup;do not promote automatically."],
            "authoritative_references": ["configs/execution_backends.yaml", doc.relative_to(ROOT).as_posix(),
                (DEST / "validation_receipt.json").relative_to(ROOT).as_posix(),
                (DEST / "independent_force_review.json").relative_to(ROOT).as_posix()]}}
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print(json.dumps({"status": receipt["status"], "tests": tests, "event": target.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    main()
