"""Submit only the user-authorized three frozen06_C static labels via canonical gates."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import preflight, submission_status, submit
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action

from .prepare import ROOT
from .prepare_06c_boundary import DEST, scan, source_review

ACTION = "SUBMIT_DIAGNOSTIC_VASP"
HOST = "sunboquan-codex"
REMOTE = "~/sbq/Fe110/diagnostics/" + DEST.name
AUTH_SOURCE = Path(__file__).with_name("authorization_submit_06c_20261018.md")
BATCH_SHA = "7830bd801ff8b3c2cdae07eb007a2c1eaf032b11cd437a30d103f3f44fcfe62f"
SAMPLES = ["06C_before_003", "06C_after_004", "06C_final_057"]
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"
REVISION = "v2"


def evidence_path(directory: Path, name: str) -> Path:
    return directory / (name + "_" + REVISION + ".json")


def write_bound_json(path: Path, value: dict) -> dict:
    """Bind the owning writer's saved JSON types, never an in-memory tuple view."""
    write_json_exclusive(path, value)
    return json.loads(path.read_bytes())


def checked_batch() -> dict:
    if sha256_file(DEST / "batch_request.json") != BATCH_SHA:
        raise ValueError("authorized batch bytes changed")
    batch = json.loads((DEST / "batch_request.json").read_bytes())
    if [s["sample_id"] for s in batch["samples"]] != SAMPLES:
        raise ValueError("not the exact authorized three jobs")
    for name, key in (("true_fe110_production.yaml", "input_profile_sha256"), ("execution_backends.yaml", "backend_policy_sha256")):
        if sha256_file(ROOT / "configs" / name) != batch[key]:
            raise ValueError("profile/backend changed;fresh review required")
    if sha256_file(AUTH_SOURCE) != "e7d85b168c046fd4d5b109d60526bf840d200c0e86d83ecedb67f6327ef97a4a":
        raise ValueError("user authority source changed")
    for row in batch["samples"]:
        directory = DEST / row["directory"]
        if row["directory"] != row["sample_id"]:
            raise ValueError("sample path changed")
        if any(sha256_file(directory / name) != digest for name, digest in row["input_hashes"].items()):
            raise ValueError("authorized inputs changed")
    return batch


def remote_check(batch: dict) -> None:
    code = """import hashlib,json,os,getpass,socket
from pathlib import Path
p=Path.home()/'sbq/Fe110/potcars/Fe_C_O_H/POTCAR'
root=Path.home()/'sbq/Fe110/diagnostics/adsorption_06c_boundary_labels_20261018_v1'
print(json.dumps({'hostname':socket.gethostname(),'user':getpass.getuser(),'potcar_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'VASP_executable':os.access(str(Path.home()/'soft/vasp541vtst/bin/vasp_std'),os.X_OK),'intel_environment_exists':Path('/home_gkx/env/intel/intel2016.sh').is_file(),'targets_exist':{name:(root/name).exists() or (root/(name+'.submission-reservation')).exists() for name in ['06C_before_003','06C_after_004','06C_final_057']}}))
"""
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST, "python3 -"],
                            input=code.encode(), capture_output=True, timeout=35, check=False)
    write_json_exclusive(evidence_path(DEST, "remote_presubmission_recheck"), {"exit_code": result.returncode,
        "stdout": result.stdout.decode(errors="replace"), "stderr": result.stderr.decode(errors="replace")})
    if result.returncode:
        raise RuntimeError("remote prerequisite failed;no upload or submission")
    record = json.loads(result.stdout)
    if record["user"] != "nsgkn_chengdj3" or record["potcar_sha256"] != batch["POTCAR"]["sha256"]:
        raise ValueError("remote account/POTCAR mismatch")
    if not record["VASP_executable"] or not record["intel_environment_exists"] or any(record["targets_exist"].values()):
        raise ValueError("runtime unavailable or duplicate remote target")


