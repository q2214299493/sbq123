"""Prepare the reviewed C2 three-arm production relaxation inputs;never submit."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import yaml

from archive.fe110_adsorption_paired_vasp3_20261020.prepare import check_pair, verify_geometry
from archive.fe110_pair2_20261027.review import post_relaxation_geometry
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid, write_json_exclusive
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_adsorption_relaxation
from scripts.workflow_geometry import minimum_image_delta_xy
from .authorize_speed import OUTPUT, PACKAGE, ROOT

DEST = OUTPUT / "c2_three_arm_dft300_v1"
PROFILE = ROOT / "configs/true_fe110_production.yaml"
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")
ARMS = ("direct_dft", "nequip_then_dft", "finetune_then_dft")


def reviewed_c2(rows):
    selected = [row for row in rows if row["name"] == "10_A"]
    if len(selected) != 2 or {row["model"] for row in selected} != {"nequip", "finetune"}:
        raise ValueError("exactly two frozen C2 model endpoints required")
    if any(row["composition"] != "C2H3" or not row["geometry_eligible_for_DFT_review"]
            or row["chemical_classification"] != "INITIAL_GRAPH_RETAINED" for row in selected):
        raise ValueError("C2 endpoint chemistry/geometry not reviewed")
    return {row["model"]: row for row in selected}


def geometry_details(source, original, rules):
    pose = read_poscar(source)
    if pose.symbols != ["Fe", "C", "H"] or pose.counts != [45, 2, 3]:
        raise ValueError("C2H3 Fe45 species/order changed")
    graph = sorted(connectivity(pose, list(range(45, 50))))
    expected = sorted(connectivity(original, list(range(45, 50))))
    if graph != expected:
        raise ValueError("C2 source graph differs from the common origin")
    post = post_relaxation_geometry(original, pose, {"final_graph": graph, "final_graph_preserved": True}, rules)
    if not post["diagnostic_DFT_geometry_ready"]:
        raise ValueError("source geometry is not eligible for DFT input preparation")
    distances = np.linalg.norm(minimum_image_delta_xy(pose.frac[:, None]-pose.frac[None]) @ pose.cell, axis=2)
    np.fill_diagonal(distances, np.inf)
    nonbonded = distances.copy()
    for a, b in graph:
        nonbonded[45+a, 45+b] = nonbonded[45+b, 45+a] = np.inf
    return {"C_C_distance_A": float(distances[45, 46]),
        "nearest_C_Fe": [{"C_index_0based": i, "Fe_index_0based": int(np.argmin(distances[i, :45])),
            "distance_A": float(distances[i, :45].min())} for i in [45, 46]],
        "nearest_H_Fe_distance_A": float(distances[47:, :45].min()),
        "minimum_nonbonded_distance_A": float(nonbonded.min()), "connectivity_local_0based": graph,
        "post_geometry": post}


def check_three_arms(destination):
    return {arm: check_pair(destination / "direct_dft", destination / arm) for arm in ARMS[1:]}


def historical_cost():
    source = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/adsorption_control_paired_vasp3_20261020_v1/runtime_evidence_20261023T115308Z/benchmark_evidence_summary_v2.json"
    rows = [row for row in load_json_object(source)["records"] if row["name"] == "10_A"]
    if len(rows) != 2 or any(row["ionic_steps"] <= 0 or row["cores"] != 32 for row in rows):
        raise ValueError("historical budget evidence schema changed")
    estimates = [row["allocated_core_hours"] / row["ionic_steps"] * 300 * 3 for row in rows]
    return {"three_job_300step_linear_core_hour_reference": [min(estimates), max(estimates)],
        "observations": [{k: row[k] for k in ["job_id", "ionic_steps", "cores", "allocated_core_hours"]} for row in rows],
        "exact_benchmark_baseline": False, "is_cost_cap_or_convergence_prediction": False, "queue_wait_included": False,
        "limitation": "Historical other starting geometries,nodes and SCF work;cost illustration only",
        "source_files": source_file_manifest([source])}


def prepare():
    if DEST.exists():
        raise FileExistsError("preserve existing three-arm preparation")
    review_path = OUTPUT / "ML_results_review.json"
    reviewed = load_json_object(review_path)
    if not source_file_manifest_valid(reviewed):
        raise ValueError("reviewed trajectory/geometry source binding changed")
    request = load_json_object(PACKAGE / "request.json")
    if reviewed["request_sha256"] != sha256_file(PACKAGE / "request.json"):
        raise ValueError("frozen model execution binding changed")
    endpoints = reviewed_c2(reviewed["cases"])
    case = next(row for row in request["scope"]["cases"] if row["name"] == "10_A")
    original_path = PACKAGE / case["seed_path"]
    if sha256_file(original_path) != case["seed_sha256"]:
        raise ValueError("common original geometry changed")
    original = read_poscar(original_path)
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    sources = {"direct_dft": original_path, **{name + "_then_dft": OUTPUT / "returned/output" / name / "10_A/seed/POSCAR" for name in endpoints}}
    for name, row in endpoints.items():
        verify_geometry(sources[name + "_then_dft"], original_path,
            {"final_POSCAR_sha256": row["final_POSCAR_sha256"], "final_graph": row["trajectory_audit"]["final_graph"]})
    geometry = {arm: geometry_details(source, original, rules) for arm, source in sources.items()}
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    if profile["routine_production"]["incar"]["EDIFFG"] != -.02 or profile["routine_production"]["incar"]["NSW"] != 300:
        raise ValueError("approved production force/step contract changed")
    DEST.mkdir()
    jobs = []
    try:
        for arm in ARMS:
            folder = DEST / arm
            folder.mkdir()
            shutil.copyfile(sources[arm], folder / "POSCAR")
            model = None if arm == "direct_dft" else arm.removesuffix("_then_dft")
            settings = build_fe110_adsorption_relaxation(folder, cores=32, screening=False, write_local_moments=True)
            metadata = {"name": "10_A_" + arm, "pair_id": "10_A_three_arm", "arm": arm, "formula": "C2H3",
                "relaxation_stage": "routine_production", "write_local_moments": True, "accepted_endpoint": False,
                "source_role": "common_original_seed_direct_DFT_control" if model is None else "work_reviewed_frozen_ML_endpoint_not_DFT_result",
                "source_POSCAR_sha256": sha256_file(sources[arm]), "common_original_seed_sha256": case["seed_sha256"],
                "model_checkpoint_sha256": request["scope"]["models"][model]["sha256"] if model else None,
                "ML_performed": model is not None, "ML_optimizer_steps": endpoints[model]["optimizer_steps"] if model else None,
                "geometry_review_sha256": sha256_file(review_path), "geometry": geometry[arm],
                "restart_policy": "new directory,no historical WAVECAR/CHGCAR or DFT output", "exposure": "historically observed10_A;not new blind test"}
            write_json_exclusive(folder / "candidate_manifest.json", metadata)
            command = [sys.executable, "-X", "utf8", str(CUSTODIAN), "--mode", "validate", "--workdir", str(folder),
                "--incar", str(folder / "INCAR"), "--poscar", str(folder / "POSCAR"), "--calculation-type", "adsorption_GO",
                "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            (folder / "custodian.stdout").write_bytes(result.stdout)
            (folder / "custodian.stderr").write_bytes(result.stderr)
            if result.returncode:
                raise ValueError("INCAR read-only validation failed:" + arm)
            custodian = json.loads(result.stdout)
            if custodian["status"] != "VALIDATION_ONLY" or custodian["blockers"]:
                raise ValueError("INCAR scientific profile blocks:" + arm)
            report = preflight(folder, "adsorption_relaxation")
            if not report["passed"]:
                raise ValueError("canonical adsorption preflight failed:" + repr(report["errors"]))
            jobs.append({"arm": arm, "path": folder.relative_to(ROOT).as_posix(), "source_path": sources[arm].relative_to(ROOT).as_posix(),
                "files": report["files"], "bundle_sha256": report["bundle_sha256"], "settings": settings, "geometry": geometry[arm],
                "source_POSCAR_sha256": metadata["source_POSCAR_sha256"], "scheduler_job_id": None, "submitted": False})
        checks = check_three_arms(DEST)
        plan = {"status": "C2_THREE_ARM_PRODUCTION_INPUTS_PREFLIGHT_PASS_NOT_SUBMITTED", "job_count": 3, "jobs": jobs,
            "method_resource_identity": checks, "budget": {"cores_each": 32, "three_jobs_total_cores": 96, "account_limit_cores": 128,
                "NSW_each": 300, "DFT_force_criterion_eV_A": .02, "LORBIT": 11, "automatic_retry_or_continuation": False},
            "cost_reference": historical_cost(), "acceptance": ["normal termination", "per-frameSCF and local/total magnetic review",
                "DFT movable fmax<=0.02eV/A", "same reviewed chemical state/site/local minimum and magnetic branch before speedup ratios"],
            "readouts": ["first same-coordinate DFT force versus saved ML force", "DFT ionicsteps to target", "totalSCF iterations",
                "VASP elapsed and allocated corehours", "ML inference and training/label amortization separately", "queue wait separately"],
            "POTCAR_policy": "POTCAR.spec only locally;recheck actual remote PAW-PBE species order and fullSHA before submission",
            "remote_input_stage": "not uploaded", "VASP_execution_authorized": False, "ALLOWED_ACTIONS": [], "uploaded": False, "submitted": False,
            "training_data_or_magnetic_grades_changed": False, "C3_included": False,
            "source_files": source_file_manifest([Path(__file__), review_path, PACKAGE / "request.json", PROFILE, rules_path,
                ROOT / "scripts/vasp_inputs.py", ROOT / "scripts/templates/sunboquan_vasp.lsf", *sources.values(),
                *[DEST / arm / filename for arm in ARMS for filename in ["POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "script.lsf", "candidate_manifest.json", "custodian.stdout", "submission_preflight.json"]]])}
        write_json_exclusive(DEST / "plan.json", plan)
    except Exception as exc:
        write_json_exclusive(DEST / "preparation_failure.json", {"error_type": type(exc).__name__, "error": str(exc), "completed_arms": [row["arm"] for row in jobs], "submitted": False})
        raise
    print({"status": plan["status"], "jobs": 3, "geometry": geometry, "budget": plan["budget"],
        "historical_core_hour_reference": plan["cost_reference"]["three_job_300step_linear_core_hour_reference"]}, flush=True)


if __name__ == "__main__":
    prepare()
