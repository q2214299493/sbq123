"""Submit exactly the user's14reviewed cases through the canonical executor."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import yaml

from archive.fe110_reico_followup_20261024.collect import save_once
from archive.fe110_reico_sampling93_20261022.submit import POTCARS
from scripts.aqcat25_calibration import parse_poscar_symbols
from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid,
    write_json_exclusive,
)
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "calculations/fe110_reico_pilot300_20261022/grouped_inputs_20261025_v1"
OUTPUT = INPUTS.parent / "grouped_submission_20261025_v1"
AUTH = ROOT / "docs/reviews/fe110_grouped_submission_20261025/user_authorization.md"
REMOTE = "~/sbq/Fe110/reico_grouped14_20261025_v1"
HOST = "sunboquan-codex"
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"


def check_account(table):
    rows = [line.split() for line in table.splitlines() if line.strip()]
    if len(rows) != 2 or "MAX" not in rows[0]:
        raise ValueError("unexpected account resource table")
    limit = int(rows[1][rows[0].index("MAX")])
    if limit != 128:
        raise ValueError("live account limit differs from the128core authorized branch")
    return limit


def cases():
    for path in [INPUTS / "plan.json", INPUTS / "verification.json", INPUTS / "input_binding.json"]:
        if not source_file_manifest_valid(load_json_object(path)):
            raise ValueError("prepared input or review binding changed")
    plan = load_json_object(INPUTS / "plan.json")
    if plan["case_counts"] != {"single_points": 12, "optimizations": 2} or len(plan["cases"]) != 14:
        raise ValueError("only the reviewed12+2case scope is authorized")
    rows = []
    for row in plan["cases"]:
        directory = Path(row["directory"])
        if (directory != INPUTS / row["role"] / row["sample_id"] or row["cores"] != 32
                or any(sha256_file(directory / n) != digest for n, digest in row["input_hashes"].items())):
            raise ValueError("case directory,cores or input bytes changed")
        spec = " ".join((directory / "POTCAR.spec").read_text(encoding="ascii").split())
        source, digest = POTCARS[spec]
        if digest != row["POTCAR_source_sha256"]:
            raise ValueError("approved POTCAR branch changed")
        rows.append({**row, "remote_dir": REMOTE + "/" + row["role"] + "/" + row["sample_id"],
            "potcar_source": source, "potcar_sha256": digest,
            "action": "SUBMIT_DIAGNOSTIC_VASP" if row["kind"] == "diagnostic_static" else "SUBMIT_VASP"})
    if len({r["sample_id"] for r in rows}) != 14:
        raise ValueError("duplicate authorized identity")
    return rows


def remote_precheck(rows):
    path = OUTPUT / "remote_precheck.json"
    if path.exists():
        return load_json_object(path)
    targets = [r["remote_dir"] for r in rows]
    sources = sorted({r["potcar_source"] for r in rows})
    program = """import os,subprocess,json,hashlib,re