def prepare() -> None:
    batch = checked_batch()
    if any(submission_status(DEST / row["directory"])["status"] != "NOT_RESERVED" for row in batch["samples"]):
        raise RuntimeError("existing submission state;reconcile receipts,do not retry")
    remote_check(batch)
    _, frames, template, _ = source_review()
    measurements, _ = scan(frames, template)
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    ready = []
    for row in batch["samples"]:
        directory = DEST / row["directory"]
        atoms = read(directory / "POSCAR", format="vasp")
        frame = frames[row["frame_index_0based"]]
        fixed = sorted(int(i) for c in atoms.constraints for i in c.get_indices())
        if (fixed != list(range(18)) or atoms.get_chemical_symbols() != frame.get_chemical_symbols()
                or not np.allclose(atoms.positions, frame.positions, atol=1e-12, rtol=0)
                or not np.allclose(atoms.cell, frame.cell, atol=1e-12, rtol=0)):
            raise ValueError("saved exact source structure changed")
        report = preflight(directory, "diagnostic_static", write_report=False)
        saved = json.loads((directory / "submission_preflight.json").read_bytes())
        if not report["passed"] or report != saved:
            raise ValueError("preflight changed;fresh binding required")
        review = {"document_kind": "adsorption_failure_boundary_submission_review", "sample_id": row["sample_id"],
            "status": "USER_ACCEPTED_FOR_EXACT_FORCE_DIAGNOSIS_ONLY", "source_batch_sha256": BATCH_SHA,
            "structure_sha256": row["structure_sha256"], "measurement": measurements[row["frame_index_0based"]],
            "source_review_sha256": sha256_file(DEST / "selection_review.json"), "stable_adsorption_accepted": False,
            "scope": "three separate static structures;no NEB path or TS acceptance"}
        review = write_bound_json(evidence_path(directory, "submission_geometry_review"), review)
        # No NEB geometry is fabricated: this is the existing scalar diagnostic
        # gate;the measured single-structure review is separately file-bound.
        analysis = analyze(directory, THRESHOLDS, [45, 46, 47, 48], write_output=False)
        analysis = write_bound_json(evidence_path(directory, "submission_no_output_analysis"), analysis)
        bindings = {name: {"path": str(path.resolve()), "sha256": sha256_file(path)} for name, path in (
            ("analysis", evidence_path(directory, "submission_no_output_analysis")), ("thresholds", THRESHOLDS),
            ("preflight", directory / "submission_preflight.json"), ("validation", evidence_path(directory, "submission_geometry_review")))}
        kwargs = dict(climb=False, path_reviewed=True, preflight=report, validation=review, source_bindings=bindings)
        evidence = decide_execution({}, analysis, thresholds, **kwargs)["EVIDENCE"]
        authorization = {"schema_version": 1, "document_kind": "user_execution_authorization", "action": ACTION,
            "calculation_kind": "diagnostic_static", "authorized_at": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(AUTH_SOURCE.resolve()), "sha256": sha256_file(AUTH_SOURCE)},
            "target": {"server_alias": HOST, "remote_dir": REMOTE + "/" + row["sample_id"]},
            "workdir_identity": workdir_identity(directory), "bundle_sha256": report["bundle_sha256"],
            "evidence_sha256": execution_evidence_sha256(evidence), "potcar": {
                "source": batch["POTCAR"]["path"], "sha256": batch["POTCAR"]["sha256"],
                "spec_sha256": report["files"]["POTCAR.spec"]}}
        path = evidence_path(directory, "user_execution_authorization")
        authorization = write_bound_json(path, authorization)
        bindings["authorization"] = {"path": str(path.resolve()), "sha256": sha256_file(path)}
        decision = decide_execution({}, analysis, thresholds, authorization=authorization, **kwargs)
        path = evidence_path(directory, "execution_decision")
        write_json_exclusive(path, decision)
        require_action(path, ACTION, decision["state_sha256"])
        ready.append({"sample_id": row["sample_id"], "decision_sha256": sha256_file(path)})
    write_json_exclusive(evidence_path(DEST, "ready_for_authorized_submission"), {"batch_sha256": BATCH_SHA, "samples": ready})
    print(json.dumps({"status": "THREE_CURRENT_HASH_BOUND_GATES_READY", "samples": ready}))


def submit_batch() -> None:
    batch = checked_batch()
    ready = json.loads(evidence_path(DEST, "ready_for_authorized_submission").read_bytes())
    if ready["batch_sha256"] != BATCH_SHA or [s["sample_id"] for s in ready["samples"]] != SAMPLES:
        raise ValueError("ready scope changed")
    records = []
    for row in ready["samples"]:
        directory = DEST / row["sample_id"]
        decision = evidence_path(directory, "execution_decision")
        if sha256_file(decision) != row["decision_sha256"]:
            raise ValueError("reviewed execution gate changed")
        record = submit(directory, decision, HOST, REMOTE + "/" + row["sample_id"], batch["POTCAR"]["path"], batch["POTCAR"]["sha256"], ACTION)
        records.append({"sample_id": row["sample_id"], **record})
        print(json.dumps({"sample_id": row["sample_id"], "job_id": record["job_id"], "status": record["status"]}), flush=True)
    write_json_exclusive(DEST / "submission_summary.json", {"status": "THREE_SUBMITTED", "records": records,
        "training_performed": False, "GPU_submitted": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "submit"))
    args = parser.parse_args()
    {"prepare": prepare, "submit": submit_batch}[args.action]()
