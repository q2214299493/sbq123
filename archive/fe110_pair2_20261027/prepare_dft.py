"""Prepare four reviewed diagnostic relaxations;never upload or submit VASP."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from archive.fe110_adsorption_paired_vasp3_20261020.prepare import check_pair, verify_geometry
from archive.fe110_c3_targeted_relaxation_20261023.prepare import timing_reference
from archive.fe110_fixed53_comparison_20261027.prepare import copy_file
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_adsorption_relaxation
from .prepare import OUTPUT, PACKAGE, ROOT

DEST = OUTPUT / "dft_screen80"
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")


def cost_reference():
    c3 = timing_reference(ROOT)
    p = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/runtime_evidence_20261023T115308Z/benchmark_evidence_summary_v2.json"
    old = load_json_object(p)
    c2 = [{"job_id": r["job_id"], "observed_ionic_steps": r["ionic_steps"], "observed_elapsed_seconds": r["vasp_elapsed_seconds"],
        "observed_cores": r["cores"], "allocated_core_hours": r["allocated_core_hours"],
        "linear_80step_core_hours_reference": r["allocated_core_hours"] / r["ionic_steps"] * 80} for r in old["records"] if r["name"] == "10_A"]
    ranges = {"C2_pair": [2 * min(r["linear_80step_core_hours_reference"] for r in c2), 2 * max(r["linear_80step_core_hours_reference"] for r in c2)],
        "C3_pair": [2 * min(r["allocated_core_hours_estimate"] for r in c3), 2 * max(r["allocated_core_hours_estimate"] for r in c3)]}
    return {"C2_observations": c2, "C3_observations": c3, "pair_core_hour_references": ranges,
        "four_job_core_hour_reference_range": [sum(r[i] for r in ranges.values()) for i in [0, 1]],
        "is_cost_cap_or_prediction_of_convergence": False, "queue_wait_included": False,
        "limitations": "Historical different starts,nodes,SCF work and output settings;linear step scaling is only a budget reference",
        "source_files": source_file_manifest([p])}


def prepare():
    if DEST.exists():
        raise FileExistsError("preserve reviewed DFT preparation")
    review_path = OUTPUT / "geometry_review_v2.json"
    reviewed = load_json_object(review_path)
    request = load_json_object(PACKAGE / "request.json")
    for source in reviewed["source_files"]:
        if sha256_file(Path(source["path"])) != source["sha256"]:
            raise ValueError("upstream geometry evidence changed")
    if len(reviewed["cases"]) != 4 or any(not r["geometry_eligible_for_DFT_review"] for r in reviewed["cases"]):
        raise ValueError("four work-reviewed diagnostic geometries required")
    cases = {c["name"]: c for c in request["scope"]["cases"]}
    DEST.mkdir()
    jobs = []
    for row in reviewed["cases"]:
        model, name = row["model"], row["name"]
        folder = DEST / name / model
        source = OUTPUT / "returned/output" / model / name / "seed/POSCAR"
        verify_geometry(source, PACKAGE / cases[name]["seed_path"], {"final_POSCAR_sha256": row["final_POSCAR_sha256"], "final_graph": row["trajectory_audit"]["final_graph"]})
        copy_file(source, folder / "POSCAR")
        settings = build_fe110_adsorption_relaxation(folder, cores=32, screening=True, write_local_moments=True)
        metadata = {"name": name + "_" + model, "pair_id": name, "arm": model, "formula": cases[name]["composition"],
            "relaxation_stage": "screening", "write_local_moments": True, "source_role": "work_reviewed_ML_endpoint_diagnostic_not_DFT_result",
            "source_POSCAR_sha256": row["final_POSCAR_sha256"], "common_original_seed_sha256": cases[name]["seed_sha256"],
            "model_checkpoint_sha256": request["scope"]["models"][model]["sha256"], "ML_status": row["status"],
            "ML_optimizer_steps": row["optimizer_steps"], "ML_fmax_eV_A": row["ML_movable_fmax_eV_A"],
            "chemical_review": row["post_relaxation_geometry_review"], "geometry_review_sha256": sha256_file(review_path),
            "intact_C3_success_eligible": False if name == "C3_05" else None, "accepted_endpoint": False,
            "warning": "C3_ML_fragmented_CO_plus_C2H2;diagnostic_only;new512_ML_not_converged_at80" if name == "C3_05" else "observed10A_system;not_new_blind_test"}
        write_json_exclusive(folder / "candidate_manifest.json", metadata)
        command = [sys.executable, "-X", "utf8", str(CUSTODIAN), "--mode", "validate", "--workdir", str(folder),
            "--incar", str(folder / "INCAR"), "--poscar", str(folder / "POSCAR"), "--calculation-type", "adsorption_GO",
            "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
        result = subprocess.run(command, capture_output=True, cwd=ROOT, check=False)
        (folder / "custodian.stdout").write_bytes(result.stdout)
        (folder / "custodian.stderr").write_bytes(result.stderr)
        if result.returncode:
            raise ValueError("read-only INCAR validation failed")
        import json
        custodian = json.loads(result.stdout)
        if custodian["status"] != "VALIDATION_ONLY" or custodian["blockers"]:
            raise ValueError("INCAR custodian blocks submission")
        report = preflight(folder, "adsorption_relaxation")
        if not report["passed"]:
            raise ValueError("canonical adsorption preflight failed: " + str(report["errors"]))
        jobs.append({"name": name, "model": model, "path": folder.relative_to(ROOT).as_posix(), "settings": settings,
            "bundle_sha256": report["bundle_sha256"], "files": report["files"], "preflight_passed": True,
            "original_seed_sha256": cases[name]["seed_sha256"], "starting_chemical_fragments": row["post_relaxation_geometry_review"]["fragment_formulas_from_connectivity"],
            "scheduler_job_id": None, "submitted": False})
    pair_checks = {name: check_pair(DEST / name / "control", DEST / name / "new512") for name in cases}
    plan = {"status": "FOUR_PAIRED_DFT_SCREEN_INPUTS_READY_NOT_SUBMITTED", "job_count": 4, "jobs": jobs, "pair_checks": pair_checks,
        "budget": {"cores_each": 32, "max_concurrent_cores": 128, "NSW_each": 80, "automatic_continuation_or_retry": False,
            "force_criterion_eV_A": 0.02, "EDIFF_eV": 1e-5, "ISMEAR": 1, "SIGMA_eV": 0.20, "LORBIT": 11,
            "live_queue_and_remote_POTCAR_recheck_required": True}, "cost_reference": cost_reference(),
        "acceptance": ["normal termination", "electronic convergence", "DFT movable fmax<=0.02", "geometry and actual chemical identity", "magnetic branch compatibility and local moments", "same reviewed final minimum before cost ratio"],
        "cost_accounting": "ionic steps,SCF iteration count,VASP elapsed,allocated CPU-core-hours,queue wait separately;ML elapsed and training/label shared cost separate,never equate GPU-hours with CPU-core-hours",
        "C3_interpretation": "CO+C2H2 candidate relaxation diagnoses ML fragmentation;cannot establish intact C3 acceleration even if converged",
        "VASP_execution_authorized": False, "ALLOWED_ACTIONS": [], "uploaded": False, "submitted": False,
        "source_files": source_file_manifest([Path(__file__), review_path, PACKAGE / "request.json", ROOT / "configs/true_fe110_production.yaml"])}
    write_json_exclusive(DEST / "plan.json", plan)
    print({"status": plan["status"], "jobs": 4, "preflight_passes": 4, "core_hour_reference": plan["cost_reference"]["four_job_core_hour_reference_range"]}, flush=True)


if __name__ == "__main__":
    prepare()
