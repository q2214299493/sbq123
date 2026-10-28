"""Audit all four returned ML paths;no inference,DFT or model promotion."""
from datetime import datetime
from pathlib import Path

import numpy as np
from ase.io import read
import yaml

from archive.fe110_pair2_20261027.review import audit_frames, post_relaxation_geometry
from archive.fe110_pair2_20261027.runtime import verify
from archive.fe110_adsorption_validation_20261018.review import surface_metrics
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .authorize_speed import OUTPUT, PACKAGE, POLICY, ROOT


def review_results():
    request, _, scope = verify(PACKAGE / "request.json")
    if sha256_file(POLICY) != request["policy"]["sha256"]:
        raise ValueError("canonical execution policy binding changed")
    returned = OUTPUT / "returned"
    manifest = load_json_object(OUTPUT / "final_manifest.json")
    for row in manifest["files"]:
        path = returned / row["path"]
        if path.stat().st_size != row["bytes"] or sha256_file(path) != row["sha256"]:
            raise ValueError("returned artifact bytes changed")
    producer = load_json_object(returned / "output/producer_exit_record.json")
    controller = load_json_object(returned / "output/controller_exit_record.json")
    if any(row["exit_code"] != 0 or row["request_sha256"] != sha256_file(PACKAGE / "request.json") for row in [producer, controller]):
        raise ValueError("four-arm producer/controller did not finish normally")
    elapsed = (datetime.fromisoformat(producer["finished_at"])-datetime.fromisoformat(producer["started_at"])).total_seconds()
    if not 0 < elapsed <= scope["max_wall_seconds"]:
        raise ValueError("actual producer duration exceeds authorized budget")
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    records, finals, sources = [], {}, []
    for model, checkpoint in scope["models"].items():
        device = load_json_object(returned / "output" / (model + "_device.json"))
        if device["model_device"] != "cuda:0" or device["physical_gpu_uuid"] != scope["gpu_uuid"]:
            raise ValueError("actual model CUDA placement mismatch")
        payload = load_json_object(returned / "output" / (model + "_cases.json"))
        if payload["checkpoint_sha256"] != checkpoint["sha256"]:
            raise ValueError("candidate was reselected")
        for case, record in zip(scope["cases"], payload["cases"], strict=True):
            directory = returned / "output" / model / case["name"] / "seed"
            seed_path, final_path = PACKAGE / case["seed_path"], directory / "POSCAR"
            seed, final = read_poscar(seed_path), read_poscar(final_path)
            frames = read(directory / "optimization.traj", index=":")
            symbols = read(seed_path, format="vasp").get_chemical_symbols()
            if any(frame.get_chemical_symbols() != symbols for frame in frames):
                raise ValueError("trajectory species/order changed")
            audit = audit_frames(seed, frames, final)
            scalar_fmax = max(sum(float(v)**2 for v in force)**.5 for force in frames[-1].get_forces(apply_constraint=False)[18:])
            if (record["name"] != case["name"] or record["source_structure_sha256"] != case["seed_sha256"]
                    or record["error"] is not None or record["optimizer_steps"]+1 != len(frames)
                    or record["optimizer_steps"] > scope["limits"]["seed_max_steps"]
                    or audit["maximum_adjacent_atom_displacement_A"] > scope["limits"]["LBFGS_maxstep_A"]+1e-8
                    or not np.isclose(scalar_fmax, record["ML_movable_fmax_eV_A"], rtol=1e-6)):
                raise ValueError("optimizer/source/trajectory/raw-force receipt mismatch")
            post = post_relaxation_geometry(seed, final, audit, rules)
            fragments = post["fragment_formulas_from_connectivity"]
            chemistry = "INITIAL_GRAPH_RETAINED" if audit["final_graph_preserved"] else "FRAGMENTED" if len(fragments)>1 else "CONNECTED_GRAPH_REARRANGED"
            records.append({"model": model, **record, "composition": case["composition"], "trajectory_audit": audit,
                "independent_scalar_fmax_eV_A": scalar_fmax, "chemical_classification": chemistry,
                "post_relaxation_geometry_review": post, "final_POSCAR_sha256": sha256_file(final_path),
                "geometry_eligible_for_DFT_review": post["diagnostic_DFT_geometry_ready"], "DFT_validated": False})
            finals[(model, case["name"])] = final
            sources += [seed_path, final_path, directory / "optimization.traj", directory / "case_record.json"]
    care_path = ROOT / "calculations/fe110_care8_isomers_20260716/candidate_manifest.json"
    care = load_json_object(care_path)
    slab_path = ROOT / care["source_slab"]
    if sha256_file(slab_path) != care["source_slab_sha256"]:
        raise ValueError("symmetry reference slab changed")
    slab = read_poscar(slab_path)
    operations = surface_pose_symmetries(slab)
    geometry = {case["name"]: surface_metrics(finals[("nequip", case["name"])], finals[("finetune", case["name"])], slab, operations) for case in scope["cases"]}
    for values in geometry.values():
        values["same_graph_between_ML_models"] = values.pop("same_graph_as_DFT")
    result = {"status": "FOUR_ML_PATHS_RETURNED_AUDITED_NOT_DFT_VALIDATED", "request_sha256": sha256_file(PACKAGE / "request.json"),
        "cases": records, "ML_final_geometry_comparison": geometry, "producer_elapsed_seconds": elapsed,
        "optimizer_steps_total": sum(row["optimizer_steps"] for row in records), "frames_total": sum(row["trajectory_audit"]["frames"] for row in records),
        "returned_artifacts_verified": len(manifest["files"]), "training_or_DFT_performed": False, "model_promoted": False,
        "DFT_convergence_or_acceleration_established": False, "original_data_isolation_and_magnetic_grades_preserved": True,
        "source_files": source_file_manifest([Path(__file__), PACKAGE / "request.json", OUTPUT / "final_manifest.json", OUTPUT / "collection_receipt.json",
            returned / "output/producer_exit_record.json", returned / "output/controller_exit_record.json", rules_path, care_path, slab_path, *sources])}
    write_json_exclusive(OUTPUT / "ML_results_review.json", result)
    print({"status": result["status"], "seconds": elapsed, "frames": result["frames_total"], "steps": result["optimizer_steps_total"],
        "cases": [{"model": r["model"], "name": r["name"], "steps": r["optimizer_steps"], "ML_fmax": r["ML_movable_fmax_eV_A"],
            "chemistry": r["chemical_classification"], "fragments": r["post_relaxation_geometry_review"]["fragment_formulas_from_connectivity"],
            "DFT_geometry_review_eligible": r["geometry_eligible_for_DFT_review"]} for r in records], "geometry": geometry}, flush=True)


if __name__ == "__main__":
    review_results()
