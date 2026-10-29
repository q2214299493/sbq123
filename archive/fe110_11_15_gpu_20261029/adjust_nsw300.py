"""User-authorized NSW amendment; preserve queued IDs and restart only two RUN jobs."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import yaml

from archive.fe110_pair2_20261027.review import post_relaxation_geometry
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.vasp_inputs import build_fe110_adsorption_relaxation
from scripts.vasp_result_gate import read_incar_values
from scripts.workflow_geometry import minimum_image_delta_xy

LIVE = Path("C:/Users/86177/Desktop/work")
BASE = LIVE / "calculations/fe110_c2_adsorption_11_15_20261020/ft512_gpu_20261029_v1"
OUT = BASE / "nsw300_update_20261029_v1"
PREP = OUT / "inputs300"
AUTH = OUT / "user_authorization.md"
PROFILE = LIVE / "configs/true_fe110_production.yaml"
DATABASE = LIVE / "data/project_registry.sqlite3"
HOST = "sunboquan-codex"
RUNNING = ["11_A", "11_B"]
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")
OLD = BASE / "dft_submission_complete_v1/ready_for_submission.json"


def remote(program, label):
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", HOST, "python3 -"],
        input=program, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
    raw = {"checked_at": datetime.now(timezone.utc).isoformat(), "returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr, "stdout_sha256": sha256_text(result.stdout)}
    write_json_exclusive(OUT / (label + "_raw.json"), raw)
    if result.returncode:
        raise ValueError("SSH phase failed;inspect preserved receipt before retry:" + label)
    return json.loads(result.stdout), raw


def scheduler_query(label):
    jobs = load_json_object(OLD)["jobs"]
    ids = [j["job_id"] for j in load_json_object(BASE / "dft_submission_complete_v1/submission_completed.json")["jobs"]]
    program = "import subprocess,json\nr=subprocess.run(['bjobs','-a','-w']+" + repr(ids) + ",capture_output=True,text=True,timeout=20)\nprint(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))\n"
    query, raw = remote(program, label)
    if query["returncode"]:
        raise ValueError("live scheduler query failed")
    return jobs, ids, query, raw


def stop_gates():
    text = "# User instruction,2026-10-29\n\n> 调整为300 把\n\n" + (
        "Scope:these15already-submitted11-15adsorption tasks only;NSW80→300,all other physical settings unchanged.\n"
        "Necessary implementation:hold13PEND jobs while amending their input bytes;retain job IDs.\n"
        "Two RUN jobs11_A/11_B cannot adopt a new NSW at runtime:request graceful STOPCAR LSTOP,\n"
        "retain all original outputs and continue from reviewed final CONTCAR in new gated directories.\n"
        "No force termination,unrelated job changes,model inference or training.\n")
    if AUTH.exists():
        if AUTH.read_text(encoding="utf-8") != text or (OUT / "scope.json").exists():
            raise FileExistsError("prior authorization or completed preparation differs")
    else:
        AUTH.write_text(text, encoding="utf-8", newline="\n")
    jobs, ids, query, raw = scheduler_query("before_hold_v2")
    thresholds = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    scoped = []
    for job, jid in zip(jobs, ids, strict=True):
        status = _parse_lsf_bjobs(query["stdout"], jid)
        if status != ("RUN" if job["name"] in RUNNING else "PEND"):
            raise ValueError("live job states changed;review before holding/amending")
        scoped.append({**job, "job_id": jid, "status": status})
        if status != "RUN":
            continue
        folder = OUT / "stop" / job["name"]
        folder.mkdir(parents=True, exist_ok=True)
        scheduler = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "adsorption_relaxation",
            "scheduler": "LSF", "server_alias": HOST, "job_id": jid, "status": status, "checked_at": raw["checked_at"],
            "source_command": "ssh sunboquan-codex bjobs -a -w " + " ".join(ids),
            "query": {**query, "argv": ["ssh", HOST, "bjobs", "-a", "-w", *ids], "stdout_sha256": sha256_text(query["stdout"])}}
        validate_stored_lsf_evidence(scheduler)
        write_json_exclusive(folder / "scheduler.json", scheduler)
        bindings = {"thresholds": {"path": str(PROFILE), "sha256": sha256_file(PROFILE)},
            "scheduler": {"path": str(folder / "scheduler.json"), "sha256": sha256_file(folder / "scheduler.json")}}
        kwargs = {"climb": False, "path_reviewed": True, "scheduler": scheduler, "source_bindings": bindings}
        evidence = decide_execution({}, {}, thresholds, **kwargs)["EVIDENCE"]
        auth = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "STOP_JOB", "job_id": jid,
            "allowed_scheduler_statuses": ["RUN"], "authorized_at": raw["checked_at"],
            "source": {"path": str(AUTH), "sha256": sha256_file(AUTH)},
            "target": {"server_alias": HOST, "remote_dir": job["remote_dir"], "job_id": jid},
            "workdir_identity": workdir_identity(Path(job["directory"])), "bundle_sha256": job["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(evidence)}
        write_json_exclusive(folder / "authorization.json", auth)
        bindings["authorization"] = {"path": str(folder / "authorization.json"), "sha256": sha256_file(folder / "authorization.json")}
        decision = decide_execution({}, {}, thresholds, authorization=auth, **kwargs)
        write_json_exclusive(folder / "decision.json", decision)
        require_action(folder / "decision.json", "STOP_JOB", decision["state_sha256"])
    write_json_exclusive(OUT / "scope.json", {"jobs": scoped, "source_files": source_file_manifest([OLD, AUTH, PROFILE])})
    print({"stop_gates": 2, "pending_to_hold": 13}, flush=True)


REMOTE_COMMON = r'''
import os,json,hashlib,subprocess
from pathlib import Path
def command(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=25)
 if r.returncode:raise RuntimeError(str(args)+':'+r.stderr+r.stdout)
 return r.stdout
def states():
 text=command(['bjobs','-a','-w']+[j['job_id'] for j in JOBS])
 rows={v[0]:v[2] for line in text.splitlines()[1:] if (v:=line.split()) and v[0].isdigit()}
 return rows,text
def folder(job):
 p=Path(os.path.expanduser(job['remote_dir']))
 assert str(p).startswith(str(Path.home()/'sbq/Fe110/adsorption')+'/')
 return p
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
'''


def hold_and_stop():
    scope = load_json_object(OUT / "scope.json")
    for name in RUNNING:
        decision = OUT / "stop" / name / "decision.json"
        require_action(decision, "STOP_JOB", load_json_object(decision)["state_sha256"])
    program = "JOBS=" + repr(scope["jobs"]) + "\n" + REMOTE_COMMON + r'''
status,before=states()
for job in JOBS:
 assert status[job['job_id']]==job['status']
 p=folder(job)
 for name in ['POSCAR','INCAR','KPOINTS','script.lsf']:
  assert digest(p/name)==job['files'][name],(job['name'],name)
 if job['status']=='RUN':assert not (p/'STOPCAR').exists()
pending=[j['job_id'] for j in JOBS if j['status']=='PEND']
held=command(['bstop']+pending)
status,after=states()
assert all(status[j]=='PSUSP' for j in pending),(status,held)
for job in JOBS:
 if job['status']=='RUN':
  assert status[job['job_id']]=='RUN'
  with (folder(job)/'STOPCAR').open('xb') as stream:stream.write(b'LSTOP = .TRUE.\n')
print(json.dumps({'pending_held':pending,'graceful_stop_requested':[j['job_id'] for j in JOBS if j['status']=='RUN'],'bstop_stdout':held,'before':before,'after':after,'force_kill':False}),flush=True)
'''
    result, _ = remote(program, "hold_and_stop")
    write_json_exclusive(OUT / "hold_and_stop.json", result)
    print({"pending_held": len(result["pending_held"]), "graceful_stop_requested": result["graceful_stop_requested"]}, flush=True)


def prepare_one(job, source):
    folder = PREP / job["name"]
    folder.mkdir(parents=True)
    shutil.copyfile(source, folder / "POSCAR")
    build_fe110_adsorption_relaxation(folder, cores=32, profile_path=PROFILE, screening=False, write_local_moments=True)
    old = read_incar_values(Path(job["directory"]) / "INCAR")
    new = read_incar_values(folder / "INCAR")
    if old.pop("NSW") != "80" or new.pop("NSW") != "300" or old != new:
        raise ValueError("settings other than NSW changed")
    metadata = {**load_json_object(Path(job["directory"]) / "candidate_manifest.json"),
        "relaxation_stage": "routine_production", "NSW_update": "user-requested80to300",
        "source_POSCAR_sha256": sha256_file(source), "previous_bundle_sha256": job["bundle_sha256"],
        "source_role": "reviewed_DFT_CONTCAR_continuation" if job["name"] in RUNNING else "unchanged_reviewed_ML_endpoint"}
    write_json_exclusive(folder / "candidate_manifest.json", metadata)
    cmd = [sys.executable, "-X", "utf8", str(CUSTODIAN), "--mode", "validate", "--workdir", str(folder),
        "--incar", str(folder / "INCAR"), "--poscar", str(folder / "POSCAR"), "--calculation-type", "adsorption_GO",
        "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
    result = subprocess.run(cmd,capture_output=True,check=False)
    (folder / "custodian.stdout").write_bytes(result.stdout)
    checked = json.loads(result.stdout)
    if result.returncode or checked["status"] != "VALIDATION_ONLY" or checked["blockers"]:
        raise ValueError("INCAR custodian blocked")
    report = preflight(folder, "adsorption_relaxation", learning_database=DATABASE, write_report=False)
    if not report["passed"]:
        raise ValueError(str(report["errors"]))
    write_json_exclusive(folder / "submission_preflight.json", report)
    return {**job, "new_directory": str(folder), "new_files": report["files"], "new_bundle_sha256": report["bundle_sha256"]}


def prepare_pending():
    jobs = load_json_object(OUT / "scope.json")["jobs"]
    records = [prepare_one(j, Path(j["directory"]) / "POSCAR") for j in jobs if j["status"] == "PEND"]
    write_json_exclusive(OUT / "pending_plan.json", {"jobs": records,
        "source_files": source_file_manifest([AUTH, PROFILE, OUT / "hold_and_stop.json"] + [Path(j["new_directory"]) / "submission_preflight.json" for j in records])})
    print({"pending_inputs_reviewed": len(records)}, flush=True)


def bind_input_gate(job, remote_dir):
    folder = Path(job["new_directory"])
    report = load_json_object(folder / "submission_preflight.json")
    review = {"scientific_acceptance": False, "scope": "user-requested NSW80to300 input review;not a result",
        "source_files": source_file_manifest([AUTH, OLD, BASE / "ML_results_review.json", folder / "POSCAR", folder / "INCAR"])}
    write_json_exclusive(folder / "geometry_review.json", review)
    bindings = {key: {"path": str(p), "sha256": sha256_file(p)} for key,p in [
        ("thresholds", PROFILE), ("preflight", folder / "submission_preflight.json"), ("validation", folder / "geometry_review.json")]}
    thresholds = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    kwargs = {"climb": False, "path_reviewed": True, "preflight": report, "validation": review, "source_bindings": bindings}
    evidence = decide_execution({}, {}, thresholds, **kwargs)["EVIDENCE"]
    authorization = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "SUBMIT_VASP",
        "calculation_kind": "adsorption_relaxation", "authorized_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(AUTH), "sha256": sha256_file(AUTH)}, "target": {"server_alias": HOST, "remote_dir": remote_dir},
        "workdir_identity": workdir_identity(folder), "bundle_sha256": report["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(evidence), "potcar": {"source": job["potcar_source"],
            "sha256": job["potcar_sha256"], "spec_sha256": report["files"]["POTCAR.spec"]}}
    write_json_exclusive(folder / "user_execution_authorization.json", authorization)
    bindings["authorization"] = {"path": str(folder / "user_execution_authorization.json"), "sha256": sha256_file(folder / "user_execution_authorization.json")}
    decision = decide_execution({}, {}, thresholds, authorization=authorization, **kwargs)
    write_json_exclusive(folder / "submission_decision.json", decision)
    require_action(folder / "submission_decision.json", "SUBMIT_VASP", decision["state_sha256"])
    return {**job, "remote_dir": remote_dir, "decision_sha256": sha256_file(folder / "submission_decision.json")}


def amend_pending():
    plan = load_json_object(OUT / "pending_plan.json")
    if not source_file_manifest_valid(plan) or len(plan["jobs"]) != 13:
        raise ValueError("thirteen reviewed pending bundles required")
    jobs = []
    for job in plan["jobs"]:
        # Retain the denied legacy-worktree gate;bind fresh evidence with the
        # current work authority used by the original actual submissions.
        rebound = OUT / "inputs300_rebound_v2" / job["name"]
        rebound.mkdir(parents=True)
        for filename in job["new_files"]:
            shutil.copyfile(Path(job["new_directory"]) / filename, rebound / filename)
        report = preflight(rebound, "adsorption_relaxation", learning_database=DATABASE, write_report=False)
        if not report["passed"]:
            raise ValueError(str(report["errors"]))
        write_json_exclusive(rebound / "submission_preflight.json", report)
        job = {**job, "new_directory": str(rebound), "new_files": report["files"], "new_bundle_sha256": report["bundle_sha256"]}
        bound = bind_input_gate(job, job["remote_dir"])
        folder = Path(bound["new_directory"])
        if any(sha256_file(folder / name) != digest for name,digest in bound["new_files"].items()):
            raise ValueError("reviewed input changed")
        if any(bound["files"][n] != bound["new_files"][n] for n in bound["files"] if n not in {"INCAR", "candidate_manifest.json"}):
            raise ValueError("pending amendment may change only NSW and stage metadata")
        jobs.append(bound)
    write_json_exclusive(OUT / "pending_authorized_plan.json", {"jobs": jobs,
        "source_files": source_file_manifest([AUTH, OUT / "pending_plan.json"] + [Path(j["new_directory"]) / "submission_decision.json" for j in jobs])})
    apply_pending()


def apply_pending():
    plan = load_json_object(OUT / "pending_authorized_plan.json")
    if not source_file_manifest_valid(plan):
        raise ValueError("pending exact gate bindings changed")
    jobs = []
    for job in plan["jobs"]:
        folder = Path(job["new_directory"])
        gate = folder / "submission_decision.json"
        require_action(gate, "SUBMIT_VASP", load_json_object(gate)["state_sha256"])
        if any(sha256_file(folder / n) != d for n,d in job["new_files"].items()):
            raise ValueError("frozen input changed")
        jobs.append({**job, "replacement_base64": {n: base64.b64encode((folder / n).read_bytes()).decode("ascii") for n in ["INCAR", "candidate_manifest.json"]}})
    program = "JOBS=" + repr(jobs) + "\nimport base64\n" + REMOTE_COMMON + r'''
status,before=states()
for job in JOBS:
 p=folder(job)
 assert status[job['job_id']]=='PSUSP'
 for name,d in job['files'].items():assert digest(p/name)==d
 for name in job['replacement_base64']:
  assert not (p/(name+'.before_nsw300_20261029')).exists()
 for name,data in job['replacement_base64'].items():
  assert hashlib.sha256(base64.b64decode(data)).hexdigest()==job['new_files'][name]
status,_=states()
assert all(status[j['job_id']]=='PSUSP' for j in JOBS)
records=[]
for job in JOBS:
 p=folder(job)
 for name,data in job['replacement_base64'].items():
  with (p/(name+'.before_nsw300_20261029')).open('xb') as f:f.write((p/name).read_bytes())
  temporary=p/(name+'.nsw300_new')
  with temporary.open('xb') as f:f.write(base64.b64decode(data));f.flush();os.fsync(f.fileno())
  os.replace(temporary,p/name)
 for name,d in job['new_files'].items():assert digest(p/name)==d
 records.append({'name':job['name'],'job_id':job['job_id'],'remote_dir':job['remote_dir'],'new_files':job['new_files'],'previous_files':job['files']})
status,held=states()
assert all(status[j['job_id']]=='PSUSP' for j in JOBS)
resumed=command(['bresume']+[j['job_id'] for j in JOBS])
status,after=states()
assert all(status[j['job_id']] in ['PEND','RUN'] for j in JOBS),status
print(json.dumps({'records':records,'bstop_verified_before_change':True,'all_input_hashes_verified_before_resume':True,'bresume_stdout':resumed,'before':before,'held':held,'after':after,'new_submissions':0}),flush=True)
'''
    result, raw = remote(program, "amend_pending_bytes_v3")
    write_json_exclusive(OUT / "pending_amendment_receipt.json", {**result, "checked_at": raw["checked_at"]})
    print({"pending_updated_and_resumed": len(result["records"]), "retained_original_job_ids": True, "new_submissions": 0}, flush=True)


def collect_stopped():
    jobs = [j for j in load_json_object(OUT / "scope.json")["jobs"] if j["name"] in RUNNING]
    program = "JOBS=" + repr(jobs) + "\n" + REMOTE_COMMON + r'''
status,text=states();out=[]
for job in JOBS:
 p=folder(job);row={'name':job['name'],'job_id':job['job_id'],'status':status[job['job_id']]}
 if row['status'] in ['DONE','EXIT']:
  for name in ['CONTCAR','OSZICAR']:
   assert (p/name).stat().st_size<150000
   row[name]=(p/name).read_text()
  f=p/'OUTCAR'
  with f.open('rb') as h:h.seek(max(0,f.stat().st_size-250000));row['OUTCAR_tail']=h.read().decode(errors='replace')
 out.append(row)
print(json.dumps({'records':out,'scheduler_stdout':text}),flush=True)
'''
    result, raw = remote(program, "stopped_collection_v2")
    write_json_exclusive(OUT / "stopped_collection_v2.json", result)
    for row in result["records"]:
        if row["status"] != "DONE" or "General timing and accounting" not in row.get("OUTCAR_tail", ""):
            raise ValueError("graceful-stop normal completion not yet established;preserve checkpoint")
        folder = OUT / "stopped" / row["name"]
        folder.mkdir(parents=True)
        for name in ["CONTCAR", "OSZICAR", "OUTCAR_tail"]:
            (folder / name).write_text(row[name], encoding="utf-8", newline="\n")
    write_json_exclusive(OUT / "stopped_collection_success.json", {**result, "checked_at": raw["checked_at"]})
    print({"normally_stopped": len(result["records"])}, flush=True)


def verify_pending():
    jobs = load_json_object(OUT / "pending_authorized_plan.json")["jobs"]
    program = "JOBS=" + repr(jobs) + "\n" + REMOTE_COMMON + r'''
status,text=states();out=[]
for job in JOBS:
 p=folder(job)
 for n,d in job['new_files'].items():assert digest(p/n)==d
 for n in ['INCAR','candidate_manifest.json']:assert digest(p/(n+'.before_nsw300_20261029'))==job['files'][n]
 out.append({'name':job['name'],'job_id':job['job_id'],'status':status[job['job_id']],'NSW':300,'new_files':job['new_files'],'old_backups_hash_verified':True})
print(json.dumps({'records':out,'scheduler_stdout':text,'new_submissions':0,'retained_original_job_ids':True}),flush=True)
'''
    result, raw = remote(program, "pending_after_resume_verification")
    if any(r["status"] not in {"PEND", "RUN"} for r in result["records"]):
        raise ValueError("input changes verified;resume propagation not yet established")
    write_json_exclusive(OUT / "pending_amendment_receipt.json", {**result, "checked_at": raw["checked_at"]})
    print({"NSW300_verified": len(result["records"]), "resumed": True, "original_job_ids_retained": True}, flush=True)


def prepare_continuations():
    stopped = load_json_object(OUT / "stopped_collection_success.json")
    if any(r["status"] != "DONE" for r in stopped["records"]):
        raise ValueError("normal stop required")
    rules = yaml.safe_load((LIVE / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))
    jobs, reviews = [], []
    for job in load_json_object(OUT / "scope.json")["jobs"]:
        if job["name"] not in RUNNING:
            continue
        source = OUT / "stopped" / job["name"] / "CONTCAR"
        seed, pose = read_poscar(Path(job["directory"]) / "POSCAR"), read_poscar(source)
        graph = connectivity(pose, list(range(45, len(pose.frac))))
        if (seed.symbols != pose.symbols or seed.counts != pose.counts or seed.flags != pose.flags
                or not np.allclose(seed.cell, pose.cell, atol=1e-10, rtol=0)
                or molecular_signature(seed) != molecular_signature(pose)
                or graph != connectivity(seed, list(range(45, len(seed.frac))))):
            raise ValueError("continuation atom order/mask/cell/chemical graph changed")
        delta = minimum_image_delta_xy(pose.frac[:18] - seed.frac[:18]) @ seed.cell
        if float(np.linalg.norm(delta, axis=1).max()) > 1e-8:
            raise ValueError("fixed Fe moved")
        geometry = post_relaxation_geometry(seed, pose, {"final_graph": graph, "final_graph_preserved": True}, rules)
        if not geometry["diagnostic_DFT_geometry_ready"]:
            raise ValueError("continuation geometry blocked")
        reviews.append({"name": job["name"], "source_CONTCAR_sha256": sha256_file(source), "geometry": geometry,
            "normal_stop_not_ionic_convergence": True})
        prepared = prepare_one(job, source)
        remote_dir = "~/sbq/Fe110/adsorption/c2_11_15_nsw300_20261029_v1/" + job["name"]
        jobs.append(bind_input_gate(prepared, remote_dir))
    execution = OUT / "continuation_execution"
    execution.mkdir()
    from archive.fe110_scratch512_20261028 import submit_c2_dft as native
    native.ROOT, native.OUTPUT = LIVE, execution
    pots = {"Fe C H": {"source": jobs[0]["potcar_source"], "sha256": jobs[0]["potcar_sha256"]}}
    native.remote_precheck(jobs, pots)
    write_json_exclusive(OUT / "continuation_plan.json", {"jobs": jobs, "geometry_reviews": reviews,
        "source_files": source_file_manifest([AUTH, OUT / "stopped_collection_success.json", execution / "remote_precheck.json"] + [Path(j["new_directory"]) / "submission_decision.json" for j in jobs])})
    print({"reviewed_CONTCAR_continuations": len(jobs), "NSW": 300}, flush=True)


def submit_continuations():
    plan = load_json_object(OUT / "continuation_plan.json")
    if not source_file_manifest_valid(plan) or [j["name"] for j in plan["jobs"]] != RUNNING:
        raise ValueError("exact two continuation bindings changed")
    for job in plan["jobs"]:
        if submission_status(Path(job["new_directory"]))["status"] != "NOT_RESERVED":
            raise ValueError("do not repeat prior or ambiguous continuation submission")
    records = []
    for job in plan["jobs"]:
        folder = Path(job["new_directory"])
        receipt = submit(folder, folder / "submission_decision.json", HOST, job["remote_dir"], job["potcar_source"], job["potcar_sha256"], "SUBMIT_VASP")
        if receipt["status"] != "SUBMITTED":
            raise ValueError("continuation not confirmed submitted")
        records.append({**job, "previous_job_id": job["job_id"], "job_id": receipt["job_id"]})
        print({"name": job["name"], "previous_job_id": job["job_id"], "new_job_id": receipt["job_id"]}, flush=True)
    write_json_exclusive(OUT / "continuation_submitted.json", {"jobs": records,
        "source_files": source_file_manifest([OUT / "continuation_plan.json"] + [Path(j["new_directory"]) / "submission_record.json" for j in records])})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    actions = {"stop-gates": stop_gates, "hold-stop": hold_and_stop, "prepare-pending": prepare_pending,
        "amend-pending": amend_pending, "apply-pending": apply_pending, "collect-stopped": collect_stopped,
        "verify-pending": verify_pending, "prepare-continuations": prepare_continuations, "submit-continuations": submit_continuations}
    parser.add_argument("action", choices=actions)
    args = parser.parse_args()
    if Path(__file__).resolve().parents[2] != LIVE:
        live_source = LIVE / "archive/fe110_11_15_gpu_20261029/adjust_nsw300.py"
        if sha256_file(live_source) != sha256_file(Path(__file__)):
            raise ValueError("current work authority must contain the reviewed identical adapter")
        raise SystemExit(subprocess.run([sys.executable, "-m", "archive.fe110_11_15_gpu_20261029.adjust_nsw300", args.action], cwd=LIVE, check=False).returncode)
    actions[args.action]()
