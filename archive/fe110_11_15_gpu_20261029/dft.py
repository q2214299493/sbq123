"""Reviewed fifteen-candidate handoff through existing VASP builders and executor."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

from archive.fe110_scratch512_20261028 import submit_c2_dft as executor
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.artifact_io import load_json_object, sha256_file, sha256_text, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from scripts.execution_backends import load_execution_backends, require_vasp_backend
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.ts_strategy_engine.execution_gate import require_action
from scripts.vasp_inputs import build_fe110_adsorption_relaxation
from scripts.vasp_result_gate import read_incar_values
from .adapter import NAMES
from .prepare import BASE, OUTPUT, QUOTE, ROOT

PREP = OUTPUT / "dft80_v1"
SUBMISSION = OUTPUT / "dft_submission_v1"
AUTH = ROOT / "docs/reviews/fe110_c2_11_15_ft512_20261029/user_authorization.md"
REMOTE = "~/sbq/Fe110/adsorption/c2_11_15_ft512_20261029_v1"
HOST = "sunboquan-codex"
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")


def configure_executor():
    executor.ROOT, executor.PREP, executor.OUTPUT = ROOT, PREP, SUBMISSION
    executor.AUTH, executor.REMOTE = AUTH, REMOTE


def reviewed_cases():
    review = load_json_object(OUTPUT / "ML_results_review.json")
    if (not source_file_manifest_valid(review) or [r["name"] for r in review["cases"]] != NAMES
            or len(review["DFT_representatives"]) != 15 or review["duplicates"]):
        raise ValueError("reviewed fifteen-case scope or source bindings changed")
    for row in review["cases"]:
        if not row["ML_endpoint_eligible"] or sha256_file(Path(row["selected_for_DFT"])) != row["selected_POSCAR_sha256"]:
            raise ValueError("selected geometry changed or was not reviewed")
    return review["DFT_representatives"]


def validate_input(folder, source, original):
    pose, seed = read_poscar(folder / "POSCAR"), read_poscar(original)
    if (sha256_file(folder / "POSCAR") != sha256_file(source)
            or pose.symbols != seed.symbols or pose.counts != seed.counts
            or not np.allclose(pose.cell, seed.cell, atol=1e-10, rtol=0)
            or not np.array_equal(pose.flags, seed.flags)
            or molecular_signature(pose) != molecular_signature(seed)):
        raise ValueError("independent geometry/order/mask/chemistry readback failed")
    incar = read_incar_values(folder / "INCAR")
    for key, value in {"ENCUT": 400, "EDIFFG": -.02, "NSW": 80, "ISPIN": 2, "LORBIT": 11}.items():
        if float(incar[key]) != value:
            raise ValueError("independent INCAR readback failed:" + key)
    report = preflight(folder, "adsorption_relaxation", write_report=False)
    if not report["passed"]:
        raise ValueError("independent canonical preflight failed")
    return {"name": folder.name, "bundle_sha256": report["bundle_sha256"], "readback": "PASS"}


def prepare_inputs():
    rows = reviewed_cases()
    PREP.mkdir()
    jobs, checks = [], []
    try:
        for row in rows:
            name = row["name"]
            source = Path(row["selected_for_DFT"])
            folder = PREP / name
            folder.mkdir()
            shutil.copyfile(source, folder / "POSCAR")
            settings = build_fe110_adsorption_relaxation(folder, cores=32, screening=True, write_local_moments=True)
            write_json_exclusive(folder / "candidate_manifest.json", {
                "name": name, "formula": row["composition"], "relaxation_stage": "screening", "write_local_moments": True,
                "source_role": row["source_role"], "source_POSCAR_sha256": row["selected_POSCAR_sha256"],
                "model_checkpoint_sha256": load_json_object(OUTPUT / "ML_results_review.json")["model_checkpoint_sha256"],
                "geometry_review_sha256": sha256_file(OUTPUT / "ML_results_review.json"), "accepted_endpoint": False})
            command = [sys.executable, "-X", "utf8", str(CUSTODIAN), "--mode", "validate", "--workdir", str(folder),
                "--incar", str(folder / "INCAR"), "--poscar", str(folder / "POSCAR"), "--calculation-type", "adsorption_GO",
                "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            (folder / "custodian.stdout").write_bytes(result.stdout)
            (folder / "custodian.stderr").write_bytes(result.stderr)
            custodian = json.loads(result.stdout)
            if result.returncode or custodian["status"] != "VALIDATION_ONLY" or custodian["blockers"]:
                raise ValueError("INCAR custodian blocked:" + name)
            report = preflight(folder, "adsorption_relaxation")
            if not report["passed"]:
                raise ValueError("canonical preflight blocked:" + repr(report["errors"]))
            checks.append(validate_input(folder, source, BASE / "candidates_v5" / name / "POSCAR"))
            jobs.append({"name": name, "path": folder.relative_to(ROOT).as_posix(), "source_path": str(source),
                "files": report["files"], "bundle_sha256": report["bundle_sha256"], "settings": settings})
        write_json_exclusive(PREP / "input_verification.json", {"status": "15_INDEPENDENT_READBACKS_PASS", "checks": checks,
            "source_files": source_file_manifest([Path(j["source_path"]) for j in jobs] + [PREP / j["name"] / f for j in jobs for f in j["files"]])})
        write_json_exclusive(PREP / "plan.json", {"job_count": 15, "status": "INPUTS_REVIEWED_NOT_SUBMITTED", "jobs": jobs,
            "budget": {"cores_each": 32, "NSW_each": 80, "DFT_force_criterion_eV_A": .02, "automatic_retry_or_continuation": False},
            "source_files": source_file_manifest([OUTPUT / "ML_results_review.json", PREP / "input_verification.json", Path(__file__), ROOT / "configs/true_fe110_production.yaml", ROOT / "configs/adsmind_lite/prescreen_rules.yaml"] )})
    except Exception as exc:
        write_json_exclusive(PREP / "preparation_failure.json", {"error": str(exc), "completed": [j["name"] for j in jobs], "submitted": False})
        raise
    print({"prepared": len(jobs), "independent_readback": len(checks)}, flush=True)


def potcar_bindings():
    provenance = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/batch_manifest.json"
    pots = {}
    for job in load_json_object(provenance)["jobs"]:
        spec = " ".join((ROOT / job["path"] / "POTCAR.spec").read_text(encoding="ascii").split())
        if spec in {"Fe C H", "Fe C O H"}:
            value = {"source": job["potcar_source"], "sha256": job["potcar_sha256"]}
            if spec in pots and pots[spec] != value:
                raise ValueError("ambiguous reviewed POTCAR binding")
            pots[spec] = value
    if set(pots) != {"Fe C H", "Fe C O H"}:
        raise ValueError("reviewed original POTCAR metadata absent")
    program = "SOURCE=" + repr(pots["Fe C O H"]["source"]) + "\nEXPECTED=" + repr(pots["Fe C O H"]["sha256"]) + "\n" + r'''
import os,re,json,hashlib
from pathlib import Path
source=Path(os.path.expanduser(SOURCE));data=source.read_bytes()
assert hashlib.sha256(data).hexdigest()==EXPECTED
ends=[m.end() for m in re.finditer(rb'End of Dataset[^\n]*\n',data)]
assert len(ends)==4 and ends[-1]==len(data)
parts=[data[a:b] for a,b in zip([0]+ends[:-1],ends)]
titles=[re.search(rb'^\s*TITEL\s*=\s*(.+)$',p,re.M).group(1).decode('ascii').strip() for p in parts]
assert [t.split()[1] for t in titles]==['Fe','C','O','H'] and all(t.startswith('PAW_PBE ') for t in titles)
reordered=b''.join(parts[i] for i in [0,2,1,3])
target=source.parent.parent/'Fe_O_C_H'/'POTCAR'
created=False
if target.exists():
 assert target.read_bytes()==reordered
else:
 target.parent.mkdir(exist_ok=True)
 with target.open('xb') as f:f.write(reordered)
 created=True
print(json.dumps({'source':str(target),'sha256':hashlib.sha256(reordered).hexdigest(),'bytes':len(reordered),'created_new':created,'titles':[titles[i] for i in [0,2,1,3]],'licensed_content_retained_on_VASP_host':True}),flush=True)
'''
    order, _ = executor.ssh_read(program, "potcar_order")
    write_json_exclusive(SUBMISSION / "POTCAR_order_provenance.json", {**order, "original_binding": pots["Fe C O H"], "permutation_0based": [0, 2, 1, 3]})
    pots["Fe O C H"] = {"source": order["source"], "sha256": order["sha256"]}
    return pots, provenance


def prepare_gates():
    reviewed_cases()
    plan = load_json_object(PREP / "plan.json")
    checked = load_json_object(PREP / "input_verification.json")
    if not source_file_manifest_valid(plan) or not source_file_manifest_valid(checked) or plan["job_count"] != 15:
        raise ValueError("input plan or independent readback changed")
    require_vasp_backend(HOST, load_execution_backends().vasp.name)
    if QUOTE not in AUTH.read_text(encoding="utf-8"):
        raise ValueError("current explicit user execution instruction absent")
    SUBMISSION.mkdir()
    pots, provenance = potcar_bindings()
    jobs = []
    for row in plan["jobs"]:
        spec = " ".join((ROOT / row["path"] / "POTCAR.spec").read_text(encoding="ascii").split())
        jobs.append({**row, "directory": str(SUBMISSION / "inputs" / row["name"]), "remote_dir": REMOTE + "/" + row["name"],
            "potcar_source": pots[spec]["source"], "potcar_sha256": pots[spec]["sha256"]})
    executor.remote_precheck(jobs, pots)
    for job in jobs:
        folder = Path(job["directory"])
        folder.mkdir(parents=True)
        for filename, digest in job["files"].items():
            source = ROOT / job["path"] / filename
            if sha256_file(source) != digest:
                raise ValueError("frozen input changed")
            shutil.copyfile(source, folder / filename)
        job["decision_sha256"] = executor.bind_gate(job)
    write_json_exclusive(SUBMISSION / "ready_for_submission.json", {"status": "15_CANONICAL_GATES_READY", "jobs": jobs,
        "source_files": source_file_manifest([AUTH, PREP / "plan.json", provenance, SUBMISSION / "remote_precheck.json", SUBMISSION / "POTCAR_order_provenance.json"] + [Path(j["directory"]) / "submission_decision.json" for j in jobs])})
    print({"gates": len(jobs), "allowed_action": "SUBMIT_VASP"}, flush=True)


def execute():
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    if not source_file_manifest_valid(ready):
        raise ValueError("execution source bindings changed")
    for job in ready["jobs"]:
        folder = Path(job["directory"])
        if submission_status(folder)["status"] != "NOT_RESERVED":
            raise ValueError("prior or ambiguous submission; inspect receipt before any action")
        decision = load_json_object(folder / "submission_decision.json")
        require_action(folder / "submission_decision.json", "SUBMIT_VASP", decision["state_sha256"])
    for job in ready["jobs"]:
        folder = Path(job["directory"])
        receipt = submit(folder, folder / "submission_decision.json", HOST, job["remote_dir"], job["potcar_source"], job["potcar_sha256"], "SUBMIT_VASP")
        if receipt["status"] != "SUBMITTED" or receipt["bundle_sha256"] != job["bundle_sha256"] or receipt["gate_decision_sha256"] != job["decision_sha256"]:
            raise ValueError("receipt differs from approved scope")
        print({"name": job["name"], "job_id": receipt["job_id"], "status": receipt["status"]}, flush=True)
    write_json_exclusive(SUBMISSION / "submission_completed.json", {"status": "15_SUBMITTED", "jobs": [load_json_object(Path(j["directory"]) / "submission_record.json") for j in ready["jobs"]],
        "scientific_validity_reviewed": False, "source_files": source_file_manifest([SUBMISSION / "ready_for_submission.json", AUTH] + [Path(j["directory"]) / "submission_record.json" for j in ready["jobs"]])})


def snapshot():
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    receipts = [load_json_object(Path(j["directory"]) / "submission_record.json") for j in ready["jobs"]]
    ids = [r["job_id"] for r in receipts]
    program = "import json,subprocess\nr=subprocess.run(['bjobs','-a','-w']+" + repr(ids) + ",capture_output=True,text=True,timeout=25)\nprint(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}),flush=True)\n"
    result, raw = executor.ssh_read(program, "scheduler_checkpoint")
    if result["returncode"]:
        raise ValueError("scheduler checkpoint failed; do not resubmit")
    records = []
    for job, receipt in zip(ready["jobs"], receipts, strict=True):
        query = {"argv": ["ssh", HOST, "bjobs", "-a", "-w", *ids], **result, "stdout_sha256": sha256_text(result["stdout"])}
        evidence = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "adsorption_relaxation", "scheduler": "LSF", "server_alias": HOST,
            "job_id": receipt["job_id"], "status": _parse_lsf_bjobs(result["stdout"], receipt["job_id"]), "checked_at": raw["checked_at"], "source_command": " ".join(query["argv"]), "query": query}
        validate_stored_lsf_evidence(evidence)
        folder = Path(job["directory"])
        write_json_exclusive(folder / "scheduler_after_submission.json", evidence)
        records.append({"name": job["name"], "model": "finetune", "job_id": receipt["job_id"], "remote_dir": job["remote_dir"], "scheduler_status": evidence["status"], "cores": 32, "scientific_status": "Not assessed"})
    write_json_exclusive(SUBMISSION / "submission_summary.json", {"checked_at": raw["checked_at"], "status": "15_SUBMITTED", "records": records, "new_VASP_submitted": len(records),
        "no_automatic_retry_or_continuation": True, "source_files": source_file_manifest([SUBMISSION / "submission_completed.json", SUBMISSION / "scheduler_checkpoint_raw.json"] + [Path(j["directory"]) / "scheduler_after_submission.json" for j in ready["jobs"]])})
    print({"checked_at": raw["checked_at"], "records": records}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "gates", "execute", "snapshot"])
    args = parser.parse_args()
    configure_executor()
    {"prepare": prepare_inputs, "gates": prepare_gates, "execute": execute, "snapshot": snapshot}[args.action]()
