"""Submit the reviewed C2/C3 fixed-geometry batch once and verify LSF receipts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

import yaml

from archive.fe110_joint_priority_20261117.analyze import BASE, ROOT, guard_hashes
from scripts.artifact_io import load_json_object as load, sha256_file as sha, write_json_exclusive as save
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import InputBundle, _bsub_command, preflight, submission_status, submit
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from .prepare_lsf import ACTION, DEFERRED, POTCAR_SHA, PREPARED, REMOTE_ROOT, SOURCE_SHA

RUN = BASE / "c2_c3_label9_lsf_20261118_v1"
EXEC = RUN / "execution_20261118_v1"
PLAN = RUN / "final_submission_list.json"
PLAN_SHA = "4ac145dc610571030b1738bef87f5b4b6be0190c0ce49104bbf1eea93537b388"
HOST = "sunboquan-codex"
QUEUE = "Gkn_normal"
USER = "nsgkn_chengdj3"
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"
APPROVED = (
    ("family_0073_step006", 135), ("family_0054_step005", 90),
    ("family_0011_step004", 90), ("family_0081_step004", 135),
    ("family_0094_step005", 135), ("family_0078_step005", 135),
    ("family_0056_step006", 135), ("family_0018_step005", 90),
    ("family_0042_step005", 90),
)


def now():
    return datetime.now(timezone.utc).isoformat()


def bind(path):
    return {"path": str(path), "sha256": sha(path)}


def ssh(command):
    argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=8", "--", HOST, command]
    completed = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=25, check=False)
    return {"observed_at_utc": now(), "command": command, "exit_code": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr}


def check_inputs():
    if sha(PLAN) != PLAN_SHA or sha(PREPARED / "review.json") != SOURCE_SHA:
        raise ValueError("Reviewed batch or geometry evidence changed")
    if sha(PREPARED / "remote_POTCAR_hash_check.json") != POTCAR_SHA:
        raise ValueError("Reviewed POTCAR evidence changed")
    batch = load(PLAN)
    rows = batch["jobs"]
    if (tuple((r["id"], r["LSF_limit_minutes"]) for r in rows) != APPROVED
            or [r["original_rank"] for r in rows] != [1, 2, 3, 5, 6, 7, 8, 9, 10]
            or batch["backend"] != HOST or batch["queue_from_canonical_script"] != QUEUE
            or guard_hashes() != batch["frozen_hashes"]):
        raise ValueError("Approved scope or protected files changed")
    excluded = {DEFERRED, *batch["reserve_ids_only"]}
    staged = {p.name for p in (RUN / "vasp_review_inputs").iterdir()}
    if staged != {r["id"] for r in rows} or staged & excluded or len(excluded) != 11:
        raise ValueError("Staged scope differs from the nine authorized points")
    if sum(32 * r["LSF_limit_minutes"] for r in rows) != 552 * 60:
        raise ValueError("Reviewed budget changed")
    return batch


def prepare(user_request):
    batch = check_inputs()
    review_path = PREPARED / "review.json"
    source_rows = {r["id"]: r for r in load(review_path)["DFT_first_ten"]}
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    potcars = {r["POTCAR_source"]: r["POTCAR_sha256"] for r in batch["jobs"]}
    live_path = EXEC / "remote_preflight.json"
    command = " && ".join((
        "set -e", "id -un", f"bqueues -w {QUEUE}", "busers -w $(id -un)",
        "test -x ~/soft/vasp541vtst/bin/vasp_std", "test -r /home_gkx/env/intel/intel2016.sh",
        "test -d ~/sbq/Fe110", f"test ! -e {REMOTE_ROOT}", f"test ! -L {REMOTE_ROOT}",
        "sha256sum " + " ".join(sorted(potcars)),
        "bparams -l | grep ABS_RUNLIMIT", "echo TARGETS_ABSENT",
    ))
    live = ssh(command)
    save(live_path, live)
    out = live["stdout"]
    if (live["exit_code"] or USER not in out.splitlines()
            or not re.search(r"^Gkn_normal\s+\d+\s+Open:Active", out, re.M)
            or not re.search(r"ABS_RUNLIMIT\s*=\s*Y\b", out)
            or "TARGETS_ABSENT" not in out.splitlines()
            or any((digest + "  ") not in out for digest in potcars.values())):
        raise RuntimeError("CPU/LSF, POTCAR or unique target preflight failed")
    empty_geometry = EXEC / "static_geometry_adapter.json"
    save(empty_geometry, {})
    authorization_source = EXEC / "user_request.json"
    save(authorization_source, {"request": user_request, "recorded_at_utc": now(),
        "final_submission_list": bind(PLAN), "scope": [r["id"] for r in batch["jobs"]],
        "host": HOST, "queue": QUEUE, "max_requested_core_hours": 552,
        "deferred": DEFERRED, "reserve_ids_only": batch["reserve_ids_only"],
        "retry": False, "gpu_or_training": False})
    ready = {}
    for row in batch["jobs"]:
        sid = row["id"]
        folder = Path(row["local_input_directory"])
        if (folder != RUN / "vasp_review_inputs" / sid or row["remote_directory"] != REMOTE_ROOT + "/" + sid
                or row["allowed_when_authorized"] != ACTION or submission_status(folder)["status"] != "NOT_RESERVED"):
            raise ValueError(f"Target, action or existing reservation mismatch: {sid}")
        preflight_path = folder / "submission_preflight.json"
        report = preflight(folder, "diagnostic_static", write_report=False)
        if (not report["passed"] or report != load(preflight_path)
                or sha(preflight_path) != row["preflight_sha256"]
                or report["files"] != row["input_sha256"] or report["bundle_sha256"] != row["bundle_sha256"]
                or report["cores"] != 32 or row["MPI_ranks"] != 32
                or report["wall_limit_minutes"] != row["LSF_limit_minutes"]
                or _bsub_command(report) != row["bsub_preview"]):
            raise ValueError(f"Current input bundle differs from reviewed preflight: {sid}")
        InputBundle.from_preflight(report).verify(folder)
        selected = source_rows[sid]
        coordinate_path = Path(selected["coordinate_path"])
        if (sha(coordinate_path) != report["files"]["POSCAR"] or selected["coordinate_sha256"] != report["files"]["POSCAR"]
                or selected["exact_catalog_label_match"] or selected["old_280_input_match"]
                or selected["geometry_check"]["failures"] or selected["fresh_geometry"]["pair_guard_failures"]
                or not selected["fresh_geometry"]["bottom18_only_fixed"]
                or not selected["fresh_geometry"]["same_clean_cell_within1e-6A"]):
            raise ValueError(f"Geometry/source binding failed: {sid}")
        analysis_path = folder / "submission_no_output_analysis.json"
        reaction_indices = range(45, 45 + len(selected["graph"]["symbols_local"]))
        analysis = analyze(folder, THRESHOLDS, list(reaction_indices), write_output=False)
        if analysis["status"] != "NO_OUTPUT":
            raise ValueError(f"Unexpected output already present: {sid}")
        save(analysis_path, analysis)
        validation_path = folder / "submission_geometry_review.json"
        validation = {"status": "REVIEWED_FOR_FIXED_GEOMETRY_DFT_LABEL_ONLY", "reviewed_input": bind(review_path),
                      "coordinate_source": bind(coordinate_path), "batch": bind(PLAN), "cpu_preflight": bind(live_path),
                      "geometry_check": selected["geometry_check"], "fresh_geometry": selected["fresh_geometry"],
                      "stable_adsorption_accepted": False}
        save(validation_path, validation)
        bindings = {"geometry": bind(empty_geometry), "analysis": bind(analysis_path),
                    "thresholds": bind(THRESHOLDS), "preflight": bind(preflight_path),
                    "validation": bind(validation_path)}
        kwargs = dict(climb=False, path_reviewed=True, preflight=report, validation=validation,
                      source_bindings=bindings)
        evidence = decide_execution({}, analysis, thresholds, **kwargs)["EVIDENCE"]
        auth_path = folder / "user_execution_authorization.json"
        auth = {"schema_version": 1, "document_kind": "user_execution_authorization",
                "action": ACTION, "calculation_kind": "diagnostic_static", "authorized_at": now(),
                "source": bind(authorization_source), "target": {"server_alias": HOST, "remote_dir": row["remote_directory"]},
                "workdir_identity": workdir_identity(folder), "bundle_sha256": report["bundle_sha256"],
                "evidence_sha256": execution_evidence_sha256(evidence),
                "potcar": {"source": row["POTCAR_source"], "sha256": row["POTCAR_sha256"],
                           "spec_sha256": report["files"]["POTCAR.spec"]}}
        save(auth_path, auth)
        bindings["authorization"] = bind(auth_path)
        decision = decide_execution({}, analysis, thresholds, authorization=auth, **kwargs)
        decision_path = folder / "execution_decision.json"
        save(decision_path, decision)
        require_action(decision_path, ACTION, decision["state_sha256"])
        ready[sid] = bind(decision_path)
    save(EXEC / "ready.json", {"plan_sha256": PLAN_SHA, "decisions": ready, "frozen_hashes": batch["frozen_hashes"]})
    print(f"{len(ready)} current, hash-bound LSF gates are ready.")


def verify_job(job_id, row, suffix):
    obs = ssh(f"bjobs -a -UF {job_id}")
    save(EXEC / f"bjobs_{job_id}_{suffix}.json", obs)
    out = re.sub(r"\n {26}", "", obs["stdout"])
    header = re.search(rf"Job <{job_id}>,\s*User <{USER}>.*?Status <([A-Z]+)>,\s*Queue <([^>]+)>",
                       out, re.S)
    ranks = re.search(r"\b(\d+)\s+(?:Processors\s+Requested|Task\(s\))", out)
    limit = re.search(r"\bRUNLIMIT\s+([0-9]+(?:\.[0-9]+)?)\s+min\b", out)
    cwd = row["remote_directory"].removeprefix("~/")
    if (obs["exit_code"] or not header or not ranks or not limit or cwd not in out
            or header[2] != QUEUE or int(ranks[1]) != 32 or float(limit[1]) != row["LSF_limit_minutes"]):
        raise RuntimeError(f"LSF parameters require review for {job_id}; see raw bjobs evidence")
    return {"id": row["id"], "job_id": job_id, "queue": header[2], "scheduler_status": header[1],
            "ranks_requested": int(ranks[1]), "limit_minutes": float(limit[1]), "observed_at_utc": obs["observed_at_utc"]}


def execute():
    batch = check_inputs()
    ready = load(EXEC / "ready.json")
    if ready["plan_sha256"] != PLAN_SHA or set(ready["decisions"]) != {r["id"] for r in batch["jobs"]}:
        raise ValueError("Gate batch identity mismatch")
    for row in batch["jobs"]:
        folder = Path(row["local_input_directory"])
        decision_path = folder / "execution_decision.json"
        decision = load(decision_path)
        if (bind(decision_path) != ready["decisions"][row["id"]]
                or submission_status(folder)["status"] != "NOT_RESERVED"):
            raise ValueError(f"Changed gate or existing submission: {row['id']}")
        require_action(decision_path, ACTION, decision["state_sha256"])
    save(EXEC / "batch_attempt.json", {"attempted_at_utc": now(), "ready": bind(EXEC / "ready.json")})
    accepted = []
    for row in batch["jobs"]:
        folder = Path(row["local_input_directory"])
        decision_path = folder / "execution_decision.json"
        receipt = submit(folder, decision_path, HOST, row["remote_directory"],
                         row["POTCAR_source"], row["POTCAR_sha256"], ACTION)
        job_id = receipt["job_id"]
        print(f"{row['id']} job={job_id} LSF_ACCEPTED", flush=True)
        if (receipt["gate_decision_sha256"] != ready["decisions"][row["id"]]["sha256"]
                or f"queue <{QUEUE}>" not in receipt["submit_stdout"]):
            raise RuntimeError(f"Submission receipt requires review for {job_id}")
        result = verify_job(job_id, row, "initial")
        print(f"{job_id} {result['scheduler_status']} {QUEUE} 32 ranks {result['limit_minutes']:g} min", flush=True)
        accepted.append(result)
    if guard_hashes() != batch["frozen_hashes"]:
        raise RuntimeError("Protected hashes differ after submission")
    save(EXEC / "submission_summary.json", {"jobs": accepted, "budget_core_hours": 552,
        "deferred": DEFERRED, "protected_hashes_unchanged": True, "plan_sha256": PLAN_SHA})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "execute"))
    args = parser.parse_args()
    if args.phase == "prepare":
        import sys

        user_request = sys.stdin.read().strip()
        if not user_request:
            raise ValueError("The explicit user request is required")
        EXEC.mkdir()
        prepare(user_request)
    else:
        execute()
