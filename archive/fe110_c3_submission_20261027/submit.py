"""Submit one user-authorized C3 continuation through the native executor."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

import yaml

from archive.fe110_grouped_submission_20261025.submit import check_account
from archive.fe110_reico_followup_20261024.collect import save_once
from archive.fe110_reico_sampling93_20261022.submit import POTCARS
from scripts.aqcat25_calibration import parse_poscar_symbols
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
PREP = BASE / "c3_continuation_20261027_v1"
OUTPUT = BASE / "c3_submission_20261027_v1"
NAME = "family_0099_step020_from9922624"
DIRECTORY = OUTPUT / "inputs" / NAME
AUTH = ROOT / "docs/reviews/fe110_c3_submission_20261027/user_authorization.md"
HOST = "sunboquan-codex"
REMOTE = "~/sbq/Fe110/reico_c3_continue_20261027_v1/" + NAME
SOURCE_REMOTE = "~/sbq/Fe110/reico_grouped14_20261025_v1/optimizations/family_0099_step020"
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"
BUNDLE = "aa89bca075e3c6f3218971a4c2c938aadbf36cc35f58646ac10cf071aa794ef8"


def approved_plan():
    plan = load_json_object(PREP / "plan.json")
    if (not source_file_manifest_valid(plan) or plan["bundle_sha256"] != BUNDLE
            or plan["source_job_id"] != "9922624" or plan["cores"] != 32
            or plan["maximum_additional_steps"] != 300 or plan["force_convergence_eV_A"] != .02
            or plan["changes"] != {"NSW": ["80", "300"]} or plan["remote_target"] != REMOTE):
        raise ValueError("only the exact reviewed one-job continuation is authorized")
    if not AUTH.is_file() or "> 提交" not in AUTH.read_text(encoding="utf-8"):
        raise ValueError("human confirmation evidence missing")
    return plan


def remote_precheck(source, digest):
    reader = """import os,subprocess,json,hashlib,re
