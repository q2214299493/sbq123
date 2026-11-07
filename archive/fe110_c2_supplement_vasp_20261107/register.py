"""Canonical registry batches for ten inputs, then native submitted-job evidence."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry
from .dft import PREP, SUBMISSION
from .review import OUT, ROOT, SELECTED

DB = ROOT / "data/project_registry.sqlite3"


def calculation_id(name):
    return "fe110_c2_supplement_20261107_" + name + "_vasp_v1"


def file_row(cid, path, role, tag, *, job_id=None, remote_path=None):
    return {"file_id": cid + "__" + tag, "calculation_id": cid, "job_record_id": job_id, "role": role,
        "filename": path.name, "local_path": str(path), "remote_path": remote_path,
        "storage_mode": "local_and_remote" if remote_path else "local_only", "byte_size": path.stat().st_size,
        "sha256": sha256_file(path), "existence_status": "confirmed", "notes": "Input/prediction/submission provenance;not an accepted energy."}


def prepare(phase):
    now = datetime.now(timezone.utc).isoformat()
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    if [row["name"] for row in ready["jobs"]] != SELECTED:
        raise ValueError("latest ten-job scope differs")
    rows = {key: [] for key in ("calculations", "jobs", "job_status_history", "files")}
    changes = []
    for job in ready["jobs"]:
        name, folder = job["name"], Path(job["directory"])
        cid = calculation_id(name)
        jid = "job_" + cid
        if phase == "inputs":
            rows["calculations"].append({"calculation_id": cid, "module": "adsorption_workflow",
                "parent_calculation_id": "fe110_c2_supplement_mz73_independent_20261107_v1",
                "purpose": "Reviewed non-equivalent C2 adsorption supplement;routine production relaxation",
                "scientific_system": "true_Fe110_Fe45_" + name,
                "workflow_status": "registered", "created_at": now,
                "source_record": str(PREP / "plan.json"),
                "notes": job["source_role"] + ";32ranks/32pernode/NSW300;SIGMA0.20;06_S1/09_S1excluded;no accepted energy or acceleration claim."})
            paths = sorted(path for path in (PREP / name).iterdir() if path.is_file())
            paths += [Path(job["source_path"]), OUT / "selection_review.json", OUT / "return_handoffs" / (name + ".json")]
            for index, path in enumerate(paths):
                rows["files"].append(file_row(cid, path, "reviewed_VASP_input_or_source", f"input_{index:03d}"))
        else:
            receipt = load_json_object(folder / "submission_record.json")
            attempt = load_json_object(folder / "submission_attempt.json")
            evidence = load_json_object(folder / "scheduler_after_submission.json")
            if receipt["status"] != "SUBMITTED" or receipt["bundle_sha256"] != job["bundle_sha256"] or evidence["job_id"] != receipt["job_id"]:
                raise ValueError("submission/source/native status differs")
            queue = re.search(r"queue <([^>]+)>", receipt["submit_stdout"])
            if queue is None:
                raise ValueError("native submission queue missing")
            rows["jobs"].append({"job_record_id": jid, "calculation_id": cid, "scheduler_job_id": receipt["job_id"],
                "scheduler": "LSF", "server_alias": "sunboquan-codex", "queue": queue[1], "remote_directory": job["remote_dir"],
                "submit_script": "script.lsf", "submitted_at": attempt["created_at_utc"]})
            rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": evidence["status"],
                "scientific_status": "Not assessed;electronic/ionic convergence and final chemistry not yet validated",
                "checked_at": evidence["checked_at"], "source_command": evidence["source_command"],
                "source_text": evidence["query"]["stdout"], "reviewer": "Codex", "notes": "Native scheduler status only;not scientific convergence."})
            paths = sorted(path for path in folder.iterdir() if path.is_file())
            for index, path in enumerate(paths):
                remote = job["remote_dir"] + "/" + path.name if path.name in job["files"] else None
                rows["files"].append(file_row(cid, path, "VASP_submission_and_input_evidence", f"submission_{index:03d}", job_id=jid, remote_path=remote))
            potcar_info = load_json_object(SUBMISSION / "remote_precheck.json")["POTCARs"][job["potcar_source"]]
            rows["files"].append({"file_id": cid + "__remote_POTCAR", "calculation_id": cid, "job_record_id": jid,
                "role": "licensed_POTCAR_input", "filename": "POTCAR", "remote_path": job["remote_dir"] + "/POTCAR",
                "storage_mode": "remote_only", "byte_size": potcar_info["bytes"], "sha256": job["potcar_sha256"],
                "existence_status": "confirmed", "notes": "Canonical executor verified remote copied POTCAR;content not copied into Git."})
            changes.append({"status_change_id": cid + "__submitted", "calculation_id": cid,
                "expected_workflow_status": "registered", "new_workflow_status": "submitted", "changed_at": evidence["checked_at"],
                "reviewer": "Codex", "reason": "Current user-authorized canonical VASP submission with exact native job receipt."})
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_c2_supplement_vasp_20261107_" + phase, "created_at": now, "reviewer": "Codex",
        "reason": "Latest user authority:9 intact ML structures+06_S2 original;06_S1/09_S1 excluded;zero scientific results.", "rows": rows}
    if changes:
        batch["workflow_status_changes"] = changes
    write_json_exclusive(OUT / ("registry_" + phase + "_batch.json"), batch)
    print(phase, {key: len(value) for key, value in rows.items()}, "workflow_changes", len(changes), flush=True)


def verify(phase):
    batch = load_json_object(OUT / ("registry_" + phase + "_batch.json"))
    keys = {"calculations": "calculation_id", "jobs": "job_record_id", "files": "file_id"}
    count = 0
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        for table, key in keys.items():
            for row in batch["rows"][table]:
                saved = db.execute("SELECT * FROM " + table + " WHERE " + key + "=?", (row[key],)).fetchone()
                if saved is None or any(saved[field] != value for field, value in row.items()):
                    raise ValueError("registry readback differs:" + table)
                count += 1
        for row in batch["rows"]["job_status_history"]:
            saved = db.execute("SELECT * FROM job_status_history WHERE job_record_id=? AND checked_at=?",
                               (row["job_record_id"], row["checked_at"])).fetchall()
            if len(saved) != 1 or any(saved[0][key] != value for key, value in row.items()):
                raise ValueError("job history readback differs")
            count += 1
        for change in batch.get("workflow_status_changes", []):
            saved = db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?", (change["calculation_id"],)).fetchone()
            if saved[0] != change["new_workflow_status"]:
                raise ValueError("workflow projection differs")
        for name in SELECTED:
            if db.execute("SELECT 1 FROM results WHERE calculation_id=?", (calculation_id(name),)).fetchone():
                raise ValueError("unreviewed job acquired scientific result")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("registry integrity failed")
    write_json_exclusive(OUT / ("registry_" + phase + "_verification.json"), {"status": "PASS", "rows_read_back": count,
        "workflow_changes_verified": len(batch.get("workflow_status_changes", [])), "scientific_results": 0})
    print("VERIFIED", phase, count, "rows;zero scientific results", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("phase", choices=("inputs", "submission"))
    args = parser.parse_args()
    {"prepare": prepare, "verify": verify}[args.action](args.phase)
