"""Twelve reviewed adsorption candidates through existing builders and VASP gates."""
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
from .prepare import BASE, OUTPUT, ROOT

PREP = OUTPUT / "dft300_v2"
SUBMISSION = OUTPUT / "dft_submission_v1"
AUTH = ROOT / "docs/reviews/fe110_c2_16_19_submission_20261102/user_authorization.md"
REMOTE = "~/sbq/Fe110/adsorption/c2_16_19_ft512_20261102_v1"
HOST = "sunboquan-codex"
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")


def configure():
    executor.ROOT, executor.PREP, executor.OUTPUT = ROOT, PREP, SUBMISSION
    executor.AUTH, executor.REMOTE = AUTH, REMOTE


def selected_cases():
    review = load_json_object(OUTPUT / "ML_results_review.json")
    if not source_file_manifest_valid(review) or [r["name"] for r in review["cases"]] != NAMES or review["duplicates"]:
        raise ValueError("source review or twelve unique selected poses changed")
    if [r["name"] for r in review["cases"] if not r["ML_endpoint_eligible"]] != ["16_B", "18_A"]:
        raise ValueError("fallback scope changed")
    for row in review["cases"]:
        if sha256_file(Path(row["selected_for_DFT"])) != row["selected_POSCAR_sha256"]:
            raise ValueError("selected coordinates changed")
        if not row["ML_endpoint_eligible"] and row["source_role"] != "reviewed_v2_original_fallback_not_ML_accelerated":
            raise ValueError("unreviewed fallback")
    return review["cases"]


def validate_input(folder, source, name):
    pose, original = read_poscar(folder / "POSCAR"), read_poscar(BASE / "review_ready_v2" / name / "POSCAR")
    if (sha256_file(folder / "POSCAR") != sha256_file(source) or pose.symbols != original.symbols
            or pose.counts != original.counts or not np.allclose(pose.cell, original.cell, atol=1e-10, rtol=0)
            or not np.array_equal(pose.flags, original.flags) or molecular_signature(pose) != molecular_signature(original)):
        raise ValueError("selected coordinate/order/mask/chemistry readback failed")
    values = read_incar_values(folder / "INCAR")
    for key, expected in {"ENCUT": 400, "EDIFFG": -.02, "NSW": 300, "ISPIN": 2, "LORBIT": 11, "SIGMA": .2}.items():
        if float(values[key]) != expected:
            raise ValueError("INCAR readback failed:" + key)
    result = preflight(folder, "adsorption_relaxation", write_report=False)
    if not result["passed"]:
        raise ValueError("canonical input preflight failed")
    return {"name": name, "bundle_sha256": result["bundle_sha256"], "readback": "PASS"}


