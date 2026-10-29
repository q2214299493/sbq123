"""Work-side review of every returned frame; retain originals for unsafe ML endpoints."""
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from archive.fe110_adsorption_validation_20261018.review import surface_metrics
from archive.fe110_pair2_20261027.review import audit_frames, post_relaxation_geometry
from scripts.adsorption.build_fe110_adsorption import expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_batch import molecular_signature
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.workflow_geometry import minimum_image_delta_xy
from .prepare import BASE, OUTPUT, PACKAGE, ROOT


def review_case(case, record, rules):
    directory = OUTPUT / "returned/output/finetune" / case["name"] / "seed"
    seed = read_poscar(PACKAGE / case["seed_path"])
    final = read_poscar(directory / "POSCAR")
    frames = read(directory / "optimization.traj", index=":")
    audit = audit_frames(seed, frames, final)
    post = post_relaxation_geometry(seed, final, audit, rules)
    if record["source_structure_sha256"] != case["seed_sha256"] or record["optimizer_steps"] + 1 != len(frames):
        raise ValueError("source/step binding changed")
    symbols = expanded_symbols(final)
    delta = minimum_image_delta_xy(final.frac[45:, None] - final.frac[None, :45]) @ final.cell
    nearest = np.linalg.norm(delta, axis=2).min(axis=1)
    chemistry = molecular_signature(seed) == molecular_signature(final) and audit["final_graph_preserved"]
    contacts = all(value >= {"C": 1.65, "O": 1.50, "H": 1.30}[symbol] for symbol, value in zip(symbols[45:], nearest, strict=True))
    ready = bool(post["diagnostic_DFT_geometry_ready"] and chemistry and contacts and record["error"] is None)
    selected = directory / "POSCAR" if ready else PACKAGE / case["seed_path"]
    return {**record, "name": case["name"], "composition": case["composition"], "trajectory_audit": audit,
        "post_relaxation_geometry_review": post, "exact_target_graph_retained": chemistry, "no_short_element_specific_contacts": contacts,
        "selected_for_DFT": str(selected), "selected_POSCAR_sha256": sha256_file(selected),
        "source_role": "ML_pre_relaxed" if ready else "reviewed_v5_original_fallback_not_ML_accelerated",
        "ML_endpoint_eligible": ready, "scientific_acceptance": False}


def review_results():
    request = load_json_object(PACKAGE / "request.json")
    for file in load_json_object(OUTPUT / "collection_manifest.json")["files"]:
        path = OUTPUT / "returned" / file["path"]
        if sha256_file(path) != file["sha256"]:
            raise ValueError("returned bytes changed")
    producer = load_json_object(OUTPUT / "returned/output/producer_exit_record.json")
    controller = load_json_object(OUTPUT / "returned/output/controller_exit_record.json")
    for receipt in [producer, controller]:
        if receipt["exit_code"] != 0 or receipt["request_sha256"] != sha256_file(PACKAGE / "request.json"):
            raise ValueError("bounded batch unsuccessful; preserve partial evidence")
    device = load_json_object(OUTPUT / "returned/output/finetune_device.json")
    if device["model_device"] != "cuda:0" or device["physical_gpu_uuid"] != request["scope"]["gpu_uuid"]:
        raise ValueError("wrong actual device")
    cases = load_json_object(OUTPUT / "returned/output/finetune_cases.json")
    if cases["checkpoint_sha256"] != request["scope"]["models"]["finetune"]["sha256"]:
        raise ValueError("checkpoint changed")
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))
    records = [review_case(case, record, rules) for case, record in zip(request["scope"]["cases"], cases["cases"], strict=True)]
    slab = read_poscar(BASE / "candidates_v5/POSCAR.clean_reference")
    operations = surface_pose_symmetries(slab)
    representatives, duplicates = [], []
    for row in records:
        pose = read_poscar(Path(row["selected_for_DFT"]))
        duplicate = None
        for prior in representatives:
            if prior["name"][:2] != row["name"][:2]:
                continue
            metric = surface_metrics(read_poscar(Path(prior["selected_for_DFT"])), pose, slab, operations)
            if metric["adsorbate_RMSD_A"] <= .20 and metric["movable_Fe_RMSD_A"] <= .05:
                duplicate = {"name": row["name"], "representative": prior["name"], "metrics": metric}
                break
        if duplicate:
            duplicates.append(duplicate)
        else:
            representatives.append(row)
    result = {"status": "WORK_REVIEWED_INITIAL_DFT_CANDIDATES_NOT_ACCEPTED_RESULTS", "cases": records,
        "DFT_representatives": representatives, "duplicates": duplicates,
        "GPU_elapsed_seconds": (datetime.fromisoformat(producer["finished_at"]) - datetime.fromisoformat(producer["started_at"])).total_seconds(),
        "model_checkpoint_sha256": cases["checkpoint_sha256"], "model_promoted": False,
        "domain_status": "Experimental transfer to these exact species;no calibrated per-candidate force error or energy ranking claimed",
        "source_files": source_file_manifest([PACKAGE / "request.json", OUTPUT / "collection_manifest.json", OUTPUT / "collection_receipt.json", ROOT / "configs/adsmind_lite/analysis_rules.yaml"])}
    write_json_exclusive(OUTPUT / "ML_results_review.json", result)
    print({"cases": len(records), "ML_converged": sum(row["converged"] for row in records),
        "ML_endpoint_eligible": sum(row["ML_endpoint_eligible"] for row in records), "DFT_unique": len(representatives),
        "duplicates": [row["name"] for row in duplicates], "fallbacks": [row["name"] for row in records if not row["ML_endpoint_eligible"]],
        "GPU_seconds": result["GPU_elapsed_seconds"]}, flush=True)


if __name__ == "__main__":
    review_results()
