"""Stage and execute exactly one approved batch of Fe(110) fixed-coordinate force labels."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import yaml

from archive.fe110_c2_c3_preflight_20261118.submit_lsf import HOST, QUEUE, THRESHOLDS, USER, bind, now, ssh
from archive.fe110_joint_priority_20261117.analyze import BASE, guard_hashes
from scripts.artifact_io import load_json_object as load, sha256_file as sha, source_file_manifest_valid, write_json_exclusive as save
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import InputBundle, _bsub_command, preflight, submission_status, submit
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256, workdir_identity
from scripts.ts_strategy_engine.execution_gate import decide_execution, require_action
from scripts.vasp_inputs import build_fe110_active_learning_force_label
from scripts.vasp_result_gate import read_incar_values

RUN = BASE / "c2_c3_reico_pathgap_20261119_v1"
SELECTION = RUN / "point_selection.json"
REMOTE = "~/sbq/Fe110/reico_c2_c3_pathgap_20261119_v1"
ACTION = "SUBMIT_DIAGNOSTIC_VASP"
POTCARS = {
    "Fe C H": ("~/sbq/Fe110/potcars/Fe_C_H/POTCAR", "bd39c0ebfbbe6207bc8e1b976677b4687ae2d2956f5a74dc1dea3298adef063a"),
    "Fe C O H": ("~/sbq/Fe110/potcars/Fe_C_O_H/POTCAR", "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85"),
}


def protected_inputs():
    frozen = load(BASE / "c2_c3_label9_lsf_20261118_v1/final_submission_list.json")["frozen_hashes"]
    snapshot = guard_hashes()
    if any(
        snapshot[path] != digest
        for path, digest in frozen.items()
        if "combined_force_package" in path or path.endswith("01_METHOD_PROTOCOL.md")
    ):
        raise ValueError("Frozen force package or scientific protocol is different")
    lock = load(RUN / "locked_optimization_starts.json")
    for row in [lock["common_start_11B"], lock["common_start_complete_C3_05_cfg2"], *lock["models"].values()]:
        if sha(Path(row["path"])) != row["sha256"]:
            raise ValueError("Locked optimization start or model changed")
    assert lock["ML_or_DFT_optimization_authorized"] is False
    return snapshot


def check_remote():
    command = " && ".join(
        (
            "set -e",
            "id -un",
            f"bqueues -w {QUEUE}",
            "busers -w $(id -un)",
            "test -x ~/soft/vasp541vtst/bin/vasp_std",
            "test -r /home_gkx/env/intel/intel2016.sh",
            f"test ! -e {REMOTE}",
            f"test ! -L {REMOTE}",
            "sha256sum " + " ".join(path for path, _ in POTCARS.values()),
            "bparams -l | grep ABS_RUNLIMIT",
            "echo TARGETS_ABSENT",
        )
    )
    result = ssh(command)
    path = RUN / "remote_preflight.json"
    save(path, result)
    output = result["stdout"]
    if (
        result["exit_code"]
        or USER not in output.splitlines()
        or "TARGETS_ABSENT" not in output.splitlines()
        or not re.search(r"^Gkn_normal\s+\d+\s+Open:Active", output, re.M)
        or not re.search(r"ABS_RUNLIMIT\s*=\s*Y\b", output)
        or any(digest + "  " not in output for _, digest in POTCARS.values())
    ):
        raise RuntimeError("CPU, queue, POTCAR or unique target preflight did not pass")
    return path


def input_bundle(row, parent):
    sid = row["id"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", sid):
        raise ValueError("Invalid point identity")
    position = Path(row["source"])
    if sha(position) != row["source_sha256"] or row["compatible_same_coordinate_label"]:
        raise ValueError(f"Unbound or already labeled coordinate: {sid}")
    folder = parent / sid
    folder.mkdir()
    with (folder / "POSCAR").open("xb") as handle:
        handle.write(position.read_bytes())
    profile = build_fe110_active_learning_force_label(folder)
    if sha(folder / "POSCAR") != row["source_sha256"]:
        raise ValueError("Static builder changed coordinate bytes")
    incar = read_incar_values(folder / "INCAR")
    if (
        profile["gamma_mesh"] != [5, 5, 1]
        or profile["cores"] != 32
        or any(
            float(incar[k]) != value
            for k, value in {
                "ENCUT": 400,
                "EDIFF": 1e-6,
                "ISPIN": 2,
                "ISMEAR": 1,
                "SIGMA": 0.2,
                "NSW": 0,
                "IBRION": -1,
                "LORBIT": 11,
            }.items()
        )
    ):
        raise ValueError(f"Locked Fe(110) force-label branch changed: {sid}")
    minutes = 135 if row["composition"] in ("C2HO", "C3H2O") else 90
    launcher = folder / "script.lsf"
    head, newline, rest = launcher.read_bytes().partition(b"\n")
    if not head.startswith(b"#!") or not newline or b"#BSUB -W" in rest:
        raise ValueError("Unrecognized shared launcher")
    launcher.write_bytes(head + newline + f"#BSUB -W {minutes}\n".encode("ascii") + rest)
    report = preflight(folder, "diagnostic_static", write_report=False)
    if not report["passed"] or report["cores"] != 32 or report["wall_limit_minutes"] != minutes:
        raise ValueError(f"Input preflight failed: {sid}: {report['errors']}")
    InputBundle.from_preflight(report).verify(folder)
    preflight_path = folder / "submission_preflight.json"
    save(preflight_path, report)
    potcar = POTCARS[(folder / "POTCAR.spec").read_text(encoding="utf-8").strip()]
    return folder, report, preflight_path, potcar


def bind_gate(row, folder, report, preflight_path, potcar, geometry_path, remote_path, auth_source, thresholds):
    analysis_path = folder / "submission_no_output_analysis.json"
    analysis = analyze(folder, THRESHOLDS, write_output=False)
    if analysis["status"] != "NO_OUTPUT":
        raise ValueError("Existing calculation output in a new input directory")
    save(analysis_path, analysis)
    review_path = folder / "submission_geometry_review.json"
    review = {
        "status": "REVIEWED_FIXED_GEOMETRY_FORCE_LABEL_ONLY",
        "point": row,
        "selection": bind(SELECTION),
        "cpu_preflight": bind(remote_path),
        "optimization_start_lock": bind(RUN / "locked_optimization_starts.json"),
        "scientific_acceptance": False,
    }
    save(review_path, review)
    bindings = {
        "geometry": bind(geometry_path),
        "analysis": bind(analysis_path),
        "thresholds": bind(THRESHOLDS),
        "preflight": bind(preflight_path),
        "validation": bind(review_path),
    }
    kwargs = dict(climb=False, path_reviewed=True, preflight=report, validation=review, source_bindings=bindings)
    evidence = decide_execution({}, analysis, thresholds, **kwargs)["EVIDENCE"]
    target = REMOTE + "/" + row["id"]
    auth = {
        "schema_version": 1,
        "document_kind": "user_execution_authorization",
        "action": ACTION,
        "calculation_kind": "diagnostic_static",
        "authorized_at": now(),
        "source": bind(auth_source),
        "target": {"server_alias": HOST, "remote_dir": target},
        "workdir_identity": workdir_identity(folder),
        "bundle_sha256": report["bundle_sha256"],
        "evidence_sha256": execution_evidence_sha256(evidence),
        "potcar": {"source": potcar[0], "sha256": potcar[1], "spec_sha256": report["files"]["POTCAR.spec"]},
    }
    auth_path = folder / "user_execution_authorization.json"
    save(auth_path, auth)
    bindings["authorization"] = bind(auth_path)
    decision = decide_execution({}, analysis, thresholds, authorization=auth, **kwargs)
    decision_path = folder / "execution_decision.json"
    save(decision_path, decision)
    require_action(decision_path, ACTION, decision["state_sha256"])
    return {
        "id": row["id"],
        "folder": str(folder),
        "remote_dir": target,
        "decision": bind(decision_path),
        "inputs": report["files"],
        "bundle_sha256": report["bundle_sha256"],
        "potcar_source": potcar[0],
        "potcar_sha256": potcar[1],
        "cores": report["cores"],
        "minutes": report["wall_limit_minutes"],
        "preview": _bsub_command(report),
        "composition": row["composition"],
        "case_type": row["case_type"],
        "why": row["why"],
    }


def prepare(user_request):
    snapshot = protected_inputs()
    selected = load(SELECTION)
    if not source_file_manifest_valid({"source_files": selected["bound_sources"]}):
        raise ValueError("Point selection sources changed")
    samples = selected["samples"]
    assert len({r["id"] for r in samples}) == len(samples)
    assert sum(r["case_type"] == "REICO_EXISTING_SAMPLED_FIXED_GEOMETRY" for r in samples) == 20
    remote_path = check_remote()
    parent = RUN / "vasp_inputs"
    parent.mkdir()
    geometry_path = RUN / "static_geometry_adapter.json"
    save(geometry_path, {})
    authority = RUN / "user_request.json"
    save(
        authority,
        {
            "exact_user_request": user_request,
            "last_instruction_authorizes_review_passed_statics": True,
            "selection": bind(SELECTION),
            "targets": [r["id"] for r in samples],
            "host": HOST,
            "GPU_training_and_geometry_optimization_authorized": False,
            "submission_retry": False,
        },
    )
    thresholds = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    rows = []
    for row in samples:
        folder, report, preflight_path, potcar = input_bundle(row, parent)
        rows.append(bind_gate(row, folder, report, preflight_path, potcar, geometry_path, remote_path, authority, thresholds))
    assert protected_inputs() == snapshot
    save(RUN / "ready.json", {"selection": bind(SELECTION), "frozen_guard_hashes": snapshot, "jobs": rows})
    print(len(rows), "hash-bound diagnostic-static gates authorized", flush=True)


def scheduler_check(entries, path):
    jobs = [r["job_id"] for r in entries]
    if any(re.fullmatch(r"[1-9]\d*", job) is None for job in jobs):
        raise ValueError("Invalid job ID in canonical submission receipt")
    record = ssh("bjobs -a -UF " + " ".join(jobs))
    save(path, record)
    chunks = re.split(r"(?m)(?=^Job <\d+>,)", record["stdout"])
    raw = {re.match(r"Job <(\d+)>", text)[1]: text for text in chunks if text.startswith("Job <")}
    if record["exit_code"] or set(raw) != set(jobs):
        raise RuntimeError("Scheduler lookup incomplete; preserve submitted jobs and inspect")
    verified = []
    for row in entries:
        text = raw[row["job_id"]]
        header = re.search(r"Status <([A-Z]+)>, Queue <([^>]+)>", text)
        ranks = re.search(r"(\d+) Processors Requested", text)
        minutes = re.search(r"RUNLIMIT\s+([0-9.]+) min", text)
        if (
            not header
            or header[2] != QUEUE
            or not ranks
            or int(ranks[1]) != row["cores"]
            or not minutes
            or float(minutes[1]) != row["minutes"]
            or row["remote_dir"][2:] not in text
            or f"User <{USER}>" not in text
        ):
            raise RuntimeError(f"Unexpected scheduler resources for {row['job_id']}; stop the batch without retry")
        verified.append({**row, "status": header[1], "queue": header[2], "observed_at_utc": record["observed_at_utc"]})
    return verified


def execute():
    ready_path = RUN / "ready.json"
    ready = load(ready_path)
    if ready["selection"] != bind(SELECTION) or protected_inputs() != ready["frozen_guard_hashes"]:
        raise ValueError("Reviewed source or frozen inputs changed")
    for row in ready["jobs"]:
        folder = Path(row["folder"])
        decision_path = Path(row["decision"]["path"])
        if bind(decision_path) != row["decision"] or submission_status(folder)["status"] != "NOT_RESERVED":
            raise ValueError("A gate changed or a job has an existing reservation")
        require_action(decision_path, ACTION, load(decision_path)["state_sha256"])
    save(RUN / "batch_attempt.json", {"ready": bind(ready_path), "started_at_utc": now(), "auto_retry": False})
    submitted = []
    for row in ready["jobs"]:
        receipt = submit(
            Path(row["folder"]), Path(row["decision"]["path"]), HOST, row["remote_dir"], row["potcar_source"], row["potcar_sha256"], ACTION
        )
        job = receipt["job_id"]
        print(row["id"], job, flush=True)
        if f"queue <{QUEUE}>" not in receipt["submit_stdout"] or receipt["bundle_sha256"] != row["bundle_sha256"]:
            raise RuntimeError("Unexpected submission parameters; preserve receipts")
        submitted.append({**row, "job_id": job})
        if len(submitted) == 1:
            scheduler_check(submitted, RUN / "first_bjobs.json")
    summary = scheduler_check(submitted, RUN / "final_bjobs.json")
    assert protected_inputs() == ready["frozen_guard_hashes"]
    save(
        RUN / "submission_summary.json",
        {"jobs": summary, "optimization_submissions": 0, "GPU_submissions": 0, "training_runs": 0, "frozen_guards_verified": True},
    )
    print(len(summary), "scheduler-verified single points", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "execute"))
    args = parser.parse_args()
    if args.phase == "prepare":
        request = sys.stdin.read().strip()
        if not request:
            raise ValueError("Need the exact user authorization")
        prepare(request)
    else:
        execute()
