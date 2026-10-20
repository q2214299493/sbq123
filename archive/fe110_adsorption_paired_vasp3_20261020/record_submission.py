"""Record six successful submissions and job-only registry receipt."""
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from archive.fe110_adsorption_paired_vasp3_20261020.prepare import DEST, ROOT
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry


def main():
    summary_path = DEST / "submission_summary.json"
    summary = load_json_object(summary_path)
    registry_path = DEST / "submission_registry_receipt.json"
    registry = load_json_object(registry_path)
    if registry["inserted"] != 96 or registry["updated"] != 0 or len(summary["records"]) != 6:
        raise ValueError("submission/registration scope changed")
    suites = ET.parse(DEST / "scheduler_stage_regression_tests.xml").getroot().findall("testsuite")
    tests = {k: sum(int(s.attrib[k]) for s in suites) for k in ("tests", "errors", "failures", "skipped")}
    if tests != {"tests": 122, "errors": 0, "failures": 0, "skipped": 0}:
        raise ValueError("scheduler-stage regression tests did not pass")
    batch = load_json_object(DEST / "submission_registry_batch.json")
    counts = {}
    with open_registry(ROOT / "data/project_registry.sqlite3") as connection:
        for table, key in (("calculations", "calculation_id"), ("jobs", "job_record_id"), ("files", "file_id")):
            expected = batch["rows"][table]
            counts[table] = sum(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {key}=?", (row[key],)).fetchone()[0] for row in expected)
            if counts[table] != len(expected):
                raise ValueError("registered row missing")
        for row in batch["rows"]["job_status_history"]:
            found = connection.execute("SELECT scheduler_status,scientific_status FROM job_status_history WHERE job_record_id=?", (row["job_record_id"],)).fetchall()
            if len(found) != 1 or tuple(found[0]) != (row["scheduler_status"], "Not assessed"):
                raise ValueError("initial job state mismatch")
        for row in batch["rows"]["calculations"]:
            if connection.execute("SELECT COUNT(*) FROM results WHERE calculation_id=?", (row["calculation_id"],)).fetchone()[0]:
                raise ValueError("unexpected scientific result record")
    parent_id = "task-fe110-adsorption-control-paired-vasp3-prepared-20261020"
    projected = load_json_object(ROOT / "data/state_handoff/projection_manifest.json")
    if projected["projections"]["tasks/current_task.md#current_task"]["source_event_id"] != parent_id:
        raise ValueError("task changed concurrently;do not supersede")
    parent = load_json_object(ROOT / "modules/state_handoff/events" / (parent_id + ".json"))
    doc = ROOT / "docs/reviews/fe110_adsorption_control_paired_vasp3_submission_20261020.md"
    now = datetime.now(timezone.utc).isoformat()
    event_id = "task-fe110-adsorption-control-paired-vasp3-submitted-20261020"
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": parent["entity"],
        "summary": "User-authorized six paired VASP relaxations submitted and job/input provenance registered;initial2RUN/4PEND.No convergence or speedup claim.",
        "evidence": [{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p),
                      "authority": "repository_document", "observed_at": now}
                     for p in (doc, summary_path, registry_path, DEST / "scheduler_stage_regression_tests.xml")],
        "review": {"required": False, "reason_codes": [], "status": "not_required"}, "supersedes": [parent_id],
        "payload": {
            "objective": "Complete the authorized three-pair VASP relaxation benchmark and compare compatible same-minimum cost,without model promotion.",
            "phase": "active", "current_evidence": [
                "User explicitly authorized exact six prepared jobs;all source/bundle hashes and remote POTCAR family/order/SHA passed;canonical SUBMIT_VASP gates and executor used.",
                "06_C baseline9910781/control9910783 RUN;09_C baseline9910785/control9910787 PEND;10_A baseline9910789/control9910791 PEND at2026-10-20T07:13:59Z.",
                "Each32MPIranks,32/node,NSW300,unchangedproductionALGO Fast/SIGMA0.20/EDIFFG-0.02;existing128rankaccountquota respected.No pilot or old-job cancellation.",
                "Six immutable submission receipts and scheduler raw/hash evidence;registry96newjob/input rows(6calculations+6jobs+6history+78files),zero scientific results.",
                "Scheduler schema gained adsorption_relaxation metadata only;first reporting error did not affect submissions,no resubmit.122related regressions pass.",
                "No electronic/ionic convergence,final basin,elapsedcost or measuredspeedup assessed;no newGPU/training/modelpromotion.",
            ],
            "one_executable_step": "At the next requested checkpoint inspect these six live scheduler/calculation sources;compare convergence and compatible final minima before performance accounting.",
            "submission_boundary": "Exact six submissions consumed.No automaticretry,newVASP,newGPU,parameter/geometrychange,training or modelpromotion authorized.",
            "done_when": [
                "Each of six jobs has terminal scheduler evidence and separately reviewed electronic/force/geometry status.",
                "Compatible same-minimum pairs compare ionicsteps,totalSCFwork,elapsedtime,CPUcorehours and GPU/sharedcost;different minima or failures are not speedup ratios.",
                "Qualified converged adsorption results are registered through owning scientific gates;unqualified cases retain truthful status.",
            ],
            "constraints": ["Freeze both checkpoints and all six submitted inputs;no result-driven checkpoint/epoch reselection.",
                "06_C training-source/site-difference/transientelongation and09_Cmixedgeometry warnings remain;no blanket success.",
                "Old131/101/114-step jobs are not exact matched controls;no speedup claim before final scientific review.",
                "Do not affect other running jobs or11-15preparation;do not bypass accountquota or auto-retry.",
                "Routine checks remain on demand;no recurring monitor was created."],
            "authoritative_references": ["configs/execution_backends.yaml", "configs/true_fe110_production.yaml",
                doc.relative_to(ROOT).as_posix(), summary_path.relative_to(ROOT).as_posix(), registry_path.relative_to(ROOT).as_posix()]}}
    path = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(path, event)
    print(json.dumps({"event": path.relative_to(ROOT).as_posix(), "verified_registry_counts": counts, "tests": tests}))


if __name__ == "__main__":
    main()
