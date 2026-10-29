"""Final live readback and append-only provenance for the explicit NSW300 amendment."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re

from archive.fe110_scratch512_20261028.register_c2_dft import local_file
from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.registry_write import plan_registry_batch
from scripts.state_manager.job_lifecycle import JOB_ALIASES
from .adjust_nsw300 import BASE, LIVE, OUT, REMOTE_COMMON, remote


def snapshot():
    amended = load_json_object(OUT / "pending_authorized_plan.json")["jobs"]
    continued = load_json_object(OUT / "continuation_submitted.json")["jobs"]
    jobs = sorted(amended + continued, key=lambda j: j["name"])
    program = "JOBS=" + repr(jobs) + "\nimport re\n" + REMOTE_COMMON + r'''
status,text=states();out=[]
for job in JOBS:
 p=folder(job)
 for n,d in job['new_files'].items():assert digest(p/n)==d,(job['name'],n)
 assert re.search(r'^NSW\s*=\s*300\s*$',(p/'INCAR').read_text(),re.M)
 header=None
 if (p/'OUTCAR').exists():
  with (p/'OUTCAR').open('rb') as f:head=f.read(50000).decode(errors='replace')
  match=re.search(r'\bNSW\s*=\s*(\d+)',head)
  header=int(match.group(1)) if match else None
  assert header in [None,300],(job['name'],header)
 out.append({'name':job['name'],'job_id':job['job_id'],'remote_dir':job['remote_dir'],'status':status[job['job_id']],'NSW':300,'runtime_OUTCAR_NSW':header,'verified_input_files':len(job['new_files'])})
print(json.dumps({'records':out,'scheduler_stdout':text,'all_current_input_hashes_verified':True}),flush=True)
'''
    result, raw = remote(program, "final_nsw300_verification")
    if any(r["status"] not in {"PEND", "RUN", "DONE"} for r in result["records"]):
        raise ValueError("unexpected active job state")
    write_json_exclusive(OUT / "final_status.json", {**result, "checked_at": raw["checked_at"], "jobs": jobs,
        "source_files": source_file_manifest([OUT / "pending_amendment_receipt.json", OUT / "continuation_submitted.json", OUT / "stopped_collection_success.json"])})
    print({"NSW300_verified": len(jobs), "retained_job_ids": 13, "continuation_job_ids": {j["name"]:j["job_id"] for j in continued},
        "runtime_header_NSW": {r["name"]:r["runtime_OUTCAR_NSW"] for r in result["records"] if r["runtime_OUTCAR_NSW"] is not None}}, flush=True)


def build_batch():
    final = load_json_object(OUT / "final_status.json")
    original = load_json_object(BASE / "dft_submission_complete_v1/registry_batch.json")
    old_jobs = {j["scheduler_job_id"]: j for j in original["rows"]["jobs"]}
    rows = {k: [] for k in ["calculations", "jobs", "job_status_history", "files"]}
    changes = []
    current = {}
    with open_registry(LIVE / "data/project_registry.sqlite3") as connection:
        for job in old_jobs.values():
            current[job["calculation_id"]] = connection.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?",(job["calculation_id"],)).fetchone()[0]
    for job, status in zip(final["jobs"], final["records"], strict=True):
        if job["name"] != status["name"]:
            raise ValueError("final job order changed")
        folder = Path(job["new_directory"])
        continued = "previous_job_id" in job
        old = old_jobs[job.get("previous_job_id", job["job_id"])]
        cid = "fe110_nsw300_20261029_" + job["name"] + "_" + job["job_id"] if continued else old["calculation_id"]
        jid = "job_" + cid if continued else old["job_record_id"]
        workflow = JOB_ALIASES.get(status["status"],status["status"]).lower()
        if continued:
            attempt = load_json_object(folder / "submission_attempt.json")
            receipt = load_json_object(folder / "submission_record.json")
            queue = re.search(r"queue <([^>]+)>",receipt["submit_stdout"])
            if queue is None or receipt["job_id"] != job["job_id"]:
                raise ValueError("native continuation receipt mismatch")
            rows["calculations"].append({"calculation_id":cid,"module":"adsorption_workflow","purpose":"User-requested NSW300 continuation "+job["name"],
                "scientific_system":"true_Fe110_Fe45_C2H3","parent_calculation_id":old["calculation_id"],"workflow_status":workflow,
                "created_at":attempt["created_at_utc"],"source_record":str(OUT/"continuation_plan.json"),"notes":"Reviewed CONTCAR after explicit graceful stop;no accepted scientific result;NSW300/32ranks/EDIFFG-0.02"})
            rows["jobs"].append({"job_record_id":jid,"calculation_id":cid,"scheduler_job_id":job["job_id"],"scheduler":"LSF","server_alias":"sunboquan-codex",
                "queue":queue[1],"remote_directory":job["remote_dir"],"submit_script":"script.lsf","submitted_at":attempt["created_at_utc"]})
            stopped = load_json_object(OUT / "stopped_collection_success.json")
            rows["job_status_history"].append({"job_record_id":old["job_record_id"],"scheduler_status":"DONE","scientific_status":"User-requested graceful stop;not force convergence or an accepted result",
                "checked_at":stopped["checked_at"],"source_command":"ssh sunboquan-codex bjobs -a -w 9927512 9927513","source_text":stopped["scheduler_stdout"],"reviewer":"Codex","notes":"Continuation parent retained;no output overwritten"})
            changes.append({"status_change_id":"nsw300_superseded_"+old["calculation_id"],"calculation_id":old["calculation_id"],
                "expected_workflow_status":current[old["calculation_id"]],"new_workflow_status":"needs_review","changed_at":final["checked_at"],"reviewer":"Codex","reason":"User-requested graceful stop and reviewed NSW300 continuation;not scientific acceptance"})
        elif current[cid] != workflow:
            changes.append({"status_change_id":"nsw300_current_"+cid,"calculation_id":cid,"expected_workflow_status":current[cid],"new_workflow_status":workflow,
                "changed_at":final["checked_at"],"reviewer":"Codex","reason":"Exact live queue observation after NSW300 input amendment"})
        rows["job_status_history"].append({"job_record_id":jid,"scheduler_status":status["status"],"scientific_status":"Not assessed;NSW300 input verified;DFT completion pending",
            "checked_at":final["checked_at"],"source_command":"ssh sunboquan-codex bjobs -a -w "+" ".join(j["job_id"] for j in final["jobs"]),"source_text":final["scheduler_stdout"],"reviewer":"Codex","notes":"No accepted energy,minimum or global magnetic state"})
        for path in sorted(folder.iterdir()):
            if path.is_file():
                row = local_file(path,cid,jid,job["remote_dir"],job["new_files"])
                row["file_id"] = "file_"+cid+"_nsw300_"+path.name.replace(".","_")
                rows["files"].append(row)
        if continued:
            for path in (OUT / "stopped" / job["name"]).iterdir():
                row = local_file(path,old["calculation_id"],old["job_record_id"],old["remote_directory"],[])
                row["file_id"] = "file_"+old["calculation_id"]+"_stopped300_"+path.name.replace(".","_")
                rows["files"].append(row)
        else:
            for filename in ["INCAR","candidate_manifest.json"]:
                rows["files"].append({"file_id":"file_"+cid+"_nsw80_backup_"+filename.replace(".","_"),"calculation_id":cid,"job_record_id":jid,
                    "role":"immutable_previous_input_backup","filename":filename+".before_nsw300_20261029","remote_path":job["remote_dir"]+"/"+filename+".before_nsw300_20261029",
                    "storage_mode":"remote_only","sha256":job["files"][filename],"existence_status":"confirmed","license_or_sensitivity":"project_internal"})
    return {"schema_version":1,"document_kind":"calculation_registry_batch","batch_id":"fe110_11_15_nsw300_20261029_v1",
        "created_at":datetime.now(timezone.utc).isoformat(),"reviewer":"Codex","reason":"Explicit human NSW300 amendment;13same-job inputs and2preserved-progress continuations;metadata only",
        "rows":rows,"workflow_status_changes":changes}


def plan():
    batch = build_batch()
    write_json_exclusive(OUT / "amendment_registry_batch.json",batch)
    checked = plan_registry_batch(LIVE / "data/project_registry.sqlite3",batch)
    write_json_exclusive(OUT / "amendment_registry_plan.json",checked)
    print({"plan_sha256":checked["plan_sha256"],"scope":checked["scope"],"insert_count":checked["insert_count"],"update_count":checked["update_count"],"rows":{k:len(v) for k,v in batch["rows"].items()}},flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["snapshot","plan"])
    args=parser.parse_args()
    {"snapshot":snapshot,"plan":plan}[args.action]()
