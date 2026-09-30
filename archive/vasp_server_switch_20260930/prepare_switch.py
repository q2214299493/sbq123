"""Bounded, user-authorized account switch using repository execution gates."""
from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import (
    load_json_object, sha256_file, sha256_text, write_json, write_json_exclusive,
)
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.submission import preflight, stop_job
from scripts.scheduler_evidence import _parse_lsf_bjobs, validate_stored_lsf_evidence
from scripts.ts_strategy_engine.execution_evidence import (
    execution_evidence_sha256, load_bound_evidence, workdir_identity,
)
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
OLD = BASE / "h_is_a_int06_gpu1802_neb_temp_r3_72r_16pn_20260930"
NEW = BASE / "h_is_a_int06_gpu1802_neb_sbq123_108r_16pn_20260930"
RECORDS = Path(__file__).resolve().parent
SOURCE = RECORDS / "user_request.json"
THRESHOLDS = ROOT / "configs/neb_agent/default_thresholds.yaml"
REMOTE_BASE = "~/sbq/Fe110/ts/c2ho_h_to_c2h2o_20260904/"
POTCAR = "~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR"
POTCAR_SHA = "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scheduler(host: str, job: str, output: Path) -> dict:
    argv = ["ssh", host, "bjobs", "-a", job]
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                            timeout=60, check=True)
    payload = {
        "schema_version": 1, "document_kind": "scheduler_job_evidence",
        "stage": "ordinary_neb", "scheduler": "LSF", "server_alias": host,
        "job_id": job, "status": _parse_lsf_bjobs(result.stdout, job),
        "checked_at": now(), "source_command": " ".join(argv),
        "query": {"argv": argv, "returncode": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr,
                  "stdout_sha256": sha256_text(result.stdout)},
    }
    validate_stored_lsf_evidence(payload)
    write_json(output, payload)
    return payload


def decide(request_path: Path, request: dict) -> dict:
    write_json(request_path, request)
    bindings = {}
    evidence = {
        name: load_bound_evidence(request_path, request, name, bindings)
        for name in ("geometry", "analysis", "thresholds", "preflight", "scheduler", "authorization")
    }
    return decide_execution(
        evidence["geometry"], evidence["analysis"], evidence["thresholds"],
        climb=False, path_reviewed=True, preflight=evidence["preflight"],
        scheduler=evidence["scheduler"], authorization=evidence["authorization"],
        source_bindings=bindings,
    )


