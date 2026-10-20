"""Record mixed geometry evidence without promoting a model or submitting DFT."""
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

from .compare import DEST, ROOT


def main():
    report_path = DEST / "geometry_comparison_review_v2.json"
    report = load_json_object(report_path)
    audit = load_json_object(DEST / "trajectory_audit.json")
    prep = load_json_object(DEST / "preparation_receipt.json")
    snapshot = DEST / "review_parser_before_graph_normalization.py"
    if prep["source"]["sha256"] != sha256_file(snapshot):
        raise ValueError("original preparation/analysis source not preserved")
    if report["analysis_source_sha256"] != sha256_file(Path(__file__).with_name("compare.py")):
        raise ValueError("corrected analysis source changed")
    if len(report["geometry"]) != 12 or not all(r["same_graph_as_seed"] and r["same_graph_as_DFT"] for r in report["geometry"]):
        raise ValueError("final graph evidence needs separate review")
    if audit["total_frames"] != 389 or audit["request_sha256"] != report["request_sha256"]:
        raise ValueError("trajectory audit scope changed")
    suites = ET.parse(DEST / "scoped_tests_complete.xml").getroot().findall("testsuite")
    tests = {k: sum(int(s.attrib[k]) for s in suites) for k in ("tests", "errors", "failures", "skipped")}
    if tests != {"tests": 82, "errors": 0, "failures": 0, "skipped": 0}:
        raise ValueError("related software checks did not pass")
    doc = ROOT / "docs/reviews/fe110_adsorption_control_geometry3_20261020.md"
    files = [report_path, DEST / "geometry_comparison_review.json", snapshot, DEST / "trajectory_audit.json",
        DEST / "validation_request.json", DEST / "preparation_receipt.json", DEST / "returned/return_manifest.json",
        DEST / "returned/output/producer_exit_record.json", DEST / "scoped_tests_complete.xml", doc,
        Path(__file__), Path(__file__).with_name("compare.py"), Path(__file__).with_name("trajectory_audit.py")]
    receipt = {"status": "PAIRED_GEOMETRY_DIAGNOSTIC_COMPLETE_MIXED_RESULTS_NO_SPEEDUP_CLAIM", "tests": tests,
        "request_sha256": report["request_sha256"], "optimizer_runs": 12, "trajectory_frames": 389,
        "GPU_executions": 1, "new_VASP": 0, "training_performed": False, "model_promoted": False,
        "retained_warning": "06_C transient C46-O47 elongation;09_C adsorbate RMSD not improved and minimum20-step budget exhausted",
        "analysis_correction": "JSON-list/tuple graph comparison only;original source/report preserved;no GPU rerun",
        "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in files]}
    write_json_exclusive(DEST / "validation_receipt.json", receipt)
    parent_id = "reconciled-task-updated-task-task-current-9fcd2113d1d1cd99bfd5"
    parent = load_json_object(ROOT / "modules/state_handoff/events" / (parent_id + ".json"))
    now = datetime.now(timezone.utc).isoformat()
    event_id = "task-fe110-adsorption-control-geometry3-reviewed-20261020"
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": parent["entity"],
        "summary": "Authorized3-case baseline/control raw-seed/minimum geometry comparison completed.Mixed gains;06_C transient elongation retained.No VASP or promotion.",
        "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p), "authority": "repository_document",
                      "observed_at": now} for p in (doc, DEST / "validation_receipt.json", report_path, DEST / "trajectory_audit.json")],
        "review": {"required": False, "reason_codes": [], "status": "not_required"}, "supersedes": [parent_id],
        "payload": {"objective": "Review completed paired geometry comparison and prepare a matched VASP steps/time benchmark for separate authorization;no default model promotion.",
            "phase": "verification", "current_evidence": [
                "One authorized GPU1 batch:3cases x2models x2origins=12short optimizations,26.54s,producer exit0;no training or VASP.",
                "Exact raw seeds and converged DFT references06_C/09_C/10_A,Fe0-17fixed;seed80steps/MLfmax0.10,minimum20steps/MLfmax0.02.",
                "Seed adsorptionRMSD baseline->control:06_C0.865754->0.435064,09_C0.310857->0.330731,10_A0.297582->0.188551A.Mixed,not blanket improvement.",
                "Candidate minimum drift06_C~0A/0steps,09_C0.091542A/20steps/fmax0.046635 not converged,10_A0.000886A/2steps.",
                "All12 final graphs preserved.389trajectory frames fixed atoms unchanged,max adjacent displacement0.20A;06_C both models transient C46-O47~1.85-1.87A then recover.",
                "JSON list/tuple graph-flag bug corrected in v2local analysis;original report/source retained and no GPU rerun.82related tests pass.",
                "Historical DFT started at older ML outputs,not exact current raw seeds;old131/101/114steps do not prove matched speedup.No default replacement."],
            "one_executable_step": "Prepare/review three baseline/control paired VASP relaxation inputs at the unchanged production branch;only submit with separate explicit authority.",
            "submission_boundary": "GPU_GEOMETRY_COMPARISON_COMPLETE_ONLY:no new VASP,training,relaxation rerun or checkpoint promotion authorized.",
            "done_when": ["Geometry/source/trajectory warnings are retained in the review.",
                "Matched VASP scope/resources/cost receive separate authorization before execution.",
                "Compatible final states,ionic steps,SCF work and total cost are compared before an acceleration claim."],
            "constraints": ["Freeze the candidate;no geometry-test-driven checkpoint/epoch reselection.",
                "06_C is in-domain training-source diagnostic;09_C/10_A are observed after force validation,not fresh blind selection.",
                "Treat06_C transient elongation and09_C mixed results as warnings,not arbitrary hard rejection or blanket success.",
                "Retain other11-15 structure-preparation files/event in backlog;no actions on that branch."],
            "authoritative_references": ["configs/execution_backends.yaml", doc.relative_to(ROOT).as_posix(),
                report_path.relative_to(ROOT).as_posix(), (DEST / "validation_receipt.json").relative_to(ROOT).as_posix()]}}
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print(json.dumps({"status": receipt["status"], "tests": tests, "event": target.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    main()