def prepare_inputs():
    rows = selected_cases()
    PREP.mkdir()
    jobs, checks = [], []
    for row in rows:
        name, source = row["name"], Path(row["selected_for_DFT"])
        folder = PREP / name
        folder.mkdir()
        shutil.copyfile(source, folder / "POSCAR")
        settings = build_fe110_adsorption_relaxation(folder, cores=32, screening=False, write_local_moments=True)
        write_json_exclusive(folder / "candidate_manifest.json", {"name": name, "formula": row["composition"],
            "relaxation_stage": "routine_production", "write_local_moments": True, "source_role": row["source_role"],
            "source_POSCAR_sha256": row["selected_POSCAR_sha256"],
            "model_checkpoint_sha256": load_json_object(OUTPUT / "ML_results_review.json")["model_checkpoint_sha256"],
            "geometry_review_sha256": sha256_file(OUTPUT / "ML_results_review.json"), "accepted_endpoint": False,
            "ML_final_fragments": row["post_relaxation_geometry_review"]["fragment_formulas_from_connectivity"],
            "ML_caption_scope": "Use actual fragment formulas;the inherited C3-specific diagnostic sentence does not name these C2 species."})
        args = [sys.executable, "-X", "utf8", str(CUSTODIAN), "--mode", "validate", "--workdir", str(folder),
            "--incar", str(folder / "INCAR"), "--poscar", str(folder / "POSCAR"), "--calculation-type", "adsorption_GO",
            "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
        result = subprocess.run(args, cwd=ROOT, capture_output=True, check=False)
        (folder / "custodian.stdout").write_bytes(result.stdout)
        (folder / "custodian.stderr").write_bytes(result.stderr)
        custodian = json.loads(result.stdout)
        if result.returncode or custodian["status"] != "VALIDATION_ONLY" or custodian["blockers"]:
            raise ValueError("INCAR custodian blocked: " + name)
        report = preflight(folder, "adsorption_relaxation")
        if not report["passed"]:
            raise ValueError("canonical preflight blocked: " + repr(report["errors"]))
        checks.append(validate_input(folder, source, name))
        jobs.append({"name": name, "path": folder.relative_to(ROOT).as_posix(), "source_path": str(source),
            "files": report["files"], "bundle_sha256": report["bundle_sha256"], "settings": settings})
    write_json_exclusive(PREP / "input_verification.json", {"status": "12_INDEPENDENT_READBACKS_PASS", "checks": checks,
        "source_files": source_file_manifest([Path(j["source_path"]) for j in jobs] + [PREP / j["name"] / f for j in jobs for f in j["files"]])})
    write_json_exclusive(PREP / "plan.json", {"job_count": 12, "status": "INPUTS_REVIEWED_NOT_SUBMITTED", "jobs": jobs,
        "budget": {"cores_each": 32, "NSW_each": 300, "DFT_force_criterion_eV_A": .02, "automatic_retry_or_continuation": False},
        "source_files": source_file_manifest([OUTPUT / "ML_results_review.json", PREP / "input_verification.json", AUTH,
            Path(__file__), ROOT / "configs/true_fe110_production.yaml"] )})
    print("PREPARED12 routine-production inputs;32ranks/NSW300;no submission", flush=True)


def prepare_gates():
    selected_cases()
    plan, checks = load_json_object(PREP / "plan.json"), load_json_object(PREP / "input_verification.json")
    if not source_file_manifest_valid(plan) or not source_file_manifest_valid(checks) or plan["job_count"] != 12:
        raise ValueError("input review changed")
    require_vasp_backend(HOST, load_execution_backends().vasp.name)
    SUBMISSION.mkdir()
    provenance = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/batch_manifest.json"
    pots = {}
    for row in load_json_object(provenance)["jobs"]:
        spec = " ".join((ROOT / row["path"] / "POTCAR.spec").read_text().split())
        if spec in {"Fe C H", "Fe C O H"}:
            value = {"source": row["potcar_source"], "sha256": row["potcar_sha256"]}
            if spec in pots and pots[spec] != value:
                raise ValueError("ambiguous POTCAR provenance")
            pots[spec] = value
    if set(pots) != {"Fe C H", "Fe C O H"}:
        raise ValueError("missing approved POTCAR source")
    jobs = []
    for row in plan["jobs"]:
        spec = " ".join((ROOT / row["path"] / "POTCAR.spec").read_text().split())
        jobs.append({**row, "directory": str(SUBMISSION / "inputs" / row["name"]), "remote_dir": REMOTE + "/" + row["name"],
            "potcar_source": pots[spec]["source"], "potcar_sha256": pots[spec]["sha256"]})
    executor.remote_precheck(jobs, pots)
    for row in jobs:
        folder = Path(row["directory"])
        folder.mkdir(parents=True)
        for filename, digest in row["files"].items():
            source = ROOT / row["path"] / filename
            if sha256_file(source) != digest:
                raise ValueError("frozen input changed")
            shutil.copyfile(source, folder / filename)
        row["decision_sha256"] = executor.bind_gate(row)
    write_json_exclusive(SUBMISSION / "ready_for_submission.json", {"status": "12_CANONICAL_GATES_READY", "jobs": jobs,
        "source_files": source_file_manifest([AUTH, PREP / "plan.json", provenance, SUBMISSION / "remote_precheck.json"] +
            [Path(j["directory"]) / "submission_decision.json" for j in jobs])})
    print("12 current hash-bound SUBMIT_VASP gates pass", flush=True)


def execute():
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    if not source_file_manifest_valid(ready) or [r["name"] for r in ready["jobs"]] != NAMES:
        raise ValueError("exact twelve-job scope changed")
    for row in ready["jobs"]:
        folder = Path(row["directory"])
        if submission_status(folder)["status"] != "NOT_RESERVED":
            raise ValueError("prior/ambiguous reservation; inspect before any submission")
        gate = folder / "submission_decision.json"
        require_action(gate, "SUBMIT_VASP", load_json_object(gate)["state_sha256"])
    for row in ready["jobs"]:
        folder = Path(row["directory"])
        receipt = submit(folder, folder / "submission_decision.json", HOST, row["remote_dir"], row["potcar_source"], row["potcar_sha256"], "SUBMIT_VASP")
        if receipt["status"] != "SUBMITTED" or receipt["bundle_sha256"] != row["bundle_sha256"] or receipt["gate_decision_sha256"] != row["decision_sha256"]:
            raise ValueError("receipt differs from approved inputs;inspect before any retry")
        print(row["name"], receipt["job_id"], receipt["status"], flush=True)
    write_json_exclusive(SUBMISSION / "submission_completed.json", {"status": "12_SUBMITTED", "jobs":
        [load_json_object(Path(j["directory"]) / "submission_record.json") for j in ready["jobs"]],
        "source_files": source_file_manifest([SUBMISSION / "ready_for_submission.json", AUTH] +
            [Path(j["directory"]) / "submission_record.json" for j in ready["jobs"]])})


def snapshot():
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    receipts = [load_json_object(Path(j["directory"]) / "submission_record.json") for j in ready["jobs"]]
    ids = [r["job_id"] for r in receipts]
    program = "import json,subprocess\nr=subprocess.run(['bjobs','-a','-w']+" + repr(ids) + ",capture_output=True,text=True,timeout=25)\nprint(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}),flush=True)\n"
    result, raw = executor.ssh_read(program, "scheduler_checkpoint")
    if result["returncode"]:
        raise ValueError("scheduler checkpoint failed;do not resubmit")
    records = []
    for row, receipt in zip(ready["jobs"], receipts, strict=True):
        query = {"argv": ["ssh", HOST, "bjobs", "-a", "-w", *ids], **result, "stdout_sha256": sha256_text(result["stdout"])}
        evidence = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "adsorption_relaxation", "scheduler": "LSF", "server_alias": HOST,
            "job_id": receipt["job_id"], "status": _parse_lsf_bjobs(result["stdout"], receipt["job_id"]), "checked_at": raw["checked_at"], "source_command": " ".join(query["argv"]), "query": query}
        validate_stored_lsf_evidence(evidence)
        write_json_exclusive(Path(row["directory"]) / "scheduler_after_submission.json", evidence)
        records.append({"name": row["name"], "job_id": receipt["job_id"], "remote_dir": row["remote_dir"], "scheduler_status": evidence["status"], "cores": 32, "NSW": 300, "scientific_status": "Not assessed"})
    write_json_exclusive(SUBMISSION / "submission_summary.json", {"checked_at": raw["checked_at"], "status": "12_SUBMITTED", "records": records, "new_VASP_submitted": 12,
        "source_files": source_file_manifest([SUBMISSION / "submission_completed.json", SUBMISSION / "scheduler_checkpoint_raw.json"] +
            [Path(j["directory"]) / "scheduler_after_submission.json" for j in ready["jobs"]])})
    print("INITIAL_SCHEDULER", [(r["name"], r["job_id"], r["scheduler_status"]) for r in records], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("prepare", "gates", "execute", "snapshot"))
    args = parser.parse_args()
    configure()
    {"prepare": prepare_inputs, "gates": prepare_gates, "execute": execute, "snapshot": snapshot}[args.action]()
