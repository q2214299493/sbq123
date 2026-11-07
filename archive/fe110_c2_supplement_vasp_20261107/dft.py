"""Latest ten-job scope through existing production builders and canonical gates."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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

from .review import AUTH, OUT, ROOT, SELECTED

PREP = OUT / "dft_inputs"
SUBMISSION = OUT / "dft_submission"
REMOTE = "~/sbq/Fe110/adsorption/c2_site_supplement_20261107_v1"
HOST = "sunboquan-codex"
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")


def configure():
    executor.ROOT, executor.PREP, executor.OUTPUT = ROOT, PREP, SUBMISSION
    executor.AUTH, executor.REMOTE = AUTH, REMOTE


def selection():
    reviewed = load_json_object(OUT / "selection_review.json")
    if not source_file_manifest_valid(reviewed) or [row["name"] for row in reviewed["cases"]] != SELECTED:
        raise ValueError("latest user scope/source review changed")
    if reviewed["skipped_by_latest_user_instruction"] != ["06_S1", "09_S1"]:
        raise ValueError("cancelled candidates entered the scope")
    for row in reviewed["cases"]:
        source = Path(row["selected_for_DFT"])
        if sha256_file(source) != row["selected_POSCAR_sha256"]:
            raise ValueError("selected coordinates changed")
        original = row["name"] == "06_S2"
        if original and (row["source_role"] != "reviewed_original_no_ML" or source != Path(row["original_POSCAR"])):
            raise ValueError("06_S2 must use exact original")
        if not original and (not row["ML_initial_structure_eligible"] or source != Path(row["ML_final_POSCAR"])):
            raise ValueError("unreviewed ML candidate")
    return reviewed["cases"]


def validate_input(folder, row):
    source = Path(row["selected_for_DFT"])
    pose, original = read_poscar(folder / "POSCAR"), read_poscar(Path(row["original_POSCAR"]))
    if (sha256_file(folder / "POSCAR") != sha256_file(source) or pose.symbols != original.symbols
            or pose.counts != original.counts or not np.array_equal(pose.flags, original.flags)
            or not np.allclose(pose.cell, original.cell, atol=1e-10, rtol=0)
            or molecular_signature(pose) != molecular_signature(original)):
        raise ValueError("selected geometry/order/mask/chemistry readback failed")
    report = preflight(folder, "adsorption_relaxation", write_report=False)
    if not report["passed"]:
        raise ValueError("canonical production preflight failed:" + repr(report["errors"]))
    return report


def custodian_check(row):
    folder = PREP / row["name"]
    command = [sys.executable, "-X", "utf8", str(CUSTODIAN), "--mode", "validate", "--workdir", str(folder),
        "--incar", str(folder / "INCAR"), "--poscar", str(folder / "POSCAR"), "--calculation-type", "adsorption_GO",
        "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=90)
    for name, data in (("custodian.stdout", result.stdout), ("custodian.stderr", result.stderr)):
        with (folder / name).open("xb") as handle:
            handle.write(data)
    payload = json.loads(result.stdout)
    if result.returncode or payload["status"] != "VALIDATION_ONLY" or payload["blockers"]:
        raise ValueError("INCAR custodian blocked:" + row["name"])
    return row["name"]


def prepare():
    rows = selection()
    PREP.mkdir()
    jobs = []
    for row in rows:
        folder = PREP / row["name"]
        folder.mkdir()
        shutil.copyfile(row["selected_for_DFT"], folder / "POSCAR")
        settings = build_fe110_adsorption_relaxation(folder, cores=32, screening=False, write_local_moments=True)
        write_json_exclusive(folder / "candidate_manifest.json", {"name": row["name"], "relaxation_stage": "routine_production",
            "write_local_moments": True, "source_role": row["source_role"], "source_POSCAR_sha256": row["selected_POSCAR_sha256"],
            "geometry_review_sha256": sha256_file(OUT / "selection_review.json"),
            "ML_used": row["source_role"] == "ML_pre_relaxed", "accepted_endpoint": False})
        report = validate_input(folder, row)
        jobs.append({"name": row["name"], "path": folder.relative_to(ROOT).as_posix(), "source_path": row["selected_for_DFT"],
                     "source_role": row["source_role"], "files": report["files"], "bundle_sha256": report["bundle_sha256"], "settings": settings})
    with ThreadPoolExecutor(4) as pool:
        checked = list(pool.map(custodian_check, rows))
    write_json_exclusive(PREP / "input_verification.json", {"status": "TEN_INDEPENDENT_READBACKS_PASS", "custodian_pass": checked,
        "source_files": source_file_manifest([Path(job["source_path"]) for job in jobs]
            + [PREP / job["name"] / name for job in jobs for name in job["files"]])})
    write_json_exclusive(PREP / "plan.json", {"job_count": 10, "jobs": jobs,
        "budget": {"cores_each": 32, "NSW_each": 300, "automatic_retry_or_continuation": False},
        "source_files": source_file_manifest([AUTH, OUT / "selection_review.json", PREP / "input_verification.json",
            ROOT / "configs/true_fe110_production.yaml", Path(__file__)])})
    print("PREPARED10:9 ML+06_S2 original;32ranks/NSW300;all native input/custodian checks PASS", flush=True)


def potcars():
    sources = [ROOT / "calculations/fe110_five_c2_adsorption_20261006/vasp_batch_v1/batch_manifest.json",
               ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/batch_manifest.json"]
    pots = {}
    for source in sources:
        document = load_json_object(source)
        for row in document.get("entries", document.get("jobs", [])):
            folder = Path(row["workdir"]) if "workdir" in row else ROOT / row["path"]
            spec = " ".join((folder / "POTCAR.spec").read_text(encoding="ascii").split())
            if spec not in {"Fe O C H", "Fe C O H", "Fe C H"}:
                continue
            value = {"source": row["potcar_source"], "sha256": row["potcar_sha256"]}
            if spec in pots and pots[spec] != value:
                raise ValueError("ambiguous approved POTCAR source")
            pots[spec] = value
    return pots, sources


def gates():
    selection()
    plan = load_json_object(PREP / "plan.json")
    if not source_file_manifest_valid(plan) or plan["job_count"] != 10:
        raise ValueError("prepared input plan changed")
    require_vasp_backend(HOST, load_execution_backends().vasp.name)
    SUBMISSION.mkdir()
    bindings, provenance = potcars()
    jobs = []
    for row in plan["jobs"]:
        spec = " ".join((ROOT / row["path"] / "POTCAR.spec").read_text(encoding="ascii").split())
        jobs.append({**row, "directory": str(SUBMISSION / "inputs" / row["name"]), "remote_dir": REMOTE + "/" + row["name"],
                     "potcar_source": bindings[spec]["source"], "potcar_sha256": bindings[spec]["sha256"]})
    executor.remote_precheck(jobs, bindings)
    for row in jobs:
        folder = Path(row["directory"])
        folder.mkdir(parents=True)
        for name, digest in row["files"].items():
            source = ROOT / row["path"] / name
            if sha256_file(source) != digest:
                raise ValueError("prepared file changed")
            shutil.copyfile(source, folder / name)
        row["decision_sha256"] = executor.bind_gate(row)
    write_json_exclusive(SUBMISSION / "ready_for_submission.json", {"status": "TEN_CANONICAL_GATES_READY", "jobs": jobs,
        "source_files": source_file_manifest([AUTH, PREP / "plan.json", SUBMISSION / "remote_precheck.json", *provenance]
            + [Path(row["directory"]) / "submission_decision.json" for row in jobs])})
    print("10 current hash-bound SUBMIT_VASP gates PASS;remote account/runtime/POTCAR/targets checked", flush=True)


def execute():
    selection()
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    if not source_file_manifest_valid(ready) or [row["name"] for row in ready["jobs"]] != SELECTED:
        raise ValueError("latest exact ten-job scope changed")
    for row in ready["jobs"]:
        folder = Path(row["directory"])
        if submission_status(folder)["status"] != "NOT_RESERVED":
            raise ValueError("prior reservation;inspect before any retry")
        gate = folder / "submission_decision.json"
        require_action(gate, "SUBMIT_VASP", load_json_object(gate)["state_sha256"])
    receipts = []
    for row in ready["jobs"]:
        folder = Path(row["directory"])
        receipt = submit(folder, folder / "submission_decision.json", HOST, row["remote_dir"], row["potcar_source"], row["potcar_sha256"], "SUBMIT_VASP")
        if receipt["status"] != "SUBMITTED" or receipt["bundle_sha256"] != row["bundle_sha256"] or receipt["gate_decision_sha256"] != row["decision_sha256"]:
            raise ValueError("submission receipt mismatch;inspect before retry")
        receipts.append(receipt)
        print(row["name"], receipt["job_id"], receipt["status"], flush=True)
    write_json_exclusive(SUBMISSION / "submission_completed.json", {"status": "TEN_SUBMITTED", "jobs": receipts,
        "source_files": source_file_manifest([AUTH, SUBMISSION / "ready_for_submission.json"]
            + [Path(row["directory"]) / "submission_record.json" for row in ready["jobs"]])})


def snapshot():
    ready = load_json_object(SUBMISSION / "ready_for_submission.json")
    receipts = [load_json_object(Path(row["directory"]) / "submission_record.json") for row in ready["jobs"]]
    ids = [row["job_id"] for row in receipts]
    program = "import json,subprocess\np=subprocess.run(['bjobs','-a','-w']+" + repr(ids) + ",capture_output=True,text=True,timeout=25)\nprint(json.dumps({'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}))\n"
    result, raw = executor.ssh_read(program, "scheduler_checkpoint")
    if result["returncode"]:
        raise ValueError("native scheduler read failed;do not resubmit")
    records = []
    for row, receipt in zip(ready["jobs"], receipts, strict=True):
        query = {"argv": ["ssh", HOST, "bjobs", "-a", "-w", *ids], **result, "stdout_sha256": sha256_text(result["stdout"])}
        evidence = {"schema_version": 1, "document_kind": "scheduler_job_evidence", "stage": "adsorption_relaxation", "scheduler": "LSF",
            "server_alias": HOST, "job_id": receipt["job_id"], "status": _parse_lsf_bjobs(result["stdout"], receipt["job_id"]),
            "checked_at": raw["checked_at"], "source_command": " ".join(query["argv"]), "query": query}
        validate_stored_lsf_evidence(evidence)
        write_json_exclusive(Path(row["directory"]) / "scheduler_after_submission.json", evidence)
        records.append({"name": row["name"], "job_id": receipt["job_id"], "remote_dir": row["remote_dir"], "scheduler_status": evidence["status"],
                        "cores": 32, "NSW": 300, "scientific_status": "Not assessed"})
    write_json_exclusive(SUBMISSION / "submission_summary.json", {"checked_at": raw["checked_at"], "new_VASP_submitted": 10,
        "records": records, "skipped": ["06_S1", "09_S1"], "source_files": source_file_manifest([SUBMISSION / "submission_completed.json",
            SUBMISSION / "scheduler_checkpoint_raw.json"] + [Path(row["directory"]) / "scheduler_after_submission.json" for row in ready["jobs"]])})
    print("INITIAL_SCHEDULER", [(row["name"], row["job_id"], row["scheduler_status"]) for row in records], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("phase", choices=("prepare", "gates", "execute", "snapshot"))
    configure()
    {"prepare": prepare, "gates": gates, "execute": execute, "snapshot": snapshot}[parser.parse_args().phase]()
