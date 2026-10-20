"""Verify local package bindings and record preparation, never submission."""
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from archive.fe110_adsorption_paired_vasp3_20261020.prepare import (
    ARMS, DEST, NAMES, ROOT, check_pair,
)
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


def main():
    parent_id = "task-fe110-adsorption-control-geometry3-reviewed-20261020"
    projection = load_json_object(ROOT / "data/state_handoff/projection_manifest.json")
    current = projection["projections"]["tasks/current_task.md#current_task"]
    if current["source_event_id"] != parent_id:
        raise ValueError("current task source changed;do not supersede")
    manifest_path = DEST / "batch_manifest.json"
    manifest = load_json_object(manifest_path)
    if (manifest["status"] != "PREPARED_LOCAL_ONLY" or manifest["execution_authorized"]
            or manifest["ALLOWED_ACTIONS"] or manifest["uploaded"] or manifest["new_VASP"]
            or manifest["new_GPU"] or manifest["model_promoted"] or manifest["measured_speedup"]):
        raise ValueError("preparation-only boundary changed")
    if len(manifest["jobs"]) != 6:
        raise ValueError("six jobs required")
    for source in manifest["sources"] + manifest["generation_sources"]:
        if sha256_file(ROOT / source["path"]) != source["sha256"]:
            raise ValueError("source/generator binding changed: " + source["path"])
    for job in manifest["jobs"]:
        folder = ROOT / job["path"]
        for name, digest in job["files"].items():
            if sha256_file(folder / name) != digest:
                raise ValueError("prepared input changed")
        report = load_json_object(folder / "submission_preflight.json")
        if (sha256_file(folder / "submission_preflight.json") != job["preflight_sha256"]
                or not report["passed"] or report["bundle_sha256"] != job["bundle_sha256"]
                or job["scheduler_status"] != "NOT_SUBMITTED" or job["scheduler_job_id"] is not None):
            raise ValueError("preflight/submission state changed")
    for name in NAMES:
        check_pair(DEST / name / ARMS[0], DEST / name / ARMS[1])
    xml = DEST.parent / "paired_vasp3_preparation_tests_fixed_20261020.xml"
    suites = ET.parse(xml).getroot().findall("testsuite")
    tests = {k: sum(int(s.attrib[k]) for s in suites) for k in ("tests", "errors", "failures", "skipped")}
    if tests != {"tests": 22, "errors": 0, "failures": 0, "skipped": 0}:
        raise ValueError("scoped preparation checks did not pass")
    doc = ROOT / "docs/reviews/fe110_adsorption_control_paired_vasp3_20261020.md"
    paths = [manifest_path, doc, xml, Path(__file__), Path(__file__).with_name("test_prepare.py"),
             DEST / "preparation_receipt.json"]
    receipt_path = DEST / "preparation_receipt_v2.json"
    write_json_exclusive(receipt_path, {
        "status": "SIX_PAIRED_VASP_INPUTS_PREPARED_NOT_SUBMITTED",
        "jobs": 6, "pairs": 3, "standard_preflight_passes": 6, "tests": tests,
        "new_VASP": 0, "new_GPU": 0, "uploaded": False, "execution_authorized": False,
        "remaining": "Separate submission authorization,current gate and live remote POTCAR/input recheck.",
        "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in paths],
    })
    parent = load_json_object(ROOT / "modules/state_handoff/events" / (parent_id + ".json"))
    now = datetime.now(timezone.utc).isoformat()
    event_id = "task-fe110-adsorption-control-paired-vasp3-prepared-20261020"
    event = {
        "schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": parent["entity"],
        "summary": "Prepared three original/control VASP relaxation pairs from reviewed seed outputs;6/6preflights pass.No upload/submission or speedup claim.",
        "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                      "authority": "repository_document", "observed_at": now}
                     for p in (doc, receipt_path, manifest_path, xml)],
        "review": {"required": False, "reason_codes": [], "status": "not_required"},
        "supersedes": [parent_id],
        "payload": {
            "objective": "Prepare a matched three-pair VASP steps/time benchmark without changing the production model or submitting calculations.",
            "phase": "verification",
            "current_evidence": [
                "Six reviewed seed-origin final POSCARs:06_C/09_C/10_A x original AQCat25/frozen uniform-control;no minimum-drift starts.",
                "Canonical routine-production builder,32ranks/job,32/node,ALGO Fast,SIGMA0.20,EDIFFG-0.02,NSW300;within-pair method/resource files byte-identical.",
                "6/6unified adsorption preflights pass;source/return/POSCAR hashes,cell/order/fixedFe0-17 and final graph checked;22related tests pass.",
                "06_C transient C-O elongation/site difference and09_C mixed geometry warning retained;not automatic same-basin acceptance.",
                "All inputs local only,no job IDs,no upload,newVASP0,newGPU0;POTCAR still needs fresh remote verification.",
                "Historical131/101/114steps are not exact matched controls;VASP savings unmeasured.No checkpoint promotion.",
            ],
            "one_executable_step": "Obtain separate explicit authority for the exact six prepared VASP inputs before generating a current submission gate and checking remote POTCAR/duplicates.",
            "submission_boundary": "PREPARED_LOCAL_ONLY:execution_authorized=false;ALLOWED_ACTIONS=[];no upload or submission authorized.",
            "done_when": [
                "Explicit exact-six-job submission authorization,current hash-bound gate and live remote input/POTCAR checks exist before execution.",
                "Each run is reviewed for termination,electronic/force convergence,chemical identity and final adsorption basin.",
                "Only compatible same-minimum pairs compare ionic/SCF work,time,CPU/GPU and declared shared costs before a speedup claim.",
            ],
            "constraints": parent["payload"]["constraints"] + [
                "No automaticpilot/retry or model reselection;no unrelated11-15task changes.",
                "Six simultaneous jobs would require192ranks;concurrency and real runtime remain unapproved/unmeasured.",
            ],
            "authoritative_references": ["configs/true_fe110_production.yaml", "configs/execution_backends.yaml",
                doc.relative_to(ROOT).as_posix(), manifest_path.relative_to(ROOT).as_posix(), receipt_path.relative_to(ROOT).as_posix()],
        },
    }
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print(json.dumps({"status": "SIX_PAIRED_VASP_INPUTS_PREPARED_NOT_SUBMITTED", "tests": tests,
                      "event": target.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    main()
