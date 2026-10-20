"""Bounded same-seed and DFT-minimum geometry comparison; no fitting or VASP."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

import numpy as np

from archive.fe110_adsorption_calibration_20261018.prepare_current_trajectories import check_inputs
from archive.fe110_adsorption_calibration_20261018.reviewed_trajectory_helpers import verify_frame
from archive.fe110_adsorption_pool_rebuild_20261019.prepare_pool import source_records, verified_collection
from archive.fe110_adsorption_validation_20261018.review import surface_metrics
from archive.fe110_adsorption_validation_20261018.runtime import load_atoms, local_path, verify
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity, surface_pose_symmetries
from scripts.aqcat25_handoff import validate_handoff
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.workflow_geometry import minimum_image_delta_xy

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
POOL = BASE / "adsorption_pool_rebuild_20261019_v1/prepared_v2"
DEST = BASE / "adsorption_control_geometry3_20261020_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/" + DEST.name
NAMES = ("06_C", "09_C", "10_A")
USER_REQUEST = "做少量同起点预松弛对照，检查构型保持，再判断能否真正减少VASP步数。"


def source_case(record: dict) -> dict:
    name = record["name"]
    folder = verified_collection(record)
    if folder is None:
        raise ValueError("no verified closed-source collection")
    source = load_json_object(folder / "source.json")
    if not source["normal_completion"] or not source["ionic_converged"]:
        raise ValueError("reference is not an ionically converged VASP run")
    inputs = POOL / "sources" / name
    check_inputs(inputs, record)
    reference = inputs / "CONTCAR"
    expected = hashlib.sha256(base64.b64decode(source["files"]["CONTCAR"], validate=True)).hexdigest()
    if sha256_file(reference) != expected:
        raise ValueError("reference CONTCAR source bytes changed")
    final = max(source["frames"], key=lambda row: row["ionic_step"])
    if final["ionic_step"] != source["total_steps"] or not final["EDIFF_marker_before_force"]:
        raise ValueError("reference final electronic cycle unverified")
    forces = verify_frame(load_atoms(reference), final)
    fmax = float(np.linalg.norm(forces[18:], axis=1).max())
    if fmax > .0200001:
        raise ValueError("reference final movable force not converged")
    seed = BASE / "gpu_direct_v3" / name / "POSCAR"
    handoff = BASE / "gpu_direct_v3" / name / "handoff.json"
    manifest = load_json_object(BASE / "gpu_direct_v3/batch_manifest.json")
    binding = {row["path"]: row["sha256"] for row in manifest["files"]}
    for path in (seed, handoff):
        if sha256_file(path) != binding[name + "/" + path.name]:
            raise ValueError("historical same-seed handoff changed")
    validate_handoff(handoff)
    if sha256_file(seed) != sha256_file(BASE / "candidates_v2" / name / "POSCAR"):
        raise ValueError("raw seed differs from original constructed geometry")
    poses = [read_poscar(p) for p in (seed, reference)]
    graphs = [sorted(connectivity(p, list(range(45, len(p.frac))))) for p in poses]
    return {"name": name, "source_VASP_job_id": record["job_id"], "source_OUTCAR_sha256": source["OUTCAR_sha256"],
        "source_collection": {"path": (folder / "source.json").relative_to(ROOT).as_posix(),
                              "sha256": sha256_file(folder / "source.json")},
        "seed_source_path": seed.relative_to(ROOT).as_posix(), "seed_sha256": sha256_file(seed),
        "reference_source_path": reference.relative_to(ROOT).as_posix(), "reference_sha256": expected,
        "reference_force_eV_A": fmax, "reference_ionic_steps": source["total_steps"],
        "seed_graph": graphs[0], "DFT_graph": graphs[1], "DFT_same_graph_as_seed": graphs[0] == graphs[1],
        "role": "observed_diagnostic_geometry_comparison_not_blind_model_selection",
        "training_trajectory": name == "06_C", "same_raw_seed_as_historical_VASP_start": sha256_file(seed) == sha256_file(inputs / "POSCAR")}


def prepare() -> None:
    previous = BASE / "adsorption_control_heldout46_20261020_v1"
    receipt = load_json_object(previous / "validation_receipt.json")
    prior = load_json_object(previous / "validation_request.json")
    if (receipt["status"] != "FROZEN46_FORCE_TEST_VERIFIED_GEOMETRY_AND_SPEEDUP_UNTESTED"
            or receipt["request_sha256"] != sha256_file(previous / "validation_request.json")
            or receipt["candidate_sha256"] != prior["models"]["candidate"]["sha256"]):
        raise ValueError("frozen candidate force evidence changed")
    records = {r["name"]: r for r in source_records()}
    cases = [source_case(records[name]) for name in NAMES]
    DEST.mkdir(exist_ok=False)
    artifacts = []

    def copy(path: Path, relative: str) -> str:
        target = local_path(DEST, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        shutil.copyfile(path, target)
        artifacts.append({"path": relative, "sha256": sha256_file(target)})
        return relative

    for case in cases:
        case["seed_path"] = copy(ROOT / case["seed_source_path"], "geometry/" + case["name"] + "/seed.vasp")
        case["reference_path"] = copy(ROOT / case["reference_source_path"], "geometry/" + case["name"] + "/DFT_CONTCAR")
    copy(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR", "geometry/clean_Fe45_CONTCAR")
    source_path = DEST / "evidence/geometry_sources.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_exclusive(source_path, {"document_kind": "frozen_geometry_comparison_sources", "geometry_cases": cases,
        "splits": {"heldout": []}, "force_predictions_repeated": 0, "previous_force_receipt_sha256": sha256_file(previous / "validation_receipt.json")})
    artifacts.append({"path": "evidence/geometry_sources.json", "sha256": sha256_file(source_path)})
    policy = copy(ROOT / "configs/execution_backends.yaml", "backend_policy.yaml")
    runtime = ROOT / "archive/fe110_adsorption_validation_20261018"
    for name in ("runtime.py", "validation_helpers.py"):
        copy(runtime / name, "runtime/" + name)
    request = {"document_kind": "adsorption_frozen_checkpoint_gpu_validation", "schema_version": 1,
        "run_id": "direct-fe110-adsorption-control-geometry3-20261020-v1", "remote_root": REMOTE,
        "exception_id": "fe110_adsorption_control_geometry3_20261020", "execution_mode": "direct_no_scheduler",
        "scheduler_job_id": None, "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da",
        "max_wall_seconds": 1200, "models": prior["models"], "heldout": [], "geometry_cases": cases,
        "limits": {"seed_max_steps": 80, "minimum_drift_max_steps": 20, "fmax_eV_per_A": .10, "minimum_drift_fmax_eV_A": .02},
        "source_manifest_path": "evidence/geometry_sources.json", "source_manifest_sha256": sha256_file(source_path),
        "policy": {"path": policy, "sha256": sha256_file(DEST / policy)}, "artifacts": artifacts,
        "comparison": "same3 original raw seeds and same3 exact converged DFT structures;no motif restraints;no force-test rerun",
        "scientific_boundaries": {"training": False, "new_VASP": False, "energy_ranking": False,
            "default_model_change": False, "heldout_model_reselection": False, "measured_speedup": False}}
    path = DEST / "validation_request.json"
    write_json_exclusive(path, request)
    write_json_exclusive(DEST / "submission_authorization.json", {"action": "RUN_GPU_ADSORPTION_FROZEN_VALIDATION",
        "user_request": USER_REQUEST, "user_authorized": True, "request_sha256": sha256_file(path),
        "scope": "one3-case baseline/control same-seed and minimum-drift batch;12short runs;1200s;no retries/training/VASP"})
    verify(path, DEST / "submission_authorization.json")
    with tarfile.open(DEST / "validation_bundle.tar", "x") as handle:
        for name in [r["path"] for r in artifacts] + ["validation_request.json", "submission_authorization.json"]:
            handle.add(DEST / name, arcname=name, recursive=False)
    write_json_exclusive(DEST / "preparation_receipt.json", {"request_sha256": sha256_file(path), "cases": list(NAMES),
        "optimizer_runs": 12, "maximum_total_optimizer_steps": 600, "max_wall_seconds": 1200,
        "source": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha256_file(Path(__file__))},
        "bundle_sha256": sha256_file(DEST / "validation_bundle.tar"), "model_executed": False})
    print(json.dumps({"status": "LOCAL_GEOMETRY_PACKAGE_PASS", "request_sha256": sha256_file(path), "cases": list(NAMES),
                      "DFT_reference_forces": {c["name"]: c["reference_force_eV_A"] for c in cases}}))


def pair_distances(pose) -> list:
    delta = minimum_image_delta_xy(pose.frac[:, None, :] - pose.frac[None, :, :]) @ pose.cell
    distances = np.linalg.norm(delta, axis=2)
    symbols = expanded_symbols(pose)
    return [{"i_0based": i, "j_0based": j, "pair": symbols[i]+"-"+symbols[j], "distance_A": float(distances[i, j])}
            for i in range(45, len(symbols)) for j in range(i+1, len(symbols))]


def same_graph(first, second) -> bool:
    """JSON lists and in-memory tuple edges denote the same chemical graph."""
    return sorted(tuple(edge) for edge in first) == sorted(tuple(edge) for edge in second)


def review(output_name="geometry_comparison_review.json") -> None:
    request_path = DEST / "validation_request.json"
    request = verify(request_path, DEST / "submission_authorization.json")
    returned = DEST / "returned"
    for entry in load_json_object(returned / "return_manifest.json")["files"]:
        if sha256_file(local_path(returned, entry["path"])) != entry["sha256"]:
            raise ValueError("returned bytes changed")
    producer = load_json_object(returned / "output/producer_exit_record.json")
    if producer["exit_code"] or producer["request_sha256"] != sha256_file(request_path):
        raise ValueError("producer failed or request stale;preserve partial evidence")
    slab = read_poscar(DEST / "geometry/clean_Fe45_CONTCAR")
    operations = surface_pose_symmetries(slab)
    rows = []
    for model in request["models"]:
        device = load_json_object(returned / "output" / (model + "_device.json"))
        if not device["model_device"].startswith("cuda") or device["physical_gpu_uuid"] != request["gpu_uuid"]:
            raise ValueError("model not on authorized CUDA device")
        for case in request["geometry_cases"]:
            reference, seed = [read_poscar(DEST / case[key]) for key in ("reference_path", "seed_path")]
            for origin in ("seed", "minimum"):
                folder = returned / "output" / model / case["name"] / origin
                result = load_json_object(folder / "case_record.json")
                start = case["seed_path"] if origin == "seed" else case["reference_path"]
                if result["source_structure_sha256"] != sha256_file(DEST / start):
                    raise ValueError("optimization did not start at exact paired structure")
                final = read_poscar(folder / "POSCAR")
                geometry = surface_metrics(reference, final, slab, operations)
                initial = seed if origin == "seed" else reference
                displacement = minimum_image_delta_xy(final.frac[:18]-initial.frac[:18]) @ initial.cell
                if np.abs(displacement).max() > 1e-10:
                    raise ValueError("fixed layer moved")
                rows.append({"name": case["name"], "model": model, "origin": origin, **result, **geometry,
                    "same_graph_as_seed": same_graph(connectivity(final, list(range(45, len(final.frac)))), case["seed_graph"]),
                    "adsorbate_pair_distances": pair_distances(final), "final_POSCAR_sha256": sha256_file(folder / "POSCAR")})
    report = {"status": "GEOMETRY_COMPARISON_COMPLETE_NOT_MODEL_PROMOTION", "request_sha256": sha256_file(request_path),
        "models": request["models"], "producer": producer, "geometry": rows, "source_cases": request["geometry_cases"],
        "analysis_source_sha256": sha256_file(Path(__file__)),
        "geometry_metric": "clean-slab face symmetries,xyPBC,graph-equivalent H;no molecular COM/height/Kabsch fit",
        "limits": ["06_C is a training-trajectory diagnostic;09_C/10_A now observed,not a fresh blind model-selection test",
            "DFT runs started at historical ML outputs,not the original raw seeds;their old step counts are not a matched no-GPU control",
            "20-step minimum drift is bounded stationarity evidence,not proof of basin stability",
            "ML forces and geometry proximity do not prove actual VASP step/time savings"],
        "training_performed": False, "new_VASP": False, "model_promoted": False, "measured_speedup": False}
    write_json_exclusive(local_path(DEST, output_name), report)
    keys = ("name", "model", "origin", "status", "optimizer_steps", "ML_movable_fmax_eV_A", "adsorbate_RMSD_A",
            "movable_Fe_RMSD_A", "same_graph_as_DFT", "same_graph_as_seed")
    print(json.dumps([{k: r.get(k) for k in keys} for r in rows]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "review"))
    parser.add_argument("--review-output", default="geometry_comparison_review.json")
    args = parser.parse_args()
    if args.action == "review":
        review(args.review_output)
    else:
        prepare()
