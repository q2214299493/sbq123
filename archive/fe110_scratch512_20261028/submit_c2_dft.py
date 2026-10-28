"""Submit only the approved three C2 relaxations through canonical gates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import yaml

from archive.fe110_fixed53_comparison_20261027.prepare import copy_file
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from scripts.execution_backends import load_execution_backends, require_vasp_backend
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from .prepare_c2_dft import ARMS, DEST as PREP

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUTPUT = BASE / "c2_three_arm_submission_20261028_v1"
AUTH = ROOT / "docs/reviews/fe110_c2_three_arm_submission_20261028/user_authorization.md"
HOST = "sunboquan-codex"
REMOTE = "~/sbq/Fe110/adsorption/c2_three_arm_20261028_v1"
PROFILE = ROOT / "configs/true_fe110_production.yaml"
EXPECTED = {("10_A", arm) for arm in ARMS}


def approved_plan():
    plan = load_json_object(PREP / "plan.json")
    checked = load_json_object(PREP / "input_verification.json")
    if (not source_file_manifest_valid(plan) or not source_file_manifest_valid(checked)
            or plan["job_count"] != 3 or [j["arm"] for j in plan["jobs"]] != list(ARMS)
            or checked["core_inputs_hash_verified"] != 18 or not checked["direct_arm_original_bytes_and_no_ML_verified"]):
        raise ValueError("three prepared source bundles or independent review changed")
    budget = plan["budget"]
    if (budget["cores_each"] != 32 or budget["NSW_each"] != 300
            or budget["DFT_force_criterion_eV_A"] != .02 or budget["automatic_retry_or_continuation"] is not False):
        raise ValueError("approved three-arm compute budget changed")
    if "> 提交" not in AUTH.read_text(encoding="utf-8"):
        raise ValueError("current human submission authorization missing")
    for job in plan["jobs"]:
        folder = ROOT / job["path"]
        if folder != PREP / job["arm"] or any(sha256_file(folder / name) != digest for name,digest in job["files"].items()):
            raise ValueError("approved source input bytes changed")
    return {**plan, "jobs": [{**job,"name":"10_A","model":job["arm"]} for job in plan["jobs"]]}


def potcar_bindings():
    path = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/batch_manifest.json"
    bindings = {}
    for job in load_json_object(path)["jobs"]:
        spec = " ".join((ROOT / job["path"] / "POTCAR.spec").read_text(encoding="ascii").split())
        if spec != "Fe C H":
            continue
        value = {"source":job["potcar_source"], "sha256":job["potcar_sha256"]}
        if spec in bindings and bindings[spec] != value:
            raise ValueError("ambiguous approved Fe/C/H POTCAR binding")
        bindings[spec] = value
    if set(bindings) != {"Fe C H"}:
        raise ValueError("reviewed Fe/C/H POTCAR metadata missing")
    return bindings,path


def ssh_read(program, label):
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "-o", "ControlMaster=no", "-o", "ControlPath=none", HOST, "python3 -"]
    result = subprocess.run(argv, input=program, capture_output=True, text=True, encoding="utf-8", timeout=55, check=False)
    raw = {"checked_at": datetime.now(timezone.utc).isoformat(), "command": argv, "returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr, "stdout_sha256": sha256_text(result.stdout)}
    write_json_exclusive(OUTPUT / (label + "_raw.json"), raw)
    if result.returncode:
        raise ValueError("read-only SSH checkpoint failed;inspect " + label)
    return json.loads(result.stdout), raw


def remote_precheck(jobs, pots):
    program = r'''import os,subprocess,json,hashlib,re
def command(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=20)
 return {'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
r={'user':command(['whoami']),'account':command(['busers','-w']),'active_jobs':command(['bjobs','-w'])}
r['runtime']={'VASP_executable':os.access(os.path.expanduser('~/soft/vasp541vtst/bin/vasp_std'),os.X_OK),'intel_environment_exists':os.path.isfile('/home_gkx/env/intel/intel2016.sh')}
r['targets']=[{'remote_dir':d,'exists':os.path.lexists(os.path.expanduser(d)),'lock_exists':os.path.lexists(os.path.expanduser(d+'.submission-reservation'))} for d in TARGETS]
r['POTCARs']={}
for path in SOURCES:
 data=open(os.path.expanduser(path),'rb').read()
 r['POTCARs'][path]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'titles':[v.decode('ascii').strip() for v in re.findall(rb'^\s*TITEL\s*=\s*(.+)$',data,re.M)]}
print(json.dumps(r),flush=True)
'''
    program = "TARGETS=" + repr([j["remote_dir"] for j in jobs]) + "\nSOURCES=" + repr(sorted(p["source"] for p in pots.values())) + "\n" + program
    diagnostic = OUTPUT / "phase_diagnostic_raw.json"
    if diagnostic.exists():
        raw = load_json_object(diagnostic)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(raw["checked_at"])).total_seconds()
        if raw["returncode"] != 0 or sha256_text(raw["stdout"]) != raw["stdout_sha256"] or not 0 <= age < 600:
            raise ValueError("read-only diagnostic receipt is failed,changed or stale")
        info = json.loads(raw["stdout"])
    else:
        write_json_exclusive(OUTPUT / "remote_reader.json", {"program": program})
        info, _ = ssh_read(program, "remote_precheck")
    expected_user = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["vasp"]["user"]
    if (info["user"]["stdout"].strip() != expected_user or info["account"]["returncode"]
            or not all(info["runtime"].values()) or any(t["exists"] or t["lock_exists"] for t in info["targets"])
            or {t["remote_dir"] for t in info["targets"]} != {j["remote_dir"] for j in jobs}):
        raise ValueError("remote user/runtime/account/target check failed")
    table = [line.split() for line in info["account"]["stdout"].splitlines() if line.strip()]
    if len(table) != 2 or "MAX" not in table[0] or int(table[1][table[0].index("MAX")]) != 128:
        raise ValueError("live account128-slot contract changed")
    for spec, pot in pots.items():
        live = info["POTCARs"][pot["source"]]
        if live["sha256"] != pot["sha256"] or [v.split()[1] for v in live["titles"]] != spec.split() or any(not v.startswith("PAW_PBE ") for v in live["titles"]):
            raise ValueError("live POTCAR family/order/hash changed")
    write_json_exclusive(OUTPUT / "remote_precheck.json", info)
    return info


def bind_gate(job):
    folder = Path(job["directory"])
    report = preflight(folder, "adsorption_relaxation", write_report=False)
    if not report["passed"] or report["bundle_sha256"] != job["bundle_sha256"] or report["files"] != job["files"]:
        raise ValueError("copied preflight differs from frozen input bundle")
    write_json_exclusive(folder / "submission_preflight.json", report)
    validation = {"scope": "work-reviewed C2 common origin or frozen ML endpoint;not a scientifically accepted result", "scientific_acceptance": False,
        "source_files": source_file_manifest([PREP / "plan.json", PREP.parent / "ML_results_review.json", PREP / "input_verification.json", folder / "POSCAR"])}
    write_json_exclusive(folder / "submission_geometry_review.json", validation)
    bindings = {key: {"path": str(path), "sha256": sha256_file(path)} for key, path in [
        ("thresholds", PROFILE), ("preflight", folder / "submission_preflight.json"), ("validation", folder / "submission_geometry_review.json")]}
    kwargs = {"climb": False, "path_reviewed": True, "preflight": report, "validation": validation, "source_bindings": bindings}
    thresholds = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    evidence = decide_execution({}, {}, thresholds, **kwargs)["EVIDENCE"]
    authorization = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "SUBMIT_VASP",
        "calculation_kind": "adsorption_relaxation", "authorized_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(AUTH), "sha256": sha256_file(AUTH)}, "target": {"server_alias": HOST, "remote_dir": job["remote_dir"]},
        "workdir_identity": workdir_identity(folder), "bundle_sha256": report["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(evidence), "potcar": {"source": job["potcar_source"], "sha256": job["potcar_sha256"], "spec_sha256": report["files"]["POTCAR.spec"]}}
    write_json_exclusive(folder / "user_execution_authorization.json", authorization)
    bindings["authorization"] = {"path": str(folder / "user_execution_authorization.json"), "sha256": sha256_file(folder / "user_execution_authorization.json")}
    decision = decide_execution({}, {}, thresholds, authorization=authorization, **kwargs)
    write_json_exclusive(folder / "submission_decision.json", decision)
    require_action(folder / "submission_decision.json", "SUBMIT_VASP", decision["state_sha256"])
    return sha256_file(folder / "submission_decision.json")


def prepare():
    plan = approved_plan()
    backend = load_execution_backends().vasp
    require_vasp_backend(HOST, backend.name)
    if (OUTPUT / "inputs").exists() or (OUTPUT / "ready_for_submission.json").exists():
        raise FileExistsError("preserve existing submission inputs or gates")
    OUTPUT.mkdir(exist_ok=True)
    pots, provenance = potcar_bindings()
    jobs = []
    for row in plan["jobs"]:
        folder = OUTPUT / "inputs" / row["name"] / row["model"]
        spec = " ".join((ROOT / row["path"] / "POTCAR.spec").read_text(encoding="ascii").split())
        jobs.append({**row, "directory": str(folder), "remote_dir": REMOTE + "/" + row["name"] + "/" + row["model"],
            "potcar_source": pots[spec]["source"], "potcar_sha256": pots[spec]["sha256"]})
    remote_precheck(jobs, pots)
    for job in jobs:
        for filename in job["files"]:
            copy_file(ROOT / job["path"] / filename, Path(job["directory"]) / filename)
        job["decision_sha256"] = bind_gate(job)
    ready = {"status": "THREE_CANONICAL_GATES_READY", "jobs": jobs,
        "source_plan_sha256": sha256_file(PREP / "plan.json"), "automatic_retry_or_continuation": False,
        "source_files": source_file_manifest([Path(__file__), AUTH, PREP / "plan.json", provenance, OUTPUT / "remote_precheck.json",
            OUTPUT / ("phase_diagnostic_raw.json" if (OUTPUT / "phase_diagnostic_raw.json").exists() else "remote_precheck_raw.json")]
            + [Path(j["directory"]) / "submission_decision.json" for j in jobs])}
    write_json_exclusive(OUTPUT / "ready_for_submission.json", ready)
    print({"status": ready["status"], "gates": len(jobs), "allowed_action": "SUBMIT_VASP"}, flush=True)


def execute():
    approved_plan()
    ready = load_json_object(OUTPUT / "ready_for_submission.json")
    if not source_file_manifest_valid(ready):
        raise ValueError("exact execution binding changed")
    for job in ready["jobs"]:
        folder = Path(job["directory"])
        if submission_status(folder)["status"] != "NOT_RESERVED":
            raise ValueError("prior or ambiguous submission;do not retry")
        decision = load_json_object(folder / "submission_decision.json")
        require_action(folder / "submission_decision.json", "SUBMIT_VASP", decision["state_sha256"])
    for job in ready["jobs"]:
        folder = Path(job["directory"])
        result = submit(folder, folder / "submission_decision.json", HOST, job["remote_dir"], job["potcar_source"], job["potcar_sha256"], "SUBMIT_VASP")
        if result["status"] != "SUBMITTED" or result["bundle_sha256"] != job["bundle_sha256"] or result["gate_decision_sha256"] != job["decision_sha256"]:
            raise ValueError("submission receipt differs from authorized scope")
        print({"name": job["name"], "model": job["model"], "job_id": result["job_id"], "status": result["status"]}, flush=True)
    write_json_exclusive(OUTPUT / "submission_completed.json", {"status": "THREE_SUBMITTED", "jobs": [load_json_object(Path(j["directory"]) / "submission_record.json") for j in ready["jobs"]],
        "new_GPU_or_training": False, "scientific_validity_reviewed": False, "source_files": source_file_manifest([OUTPUT / "ready_for_submission.json", AUTH] + [Path(j["directory"]) / "submission_record.json" for j in ready["jobs"]])})


def snapshot():
    ready = load_json_object(OUTPUT / "ready_for_submission.json")
    receipts = [load_json_object(Path(j["directory"]) / "submission_record.json") for j in ready["jobs"]]
    ids = [r["job_id"] for r in receipts]
    program = "import json,subprocess\nr=subprocess.run(['bjobs','-a','-w']+" + repr(ids) + ",capture_output=True,text=True,timeout=25)\nprint(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}),flush=True)\n"
    result, raw = ssh_read(program, "scheduler_checkpoint")
    if result["returncode"]:
        raise ValueError("scheduler checkpoint failed;do not resubmit")
    records = []
    for job, receipt in zip(ready["jobs"], receipts, strict=True):
        query = {"argv": ["ssh", HOST, "bjobs", "-a", "-w", *ids], **result, "stdout_sha256": sha256_text(result["stdout"])}
        evidence = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "adsorption_relaxation", "scheduler": "LSF", "server_alias": HOST,
            "job_id": receipt["job_id"], "status": _parse_lsf_bjobs(result["stdout"], receipt["job_id"]), "checked_at": raw["checked_at"], "source_command": " ".join(query["argv"]), "query": query}
        validate_stored_lsf_evidence(evidence)
        folder = Path(job["directory"])
        write_json_exclusive(folder / "scheduler_after_submission.json", evidence)
        records.append({"name": job["name"], "model": job["model"], "job_id": receipt["job_id"], "remote_dir": job["remote_dir"], "scheduler_status": evidence["status"], "cores": 32,
            "receipt_sha256": sha256_file(folder / "submission_record.json"), "scheduler_evidence_sha256": sha256_file(folder / "scheduler_after_submission.json"), "scientific_status": "Not assessed"})
    write_json_exclusive(OUTPUT / "submission_summary.json", {"checked_at": raw["checked_at"], "status": "THREE_SUBMITTED", "records": records, "new_VASP_submitted": 3,
        "no_automatic_retry_or_continuation": True, "source_files": source_file_manifest([OUTPUT / "submission_completed.json", OUTPUT / "scheduler_checkpoint_raw.json"] + [Path(j["directory"]) / "scheduler_after_submission.json" for j in ready["jobs"]])})
    print({"checked_at": raw["checked_at"], "records": records}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "execute", "snapshot"])
    args = parser.parse_args()
    {"prepare": prepare, "execute": execute, "snapshot": snapshot}[args.action]()