def bind_gate(workdir: Path, destination: Path, action: str, host: str,
              scheduler_path: Path | None = None, job_id: str | None = None) -> Path:
    request = {
        "geometry_file": str(workdir / "path_geometry_diagnosis.json"),
        "analysis_file": str(workdir / "neb_analysis.json"),
        "thresholds_file": str(THRESHOLDS), "climb": False, "path_reviewed": True,
    }
    if scheduler_path:
        request["scheduler_file"] = str(scheduler_path)
    if action == "SUBMIT_VASP":
        request["preflight_file"] = str(workdir / "submission_preflight.json")
    initial = decide(destination / "gate_request_before_authorization.json", request)
    write_json(destination / "gate_before_authorization.json", initial)
    bundle = load_json_object(workdir / "submission_preflight.json")
    target = {"server_alias": host, "remote_dir": REMOTE_BASE + workdir.name}
    authorization = {
        "schema_version": 1, "document_kind": "user_execution_authorization",
        "action": action, "authorized_at": now(),
        "source": {"path": str(SOURCE), "sha256": sha256_file(SOURCE)},
        "target": target, "workdir_identity": workdir_identity(workdir),
        "bundle_sha256": bundle["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(initial["EVIDENCE"]),
    }
    if job_id:
        authorization.update(job_id=job_id, allowed_scheduler_statuses=["PEND", "RUN"])
        target["job_id"] = job_id
    else:
        authorization["calculation_kind"] = "ordinary_neb"
        authorization["potcar"] = {
            "source": POTCAR, "sha256": POTCAR_SHA,
            "spec_sha256": bundle["files"]["POTCAR.spec"],
        }
    auth_path = destination / "user_execution_authorization.json"
    write_json(auth_path, authorization)
    request["authorization_file"] = str(auth_path)
    decision = decide(destination / "execution_gate_request.json", request)
    decision_path = destination / "execution_gate_decision.json"
    write_json(decision_path, decision)
    require_action(decision_path, action, decision["state_sha256"])
    return decision_path


def stop() -> None:
    receipt = RECORDS / "stop_receipt.json"
    if receipt.exists():
        raise FileExistsError("Stop receipt exists; reconcile it before any repeat.")
    before = RECORDS / "scheduler_before.json"
    current = scheduler("sunboquan-cdj1-temp", "9806036", before)
    if current["status"] not in {"PEND", "RUN"}:
        raise ValueError("Old job already terminal; inspect before changing the plan.")
    decision_path = bind_gate(OLD, RECORDS, "STOP_JOB", "sunboquan-cdj1-temp", before, "9806036")
    result = stop_job(decision_path, "sunboquan-cdj1-temp", "9806036", receipt)
    after = scheduler("sunboquan-cdj1-temp", "9806036", RECORDS / "scheduler_after.json")
    if after["status"] != "EXIT":
        raise ValueError("Stop issued but EXIT not confirmed; preserve old SSH connection.")
    print(f"STOP {result['job_id']} confirmed {after['status']}")


def prepare() -> None:
    terminal = load_json_object(RECORDS / "scheduler_after.json")
    validate_stored_lsf_evidence(terminal, required_status="EXIT")
    if not NEW.is_dir() or not (NEW / "script.lsf").is_file():
        raise FileNotFoundError("Create the reviewed 108-rank script with apply_patch first.")
    files = ["INCAR", "KPOINTS", "POTCAR.spec", "reaction_contract.normalized.json",
             "path_generation_report.json", "path_review.json", "dist.dat", "movie.xyz",
             "work_review_evidence.json"] + [f"{i:02d}/POSCAR" for i in range(11)]
    hashes = {}
    for name in files:
        target = NEW / name
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite replacement input: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OLD / name, target)
        digest = sha256_file(OLD / name)
        if sha256_file(target) != digest:
            raise ValueError(f"Scientific-input identity failed: {name}")
        hashes[name] = digest
    write_json(NEW / "server_switch_identity.json", {
        "status": "PASS", "source_workdir": str(OLD), "replacement_workdir": str(NEW),
        "unchanged_files_sha256": hashes, "mpi_ranks": 108, "ranks_per_image": 12,
        "per_node_rank_cap": 16, "source_request_sha256": sha256_file(SOURCE),
        "dist_movie_review": "Reused byte-identical reviewed path evidence; no coordinate change.",
    })
    geometry = diagnose(NEW, ["49"], [str(i) for i in range(18)], THRESHOLDS,
                        expected_interior=9)
    if geometry["status"] != "PASS":
        raise ValueError(f"Geometry needs review: {geometry['status']}")
    analyze(NEW, THRESHOLDS, [49])
    check = preflight(NEW, "ordinary_neb")
    if not check["passed"]:
        raise ValueError(f"Preflight failed: {check['errors']}")
    decision = bind_gate(NEW, NEW, "SUBMIT_VASP", "sunboquan-codex")
    print(f"PREPARED {NEW.name}: geometry PASS; preflight PASS; SUBMIT_VASP allowed: {decision.name}")