def command(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=20)
 return {'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
result={'user':command(['whoami']),'account':command(['busers','-w']),'source_job':command(['bjobs','-a','-w','9922624']),'active_jobs':command(['bjobs','-w'])}
result['runtime']={'VASP_executable':os.access(os.path.expanduser('~/soft/vasp541vtst/bin/vasp_std'),os.X_OK),'intel_environment_exists':os.path.isfile('/home_gkx/env/intel/intel2016.sh')}
result['target']={'exists':os.path.lexists(os.path.expanduser(TARGET)),'lock_exists':os.path.lexists(os.path.expanduser(TARGET+'.submission-reservation'))}
data=open(os.path.expanduser(POTCAR),'rb').read()
result['POTCAR']={'sha256':hashlib.sha256(data).hexdigest(),'titles':[v.decode('ascii').strip() for v in re.findall(rb'^\\s*TITEL\\s*=\\s*(.+)$',data,re.M)]}
result['source_hashes']={name:hashlib.sha256(open(os.path.join(os.path.expanduser(SOURCE),name),'rb').read()).hexdigest() for name in ['POSCAR','CONTCAR','INCAR','KPOINTS','OUTCAR','OSZICAR','POTCAR']}
print(json.dumps(result))
"""
    program = "TARGET=" + repr(REMOTE) + "\nPOTCAR=" + repr(source) + "\nSOURCE=" + repr(SOURCE_REMOTE) + "\n" + reader
    save_once(OUTPUT / "remote_reader.json", {"program": program})
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "-o", "ControlMaster=no",
            "-o", "ControlPath=none", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2", HOST, "python3 -"]
    diagnostic = OUTPUT / "phase_diagnostic.json"
    if diagnostic.exists():
        raw = load_json_object(diagnostic)
        raw.update({"checked_at": datetime.fromtimestamp(diagnostic.stat().st_mtime, timezone.utc).isoformat(),
                    "command": argv, "diagnostic_source_sha256": sha256_file(diagnostic)})
    else:
        try:
            process = subprocess.run(argv, input=program, capture_output=True, text=True, encoding="utf-8", timeout=55, check=False)
        except subprocess.TimeoutExpired:
            save_once(OUTPUT / "remote_precheck_timeout.json", {"timeout_seconds": 55, "remote_writes": False})
            raise
        raw = {"checked_at": datetime.now(timezone.utc).isoformat(), "command": argv,
               "returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr}
    save_once(OUTPUT / "remote_precheck_raw.json", raw)
    if raw.get("returncode") != 0:
        raise ValueError("read-only remote precheck failed")
    info = json.loads(raw["stdout"])
    if (info["user"]["stdout"].strip() != "nsgkn_chengdj3" or info["account"]["returncode"]
            or not all(info["runtime"].values()) or any(info["target"].values())):
        raise ValueError("remote user/runtime/account/target precheck failed")
    check_account(info["account"]["stdout"])
    if (info["POTCAR"]["sha256"] != digest
            or [v.split()[1] for v in info["POTCAR"]["titles"]] != ["Fe", "C", "O", "H"]):
        raise ValueError("live POTCAR family/order/hash changed")
    receipt = load_json_object(BASE / "grouped_qc_20261026_v2/collection/family_0099_step020/collection.json")
    if any(info["source_hashes"][n] != receipt["remote"]["files"][n]["sha256"] for n in info["source_hashes"]):
        raise ValueError("remote source differs from reviewed source")
    if not any(line.split()[:3] == ["9922624", "nsgkn_chengdj3", "DONE"] for line in info["source_job"]["stdout"].splitlines()):
        raise ValueError("source job is not DONE")
    save_once(OUTPUT / "remote_precheck.json", info)


def prepare():
    plan = approved_plan()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "ready_for_submission.json").exists() or DIRECTORY.exists():
        raise FileExistsError("preserve existing gate/input state;inspect rather than rebuild")
    source, digest = POTCARS["Fe C O H"]
    remote_precheck(source, digest)
    DIRECTORY.mkdir(parents=True)
    for path in (PREP / "inputs").iterdir():
        if path.name != "submission_preflight.json":
            shutil.copy2(path, DIRECTORY / path.name)
    report = preflight(DIRECTORY, "adsorption_relaxation", write_report=False)
    if not report["passed"] or report["bundle_sha256"] != BUNDLE or report["files"] != plan["input_hashes"]:
        raise ValueError("execution copy differs from reviewed bundle")
    save_once(DIRECTORY / "submission_preflight.json", report)
    validation = {"scope": "reviewed9922624CONTCAR continuation only;not accepted endpoint",
        "structure_sha256": plan["source_CONTCAR_sha256"], "native_geometry_pass": True,
        "scientific_acceptance": False, "source_files": source_file_manifest([PREP / "plan.json",
            PREP / "geometry_review.json", PREP / "independent_input_verification.json", DIRECTORY / "POSCAR"])}
    save_once(DIRECTORY / "submission_geometry_review.json", validation)
    analysis = analyze(DIRECTORY, THRESHOLDS, list(range(45, len(parse_poscar_symbols(DIRECTORY / "POSCAR")))) , write_output=False)
    save_once(DIRECTORY / "submission_no_output_analysis.json", analysis)
    bindings = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in [
        ("analysis", DIRECTORY / "submission_no_output_analysis.json"), ("thresholds", THRESHOLDS),
        ("preflight", DIRECTORY / "submission_preflight.json"), ("validation", DIRECTORY / "submission_geometry_review.json")]}
    kwargs = {"climb": False, "path_reviewed": True, "preflight": report, "validation": validation, "source_bindings": bindings}
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    evidence = decide_execution({}, analysis, thresholds, **kwargs)["EVIDENCE"]
    authorization = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": "SUBMIT_VASP",
        "calculation_kind": "adsorption_relaxation", "authorized_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(AUTH), "sha256": sha256_file(AUTH)}, "target": {"server_alias": HOST, "remote_dir": REMOTE},
        "workdir_identity": workdir_identity(DIRECTORY), "bundle_sha256": BUNDLE,
        "evidence_sha256": execution_evidence_sha256(evidence),
        "potcar": {"source": source, "sha256": digest, "spec_sha256": report["files"]["POTCAR.spec"]}}
    save_once(DIRECTORY / "user_execution_authorization.json", authorization)
    bindings["authorization"] = {"path": str(DIRECTORY / "user_execution_authorization.json"), "sha256": sha256_file(DIRECTORY / "user_execution_authorization.json")}
    decision = decide_execution({}, analysis, thresholds, authorization=authorization, **kwargs)
    save_once(DIRECTORY / "execution_decision.json", decision)
    require_action(DIRECTORY / "execution_decision.json", "SUBMIT_VASP", decision["state_sha256"])
    ready = {"status": "ONE_CANONICAL_GATE_READY", "directory": str(DIRECTORY), "remote_dir": REMOTE,
        "potcar_source": source, "potcar_sha256": digest, "bundle_sha256": BUNDLE,
        "decision_sha256": sha256_file(DIRECTORY / "execution_decision.json"),
        "source_files": source_file_manifest([Path(__file__), AUTH, PREP / "plan.json", OUTPUT / "remote_precheck.json", DIRECTORY / "execution_decision.json"])}
    save_once(OUTPUT / "ready_for_submission.json", ready)
    print({"status": ready["status"], "allowed_actions": decision["ALLOWED_ACTIONS"], "bundle_sha256": BUNDLE}, flush=True)


def execute():
    approved_plan()
    ready = load_json_object(OUTPUT / "ready_for_submission.json")
    if not source_file_manifest_valid(ready) or ready["remote_dir"] != REMOTE:
        raise ValueError("execution binding changed")
    if submission_status(DIRECTORY)["status"] != "NOT_RESERVED":
        raise ValueError("existing attempt;never retry automatically")
    result = submit(DIRECTORY, DIRECTORY / "execution_decision.json", HOST, REMOTE,
                    ready["potcar_source"], ready["potcar_sha256"], "SUBMIT_VASP")
    if (result["status"] != "SUBMITTED" or result["remote_dir"] != REMOTE
            or result["gate_decision_sha256"] != ready["decision_sha256"] or result["bundle_sha256"] != BUNDLE):
        raise ValueError("submission receipt does not match scope")
    save_once(OUTPUT / "submission_summary.json", {"status": "ONE_SUBMITTED", "receipt": result,
        "scientific_outputs_reviewed": False, "training_started": False, "automatic_retry_or_continuation": False,
        "source_files": source_file_manifest([OUTPUT / "ready_for_submission.json", AUTH, DIRECTORY / "submission_record.json"])})
    print({"status": "SUBMITTED", "job_id": result["job_id"], "remote_dir": REMOTE}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "execute"])
    args = parser.parse_args()
    prepare() if args.action == "prepare" else execute()