def command(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=20)
 return {'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
result={'user':command(['whoami']),'account':command(['busers','-w']),'active_jobs':command(['bjobs','-w'])}
result['runtime']={'VASP_executable':os.access(os.path.expanduser('~/soft/vasp541vtst/bin/vasp_std'),os.X_OK),'intel_environment_exists':os.path.isfile('/home_gkx/env/intel/intel2016.sh')}
result['targets']=[{'remote_dir':d,'exists':os.path.lexists(os.path.expanduser(d)),'lock_exists':os.path.lexists(os.path.expanduser(d+'.submission-reservation'))} for d in TARGETS]
result['POTCARs']={}
for path in SOURCES:
 data=open(os.path.expanduser(path),'rb').read()
 result['POTCARs'][path]={'sha256':hashlib.sha256(data).hexdigest(),'titles':[v.decode('ascii').strip() for v in re.findall(rb'^\\s*TITEL\\s*=\\s*(.+)$',data,re.M)]}
print(json.dumps(result))
"""
    program = "TARGETS=" + repr(targets) + "\nSOURCES=" + repr(sources) + "\n" + program
    reader = OUTPUT / "remote_reader.py"
    reader.write_text(program, encoding="utf-8", newline="\n")
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", HOST, "python3 -"]
    process = subprocess.run(command, input=program, capture_output=True, text=True,
                             encoding="utf-8", timeout=55, check=False)
    raw = {"checked_at": datetime.now(timezone.utc).isoformat(), "command": command,
        "returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
        "reader_sha256": sha256_file(reader)}
    save_once(OUTPUT / "remote_precheck_raw.json", raw)
    if process.returncode:
        raise ValueError("read-only remote precheck failed")
    parsed = json.loads(process.stdout)
    if (parsed["user"]["stdout"].strip() != "nsgkn_chengdj3"
            or parsed["account"]["returncode"] or not all(parsed["runtime"].values())
            or any(r["exists"] or r["lock_exists"] for r in parsed["targets"])):
        raise ValueError("remote user/runtime/account/target checks failed")
    check_account(parsed["account"]["stdout"])
    for row in rows:
        info = parsed["POTCARs"][row["potcar_source"]]
        if (info["sha256"] != row["potcar_sha256"] or
                [v.split()[1] for v in info["titles"]] != row["POTCAR_species_order"]):
            raise ValueError("live POTCAR family/order/hash mismatch")
    save_once(path, parsed)
    return parsed


def prepare_gate(row, thresholds):
    directory = Path(row["directory"])
    if submission_status(directory)["status"] != "NOT_RESERVED":
        raise ValueError("existing reservation;inspect before any submission")
    report = preflight(directory, row["kind"], write_report=False)
    if report != load_json_object(directory / "submission_preflight.json") or not report["passed"]:
        raise ValueError("prepared preflight changed")
    previous = INPUTS.parent / "grouped_supplement_20261025_v1"
    audit_path = previous / "native_geometry_audits" / (row["sample_id"] + ".json")
    if load_json_object(audit_path)["verdict"] != "pass":
        raise ValueError("reviewed native geometry audit failed")
    validation_path = directory / "submission_geometry_review.json"
    validation = {"sample_id": row["sample_id"], "scope": "reviewed exact geometry for authorized label or bounded relaxation;not scientific acceptance",
        "structure_sha256": row["structure_sha256"], "native_geometry_pass": True,
        "scientific_acceptance": False, "source_files": source_file_manifest([
            previous / "verification.json", audit_path, directory / "incar_custodian_validation.json",
            INPUTS / "verification.json", directory / "POSCAR"])}
    save_once(validation_path, validation)
    analysis_path = directory / "submission_no_output_analysis.json"
    adsorbate_indices = list(range(45, len(parse_poscar_symbols(directory / "POSCAR"))))
    analysis = analyze(directory, THRESHOLDS, adsorbate_indices, write_output=False)
    save_once(analysis_path, analysis)
    bindings = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in [
        ("analysis", analysis_path), ("thresholds", THRESHOLDS),
        ("preflight", directory / "submission_preflight.json"), ("validation", validation_path)]}
    kwargs = {"climb": False, "path_reviewed": True, "preflight": report,
              "validation": validation, "source_bindings": bindings}
    evidence = decide_execution({}, analysis, thresholds, **kwargs)["EVIDENCE"]
    auth_path = directory / "user_execution_authorization.json"
    authorization = {"schema_version": 1, "document_kind": "user_execution_authorization",
        "action": row["action"], "calculation_kind": row["kind"],
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(AUTH), "sha256": sha256_file(AUTH)},
        "target": {"server_alias": HOST, "remote_dir": row["remote_dir"]},
        "workdir_identity": workdir_identity(directory), "bundle_sha256": report["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(evidence),
        "potcar": {"source": row["potcar_source"], "sha256": row["potcar_sha256"],
                   "spec_sha256": report["files"]["POTCAR.spec"]}}
    save_once(auth_path, authorization)
    bindings["authorization"] = {"path": str(auth_path), "sha256": sha256_file(auth_path)}
    decision = decide_execution({}, analysis, thresholds, authorization=authorization, **kwargs)
    decision_path = directory / "execution_decision.json"
    save_once(decision_path, decision)
    require_action(decision_path, row["action"], decision["state_sha256"])
    return {**row, "decision_sha256": sha256_file(decision_path)}


def prepare():
    rows = cases()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "ready_for_submission.json").exists():
        raise FileExistsError("ready evidence exists;validate it instead of rebuilding gates")
    remote_precheck(rows)
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    ready = [prepare_gate(row, thresholds) for row in rows]
    save_once(OUTPUT / "ready_for_submission.json", {"cases": ready,
        "source_files": source_file_manifest([Path(__file__), AUTH, INPUTS / "plan.json",
            INPUTS / "verification.json", OUTPUT / "remote_precheck.json",
            *[Path(r["directory"]) / "execution_decision.json" for r in ready]])})
    print("CANONICAL_GATES_READY", len(ready), flush=True)


def execute():
    ready = load_json_object(OUTPUT / "ready_for_submission.json")
    cases()
    if not source_file_manifest_valid(ready):
        raise ValueError("reviewed gate or execution source binding changed")
    records = []
    for row in ready["cases"]:
        directory = Path(row["directory"])
        state = submission_status(directory)
        if state["status"] == "SUBMITTED":
            receipt = state
        elif state["status"] == "NOT_RESERVED":
            try:
                receipt = submit(directory, directory / "execution_decision.json", HOST,
                    row["remote_dir"], row["potcar_source"], row["potcar_sha256"], row["action"])
            except Exception as error:
                write_json_exclusive(OUTPUT / ("submission_error_" + row["sample_id"] + ".json"),
                    {"sample_id": row["sample_id"], "error": str(error),
                     "submission_state": submission_status(directory), "automatic_retry": False})
                raise
        else:
            raise ValueError("uncertain attempt;never retry automatically")
        if (receipt["status"] != "SUBMITTED" or receipt["remote_dir"] != row["remote_dir"]
                or receipt["gate_decision_sha256"] != row["decision_sha256"]):
            raise ValueError("receipt does not match the authorized exact scope")
        records.append({"sample_id": row["sample_id"], "role": row["role"], **receipt})
        print("SUBMITTED", len(records), "/14", row["sample_id"], receipt["job_id"], flush=True)
    save_once(OUTPUT / "submission_summary.json", {"status": "ALL14_SUBMITTED",
        "records": records, "scientific_outputs_reviewed": False,
        "training_started": False, "source_files": source_file_manifest([
            OUTPUT / "ready_for_submission.json", AUTH,
            *[Path(r["directory"]) / "submission_record.json" for r in ready["cases"]]])})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "execute"])
    arguments = parser.parse_args()
    prepare() if arguments.action == "prepare" else execute()
