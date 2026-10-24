"""Record actual resumed submissions, exact scheduler evidence and registry plan."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from archive.fe110_reico_sampling93_20261022 import submit as original
from archive.fe110_reico_sampling93_20261022.submission_review import file_row
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, write_json_exclusive
from scripts.neb_agent.submission import submission_status
from scripts.registry_write import plan_registry_batch
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.state_manager.job_lifecycle import JOB_ALIASES
from .preflight import OUTPUT, ROOT
from .submit import AUTH


def snapshot():
    initial=load_json_object(OUTPUT/"initial_scope.json")
    records=[{"sample_id":r["sample_id"],**submission_status(original.DEST/r["sample_id"])}
             for r in initial["eligible"] if submission_status(original.DEST/r["sample_id"])["status"] == "SUBMITTED"]
    if not records:
        raise ValueError("no native success receipts")
    write_json_exclusive(OUTPUT/"new_submissions_summary.json",{"records":records,"original7preserved":True})
    for row in records:
        if submission_status(original.DEST/row["sample_id"]) != {k:v for k,v in row.items() if k != "sample_id"}:
            raise ValueError("successful native receipt changed")
    argv=["ssh","-n","-o","BatchMode=yes","-o","ConnectTimeout=15",original.HOST,"bjobs","-a",*[r["job_id"] for r in records]]
    response=subprocess.run(argv,capture_output=True,text=True,timeout=60,check=False)
    checked=datetime.now(timezone.utc).isoformat()
    query={"argv":argv,"returncode":response.returncode,"stdout":response.stdout,"stderr":response.stderr,
           "stdout_sha256":sha256_text(response.stdout)}
    if response.returncode:
        write_json_exclusive(OUTPUT/"post_submission_query_failure.json",query)
        raise RuntimeError("new jobs are submitted; scheduler query failed; do not resubmit")
    jobs=[]
    for row in records:
        evidence={"schema_version":1,"document_kind":"scheduler_job_evidence","stage":"vasp_force_label",
            "scheduler":"LSF","server_alias":original.HOST,"job_id":row["job_id"],
            "status":_parse_lsf_bjobs(response.stdout,row["job_id"]),"checked_at":checked,
            "source_command":" ".join(argv),"query":query}
        validate_stored_lsf_evidence(evidence)
        jobs.append({"sample_id":row["sample_id"],"job_id":row["job_id"],"status":evidence["status"]})
    resources_argv=["ssh","-n","-o","BatchMode=yes","-o","ConnectTimeout=15",original.HOST,"busers","-w"]
    resources=subprocess.run(resources_argv,capture_output=True,text=True,timeout=60,check=False)
    resource_query={"argv":resources_argv,"returncode":resources.returncode,"stdout":resources.stdout,"stderr":resources.stderr}
    result={"checked_at":checked,"query":query,"jobs":jobs,"status_counts":dict(Counter(r["status"] for r in jobs)),
            "account_resource_query":resource_query,"scientific_outputs_reviewed":False}
    write_json_exclusive(OUTPUT/"new_scheduler_snapshot.json",result)
    all_records=[]
    unknown=[]
    for ready in original.checked_ready():
        state=submission_status(original.DEST/ready["sample_id"])
        if state["status"] == "SUBMITTED":
            all_records.append({"sample_id":ready["sample_id"],"workdir":str(original.DEST/ready["sample_id"]),**state})
        else:
            unknown.append({"sample_id":ready["sample_id"],"submission_state":state["status"]})
    write_json_exclusive(OUTPUT/"cumulative_submission_checkpoint.json",{"status":"ACTUAL_RECEIPTS_WITH_UNKNOWN_ATTEMPTS_PRESERVED",
        "batch_sha256":original.BATCH_SHA,"records":all_records,"outstanding":unknown,
        "original_workdir_root":str(original.DEST),"existing_DFT_labels_reused":12,
        "new_this_turn":len(records),"all_success_receipts":len(all_records),"original_markers_preserved":True})
    print({"new_success":len(records),"cumulative_success":len(all_records),"remaining_unknown":len(unknown),
           "new_scheduler":result["status_counts"],"account":resource_query})


def registry_plan(submissions_name="new_submissions_summary.json", scheduler_name="new_scheduler_snapshot.json",
                  suffix="", additional_provenance=()):
    submitted=load_json_object(OUTPUT/submissions_name)["records"]
    evidence=load_json_object(OUTPUT/scheduler_name)
    states={r["job_id"]:r["status"] for r in evidence["jobs"]}
    batch={r["sample_id"]:r for r in original.checked_batch()["samples"]}
    rows={"calculations":[],"jobs":[],"job_status_history":[],"files":[]}
    artifacts=["POSCAR","INCAR","KPOINTS","POTCAR.spec","script.lsf","input_profile.json",
        "incar_validation.json","incar_validation_binding.json","label_request.json","submission_preflight.json",
        "submission_geometry_review.json","submission_no_output_analysis.json","user_execution_authorization.json",
        "execution_decision.json","submission_attempt.json","submission_record.json"]
    for receipt in submitted:
        sid=receipt["sample_id"]
        sample=batch[sid]
        directory=Path(receipt.get("workdir",str(original.DEST/sid)))
        state=submission_status(directory)
        if state != {k:v for k,v in receipt.items() if k not in {"sample_id","workdir"}}:
            raise ValueError("exact new receipt changed before registry planning")
        job_id=receipt["job_id"]
        calculation="fe110_reico_labels280_"+sid+"_"+job_id
        job="job_"+calculation
        package=Path(sample["structure_path"]).parents[4].name
        parent={"sampling6_v1":"fe110_reico_sampling6_20261022_v1_",
                "sampling93_v1":"fe110_reico_sampling93_20261022_v1_"}[package]+sample["family_id"]
        attempt=load_json_object(directory/"submission_attempt.json")
        status=states[job_id]
        rows["calculations"].append({"calculation_id":calculation,"module":"adsorption_workflow",
            "purpose":"Authorized remaining original selected random-frame static energy/force/magnetic label",
            "scientific_system":"true_Fe110_Fe45_"+sample["composition"]+"_random_environment",
            "parent_calculation_id":parent,"workflow_status":JOB_ALIASES.get(status,status).lower(),
            "created_at":attempt["created_at_utc"],"source_record":str(directory/"label_request.json"),
            "notes":"partition="+sample["partition"]+";32cores;NSW0;scientific result not reviewed;unknown markers preserved"})
        rows["jobs"].append({"job_record_id":job,"calculation_id":calculation,"scheduler_job_id":job_id,
            "scheduler":"LSF","server_alias":original.HOST,"queue":"Gkn_normal", "remote_directory":receipt["remote_dir"],
            "submit_script":"script.lsf"})
        rows["job_status_history"].append({"job_record_id":job,"scheduler_status":status,
            "scientific_status":"Not reviewed;electronic convergence,raw forces and magnetic moments pending",
            "checked_at":evidence["checked_at"],"source_command":" ".join(evidence["query"]["argv"]),
            "source_text":"\n".join(line for line in evidence["query"]["stdout"].splitlines() if line.split() and line.split()[0] in {"JOBID",job_id})+"\n",
            "reviewer":"Codex","notes":"Scheduler state only;sourceSHA="+sha256_file(OUTPUT/scheduler_name)})
        for name in artifacts:
            rows["files"].append(file_row(directory/name,calculation,job,receipt["remote_dir"],
                "vasp_input" if name in sample["input_hashes"] else "reviewed_submission_provenance"))
    for shared in [OUTPUT/submissions_name,OUTPUT/scheduler_name,OUTPUT/"initial_scope.json",AUTH,*additional_provenance]:
        rows["files"].append(file_row(shared,calculation,job,receipt["remote_dir"],"batch_submission_provenance"))
    manifest={"schema_version":1,"document_kind":"calculation_registry_batch",
        "batch_id":"fe110_reico_remaining_submission_20261024_v1"+suffix,"created_at":datetime.now(timezone.utc).isoformat(),
        "reviewer":"Codex","reason":"Register actual user-authorized remaining original submissions;no scientific results",
        "rows":rows}
    write_json_exclusive(OUTPUT/("registry_batch"+suffix+".json"),manifest)
    plan=plan_registry_batch(ROOT/"data/project_registry.sqlite3",manifest)
    write_json_exclusive(OUTPUT/("registry_plan"+suffix+".json"),plan)
    print({"plan_sha256":plan["plan_sha256"],"inserts":plan["insert_count"],"updates":plan["update_count"],"scope":plan["scope"]})


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("snapshot","registry-plan"))
    args=parser.parse_args()
    {"snapshot":snapshot,"registry-plan":registry_plan}[args.action]()