def checkpoint() -> None:
    receipt = load_json_object(NEW / "submission_record.json")
    current = load_json_object(NEW / "scheduler_checkpoint_submission.json")
    job_id = receipt["job_id"]
    validate_stored_lsf_evidence(current)
    if receipt["status"] != "SUBMITTED" or current["job_id"] != job_id:
        raise ValueError("Submission receipt and scheduler evidence must match.")
    previous_id = "task-is-a-int06-neb9806036-resource-reallocation-20260930"
    event = load_json_object(ROOT / "modules/state_handoff/events" / (previous_id + ".json"))
    stamp = now()
    event_id = f"task-is-a-int06-neb{job_id}-sbq123-switch-20260930"
    event.update(event_id=event_id, occurred_at=stamp, recorded_at=stamp,
                 supersedes=[previous_id],
                 summary=f"User-authorized account switch: NEB9806036 EXIT; identical-science 108-rank NEB{job_id} submitted on sbq123 and {current['status']}.")
    records = [
        (SOURCE, "user_authorization"),
        (RECORDS / "stop_receipt.json", "repository_document"),
        (RECORDS / "scheduler_after.json", "scheduler"),
        (NEW / "server_switch_identity.json", "module_validation"),
        (NEW / "submission_preflight.json", "module_validation"),
        (NEW / "execution_gate_decision.json", "module_validation"),
        (NEW / "submission_record.json", "repository_document"),
        (NEW / "scheduler_checkpoint_submission.json", "scheduler"),
    ]
    event["evidence"] = [{"locator": path.relative_to(ROOT).as_posix(),
                           "sha256": sha256_file(path), "authority": authority,
                           "observed_at": stamp} for path, authority in records]
    event["payload"] = {
        "objective": f"Monitor ordinary coarse NEB{job_id} for the remaining IS-A9725473 -> INT06_9748648 H migration.",
        "phase": "active",
        "current_evidence": [
            "User changed the future VASP default connection to nsgkn_chengdj3@10.68.0.103:22 (sunboquan-codex / sbq123).",
            "Old NEB9806036 was PEND when the current STOP_JOB executor stopped it; raw scheduler evidence confirms EXIT. Its old temporary SSH connection was removed; calculation files and other jobs were retained.",
            f"Replacement NEB{job_id} was submitted once with 108 ranks, 12 ranks per internal image, NPAR4 and NP_PER_NODE16. Its saved scheduler checkpoint is {current['status']}.",
            "All eleven POSCARs, INCAR, KPOINTS, POTCAR.spec, contract and reviewed dist/movie/path evidence are byte-identical to the source package. The geometry parser and execution evidence were regenerated against the replacement directory.",
            "Geometry diagnosis, ordinary-NEB preflight and current SUBMIT_VASP gate passed. No convergence, TS, barrier or Grade-A result is claimed.",
        ],
        "one_executable_step": f"At the next requested checkpoint query LSF{job_id} through sunboquan-codex and run the canonical compact NEB monitor for {REMOTE_BASE + NEW.name}; separate scheduler, electronic, force and geometry states.",
        "submission_boundary": "One replacement ordinary NEB submitted under explicit user authority. No duplicate, restart, resource change, CI/Dimer or stop without a current gate and user authority.",
        "done_when": [f"NEB{job_id} is monitored with scheduler and per-image evidence; a completed/stopped path is reviewed before any authorized refinement."],
        "constraints": [
            "Keep accepted INT06-MID and MID-FS segments unchanged.",
            "Preserve atom order, fixed Fe0-17, nine internal images, NPAR4 and SIGMA0.20 compatibility.",
            "User explicitly requested 108 total ranks for this replacement; under resource pressure retain a 16- or 32-rank per-node cap subject to image/rank divisibility and quota.",
            "GPU predictions cannot establish a TS or electronic barrier.",
        ],
        "authoritative_references": [path.relative_to(ROOT).as_posix() for path, _ in records],
    }
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print(target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("stop", "prepare", "scheduler", "checkpoint"))
    parser.add_argument("--job-id")
    args = parser.parse_args()
    if args.action == "stop":
        stop()
    elif args.action == "prepare":
        prepare()
    elif args.action == "checkpoint":
        checkpoint()
    else:
        if not args.job_id:
            parser.error("scheduler requires --job-id")
        print(scheduler("sunboquan-codex", args.job_id, NEW / "scheduler_checkpoint_submission.json")["status"])
