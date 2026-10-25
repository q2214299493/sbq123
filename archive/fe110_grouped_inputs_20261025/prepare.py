"""Prepare the reviewed12+2 locally with native builders; never upload or submit."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid,
)
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import (
    build_fe110_active_learning_force_label, build_fe110_adsorption_relaxation,
)
from scripts.vasp_result_gate import read_incar_values


def timing(path):
    """Read only bounded header/tail text; hash original bytes separately."""
    with path.open("rb") as handle:
        header = handle.read(16000).decode("ascii", errors="replace")
        handle.seek(max(0, path.stat().st_size - 64000))
        tail = handle.read().decode("ascii", errors="replace")
    cores = re.search(r"running on\s+(\d+) total cores", header)
    elapsed = re.search(r"Elapsed time \(sec\):\s*([\d.]+)", tail)
    steps = re.findall(r"Iteration\s+(\d+)\s*\(", tail)
    if not cores or not elapsed or int(cores[1]) <= 0 or float(elapsed[1]) <= 0:
        raise ValueError("missing or invalid timing metadata")
    return {"OUTCAR_path": str(path), "OUTCAR_sha256": sha256_file(path),
        "cores": int(cores[1]), "elapsed_seconds": float(elapsed[1]),
        "last_ionic_iteration_in_tail": max(map(int, steps)) if steps else None,
        "allocated_core_hours": int(cores[1]) * float(elapsed[1]) / 3600}


def cost_references(root):
    base = root / "calculations/fe110_reico_pilot300_20261022/probe6_v1"
    samples = load_json_object(base / "submission_summary.json")["samples"]
    static, relaxation, sources = [], [], [base / "submission_summary.json"]
    for row in samples:
        folder = base / "checks/20261022T084625Z/vasp" / row["sample_id"]
        review = load_json_object(folder / "label_review.json")
        record = timing(folder / "OUTCAR")
        if (record["OUTCAR_sha256"] != review["source_OUTCAR_sha256"]
                or not review["normal_completion"] or not review["electronic_converged"]):
            raise ValueError("timing reference not bound to a qualified static")
        incar = read_incar_values(folder / "INCAR")
        if float(incar["SIGMA"]) != .2 or float(incar["EDIFF"]) != 1e-6 or record["cores"] != 32:
            raise ValueError("incompatible static timing reference")
        static.append({**record, "job_id": row["job_id"], "composition": review["composition"]})
        sources.extend(folder / name for name in ["OUTCAR", "INCAR", "label_review.json"])
    for job in ["9629858", "9629859"]:
        folder = root / "calculations/fe110_c3_existing_recovery_20261023/collection_v1" / job
        record = timing(folder / "OUTCAR")
        with (folder / "OSZICAR").open(encoding="utf-8") as handle:
            steps = [int(match[1]) for line in handle
                     if (match := re.match(r"^\s*(\d+)\s+F=", line))]
        if record["cores"] != 32 or steps != list(range(1, 81)):
            raise ValueError("expected a32-core80-step relaxation timing reference")
        incar = read_incar_values(folder / "INCAR")
        relaxation.append({**record, "job_id": job, "composition": "C3H2O",
            "completed_ionic_steps_from_OSZICAR": len(steps),
            "OSZICAR_sha256": sha256_file(folder / "OSZICAR"),
            "reference_NPAR": incar.get("NPAR"), "reference_LORBIT": incar.get("LORBIT"),
            "reference_SIGMA": incar["SIGMA"], "reference_EDIFF": incar["EDIFF"]})
        sources.extend(folder / name for name in ["OUTCAR", "INCAR", "OSZICAR"])
    return static, relaxation, sources


def budget(static, relaxation):
    single = [12 * min(r["allocated_core_hours"] for r in static),
              12 * max(r["allocated_core_hours"] for r in static)]
    optimize = [2 * min(r["allocated_core_hours"] for r in relaxation),
                2 * max(r["allocated_core_hours"] for r in relaxation)]
    return {"single_points": 12, "optimizations": 2, "cores_per_job": 32,
        "max_ionic_steps_per_optimization": 80, "automatic_continuation": False,
        "account_core_quota_planning_assumption": 128, "max_concurrent_jobs_assuming_empty_account": 4,
        "single_point_reference_core_hours": single,
        "optimization_reference_core_hours": optimize,
        "combined_reference_core_hours": [a + b for a, b in zip(single, optimize, strict=True)],
        "separate_batches_ideal_hours_without_queue": [
            3 * min(r["elapsed_seconds"] for r in static) / 3600 + optimize[0] / 64,
            3 * max(r["elapsed_seconds"] for r in static) / 3600 + optimize[1] / 64],
        "cost_is_historical_envelope_not_confidence_interval_or_cap": True,
        "optimization_reference_mismatch": "C3-only old runs haveNPAR4 and noLORBIT;new canonical C2H3/C3 runs write local moments and inherit defaultNPAR;analogy only",
        "monetary_cost": None, "account_price_per_core_hour": "UNKNOWN",
        "live_quota_queue_and_target_POTCAR_rechecks_required": True}


def case_input(row, role, destination, profile_path, custodian, root, potcars):
    if destination.exists():
        old = load_json_object(destination / "prepared_case.json")
        check = preflight(destination, old["kind"], write_report=False)
        if not check["passed"] or check["bundle_sha256"] != old["bundle_sha256"]:
            raise ValueError("existing prepared case changed")
        return old
    source = Path(row["structure_path"])
    if sha256_file(source) != row["structure_sha256"]:
        raise ValueError("source geometry changed")
    destination.mkdir(parents=True)
    (destination / "POSCAR").write_bytes(source.read_bytes())
    if role == "single_points":
        metadata = build_fe110_active_learning_force_label(destination, profile_path=profile_path)
        kind, calculation_type = "diagnostic_static", "adsorption_static"
    else:
        metadata = build_fe110_adsorption_relaxation(destination, cores=32,
            profile_path=profile_path, screening=True, write_local_moments=True)
        kind, calculation_type = "adsorption_relaxation", "adsorption_GO"
        save_once(destination / "candidate_manifest.json", {
            "sample_id": row["sample_id"], "composition": row["composition"],
            "relaxation_stage": metadata["relaxation_stage"], "write_local_moments": True,
            "source_structure_sha256": row["structure_sha256"],
            "source_label_in_training": True, "source_magnetic_review_level": row["source_magnetic_review_level"],
            "purpose": "bounded_optimization_for_low_force_training_frames",
            "accepted_endpoint": False, "submitted": False})
    spec = (destination / "POTCAR.spec").read_text(encoding="ascii").split()
    matches = [r for r in potcars["records"] if [s.split()[1] for s in r["titles"]] == spec]
    if len(matches) != 1 or any(not s.startswith("PAW_PBE ") for s in matches[0]["titles"]):
        raise ValueError("no unique verified PAW_PBE source matching species order")
    save_once(destination / "POTCAR.metadata.json", {**matches[0],
        "contents_copied": False, "target_reverification_required": True})
    save_once(destination / "input_profile.json", metadata)
    command = [sys.executable, "-X", "utf8", str(custodian), "--mode", "validate",
        "--workdir", str(destination), "--incar", str(destination / "INCAR"),
        "--poscar", str(destination / "POSCAR"), "--calculation-type", calculation_type,
        "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
    process = subprocess.run(command, cwd=root, capture_output=True, check=False)
    (destination / "incar_custodian_validation.json").write_bytes(process.stdout)
    if process.returncode:
        (destination / "custodian_failure.txt").write_bytes(process.stderr)
        raise ValueError("custodian command failed")
    validation = json.loads(process.stdout)
    if validation["status"] != "VALIDATION_ONLY" or validation["blockers"]:
        raise ValueError("custodian found blockers")
    check = preflight(destination, kind, write_report=False)
    save_once(destination / "submission_preflight.json", check)
    if not check["passed"]:
        raise ValueError("canonical preflight failed: " + str(check["errors"]))
    record = {"sample_id": row["sample_id"], "composition": row["composition"],
        "role": role, "kind": kind, "cores": metadata["cores"],
        "structure_sha256": row["structure_sha256"], "bundle_sha256": check["bundle_sha256"],
        "input_hashes": check["files"], "incar": metadata["incar"],
        "directory": str(destination), "POTCAR_source_sha256": matches[0]["sha256"],
        "POTCAR_species_order": spec, "initial_single_point_already_exists": role != "single_points",
        "partition": "train", "new_label_magnetic_grade": "PENDING_DFT_REVIEW",
        "electronic_convergence_required": True, "per_frame_local_moment_review_required": True,
        "preflight_passed": True, "scientific_acceptance": False,
        "execution_authorized": False, "uploaded": False, "submitted": False}
    save_once(destination / "prepared_case.json", record)
    return record


def run(root, output, custodian):
    prior = root / "calculations/fe110_reico_pilot300_20261022/grouped_supplement_20261025_v1"
    for name in ["summary.json", "verification.json"]:
        if not source_file_manifest_valid(load_json_object(prior / name)):
            raise ValueError("reviewed selection source binding changed")
    proposal = load_json_object(prior / "proposals.json")
    selected = proposal["round1_new_single_points"]
    optimization = proposal["optimization_sources_already_labelled"]
    if len(selected) != 12 or len(optimization) != 2 or len({r["sample_id"] for r in selected + optimization}) != 14:
        raise ValueError("exact12+2 reviewed scope required")
    profile_path = root / "configs/true_fe110_production.yaml"
    policy_path = root / "configs/adsmind_lite/prescreen_rules.yaml"
    if yaml.safe_load(policy_path.read_text(encoding="utf-8"))["staged_relaxation"]["screening_nsw"] != 80:
        raise ValueError("reviewed80-step scheduling bound changed")
    potcar_path = prior.parent / "grouped_inputs_potcar_check_20261025_v2.json"
    potcars = load_json_object(potcar_path)
    if potcars["status"] != "METADATA_VERIFIED_AT_SOURCE_TARGET_RECHECK_REQUIRED":
        raise ValueError("source POTCAR metadata not verified")
    static, relax, sources = cost_references(root)
    output.mkdir(parents=True, exist_ok=True)
    save_once(output / "input_binding.json", {"source_files": source_file_manifest([
        Path(__file__), prior / "summary.json", prior / "verification.json", prior / "proposals.json",
        profile_path, policy_path, potcar_path, custodian, root / "scripts/vasp_inputs.py",
        root / "scripts/neb_agent/submission.py", root / "scripts/adsorption/preflight_fe110_adsorption.py",
        root / "configs/incar_custodian/project_profiles.yaml", *sources])})
    save_once(output / "cost_reference.json", {"static_references": static,
        "optimization_references": relax, "budget": budget(static, relax)})
    cases = []
    for role, rows in [("single_points", selected), ("optimizations", optimization)]:
        for row in rows:
            destination = output / role / row["sample_id"]
            try:
                cases.append(case_input(row, role, destination, profile_path, custodian, root, potcars))
            except Exception as error:
                save_once(output / ("failed_" + row["sample_id"] + ".json"), {
                    "sample_id": row["sample_id"], "error": str(error), "submitted": False})
                raise
    result = {"status": "LOCAL_INPUTS_PREPARED_NOT_SUBMITTED", "cases": cases,
        "case_counts": dict(Counter(r["role"] for r in cases)),
        "budget": budget(static, relax), "reserve_single_points_prepared": 0,
        "external_geometry_retrieval": "not introduced;reuse reviewed local geometry under method protocol2",
        "future_optimization_frames_require_fresh_QC_and_isolation": True,
        "source_POTCAR_check": potcars["checked_at_utc"],
        "target_POTCAR_and_live_headroom_check_pending": True,
        "submission_requires_explicit_authority_and_canonical_execution_gate": True,
        "no_automatic_retry_continuation_training_or_paused05_07_restart": True,
        "source_files": source_file_manifest([output / "input_binding.json", output / "cost_reference.json",
            *[Path(r["directory"]) / "prepared_case.json" for r in cases]])}
    save_once(output / "plan.json", result)
    print({k: v for k, v in result.items() if k in ["status", "case_counts", "budget"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--custodian", type=Path, required=True)
    args = parser.parse_args()
    run(args.evidence_root.resolve(), args.output.resolve(), args.custodian.resolve())
