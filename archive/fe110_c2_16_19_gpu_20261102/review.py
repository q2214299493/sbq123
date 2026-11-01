"""Review immutable GPU trajectories locally and create schema-v2 return handoffs."""
from datetime import datetime
from pathlib import Path

from ase.io import read
from jsonschema import Draft202012Validator
import yaml

from archive.fe110_11_15_gpu_20261029 import review as previous
from archive.fe110_adsorption_validation_20261018.review import surface_metrics
from archive.fe110_pair2_20261027.review import audit_frames, post_relaxation_geometry
from scripts.adsorption.build_fe110_adsorption import read_poscar, expanded_symbols
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive

from .prepare import BASE, OUTPUT, PACKAGE, ROOT


def verified_inputs():
    request = load_json_object(PACKAGE / "request.json")
    for item in load_json_object(OUTPUT / "collection_manifest.json")["files"]:
        if sha256_file(OUTPUT / "returned" / item["path"]) != item["sha256"]:
            raise ValueError("returned bytes changed")
    producer_path = OUTPUT / "returned/output/producer_exit_record.json"
    producer = load_json_object(producer_path)
    controller = load_json_object(OUTPUT / "returned/output/controller_exit_record.json")
    for record in (producer, controller):
        if record["exit_code"] != 0 or record["request_sha256"] != sha256_file(PACKAGE / "request.json"):
            raise ValueError("successful bounded production not established")
    device = load_json_object(OUTPUT / "returned/output/finetune_device.json")
    if device["model_device"] != "cuda:0" or device["physical_gpu_uuid"] != request["scope"]["gpu_uuid"]:
        raise ValueError("actual CUDA placement is not the authorized physical GPU")
    payload = load_json_object(OUTPUT / "returned/output/finetune_cases.json")
    if payload["checkpoint_sha256"] != request["scope"]["models"]["finetune"]["sha256"]:
        raise ValueError("model changed")
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text())
    return request, producer_path, producer, payload, rules_path, rules


def review_results():
    if (OUTPUT / "ML_results_review.json").exists():
        raise FileExistsError("preserve the existing result review")
    previous.OUTPUT, previous.PACKAGE = OUTPUT, PACKAGE
    request, producer_path, producer, payload, rules_path, rules = verified_inputs()
    records, frames_by_name = [], {}
    for case, record in zip(request["scope"]["cases"], payload["cases"], strict=True):
        if case["name"] != record["name"]:
            raise ValueError("case ordering changed")
        directory = OUTPUT / "returned/output/finetune" / case["name"] / "seed"
        seed, final = read_poscar(PACKAGE / case["seed_path"]), read_poscar(directory / "POSCAR")
        frames = read(directory / "optimization.traj", index=":")
        if expanded_symbols(seed) != expanded_symbols(final) or any(f.get_chemical_symbols() != expanded_symbols(seed) for f in frames):
            raise ValueError("atom identities/order changed")
        frames_by_name[case["name"]] = frames
        try:
            row = previous.review_case(case, record, rules)
        except ValueError as error:
            audit = audit_frames(seed, frames, final)
            post = post_relaxation_geometry(seed, final, audit, rules)
            row = {**record, "name": case["name"], "composition": case["composition"],
                "trajectory_audit": audit, "post_relaxation_geometry_review": post,
                "exact_target_graph_retained": False, "ML_endpoint_eligible": False,
                "selected_for_DFT": str(PACKAGE / case["seed_path"]), "selected_POSCAR_sha256": case["seed_sha256"],
                "source_role": "reviewed_v2_original_fallback_not_ML_accelerated", "review_error": str(error),
                "scientific_acceptance": False}
        if not row["ML_endpoint_eligible"]:
            row["source_role"] = "reviewed_v2_original_fallback_not_ML_accelerated"
        records.append(row)
    source = load_json_object(BASE / "review_ready_v2/candidate_review.json")
    slab = read_poscar(Path(source["source_slab"]))
    ops = surface_pose_symmetries(slab)
    representatives, duplicates = [], []
    for row in records:
        pose = read_poscar(Path(row["selected_for_DFT"]))
        duplicate = None
        for prior in representatives:
            if prior["name"][:2] != row["name"][:2]:
                continue
            metric = surface_metrics(read_poscar(Path(prior["selected_for_DFT"])), pose, slab, ops)
            if metric["adsorbate_RMSD_A"] <= .20 and metric["movable_Fe_RMSD_A"] <= .05:
                duplicate = {"name": row["name"], "representative": prior["name"], "metrics": metric}
                break
        (duplicates if duplicate else representatives).append(duplicate if duplicate else row)
    # This adapter names the real direct process, not a fictitious scheduler job.
    exit_path = OUTPUT / "producer_exit_handoff_adapter.json"
    exit_document = {"gpu_job_id": "direct_process:" + str(producer["pid"]),
        "exit_code": producer["exit_code"], "scheduler_job_id": None,
        "native_exit_record_path": str(producer_path), "native_exit_record_sha256": sha256_file(producer_path)}
    if exit_path.exists():
        if load_json_object(exit_path) != exit_document:
            raise ValueError("preserve changed producer adapter")
    else:
        write_json_exclusive(exit_path, exit_document)
    handoffs = []
    schema = load_json_object(PACKAGE / "handoff.schema.json")
    for row in records:
        name = row["name"]
        original_path = PACKAGE / "handoffs" / (name + ".json")
        original = load_json_object(original_path)
        candidate = OUTPUT / "returned/output/finetune" / name / "seed/POSCAR"
        pose = read_poscar(candidate)
        symbols = expanded_symbols(pose)
        document = {k: original[k] for k in ("schema_version", "handoff_id", "workflow_kind", "source_workflow_sha256", "adsorption", "restrictions")}
        document.update(direction="gpu_to_work", source_handoff={"path": original_path.relative_to(OUTPUT).as_posix(), "sha256": sha256_file(original_path)},
            candidate_structure={"path": candidate.relative_to(OUTPUT).as_posix(), "sha256": sha256_file(candidate), "format": "vasp_poscar",
                "atom_count": len(symbols), "atom_order_sha256": atom_order_sha256(symbols)},
            producer={"backend": "aqcat_gpu", "hostname": "MZ73", "gpu_job_id": "direct_process:" + str(producer["pid"]),
                "model_identifier": original["model"]["identifier"], "checkpoint_sha256": payload["checkpoint_sha256"]},
            result={"result_class": "predicted_adsorption_candidate_only", "optimizer_status": "converged" if row["converged"] else "unfinished",
                "optimizer_steps": row["optimizer_steps"], "predicted_energy": {"value": float(frames_by_name[name][-1].get_potential_energy()), "unit": "eV", "reportable_dft": False},
                "predicted_force": {"fmax": row["ML_movable_fmax_eV_A"], "unit": "eV/A", "reportable_dft": False},
                "geometry_before": {"source_POSCAR_sha256": row["source_structure_sha256"]}, "geometry_after": row["post_relaxation_geometry_review"],
                "connectivity_status": "pass" if row["exact_target_graph_retained"] else "fail",
                "structure_invariants": {"atom_order_preserved": True, "cell_preserved": True, "fixed_atoms_preserved": True}},
            domain_assessment={"calibration_id": None, "status": "out_of_domain", "method": "explicit_scope_atom_count_and_checkpoint_review",
                "reasons": ["Seven/eight adsorbate atoms exceed the existing 2-6 atom calibration scope.", "Frozen partial snapshot is not calibrated for these isomers;no ranking/uncertainty claim."]},
            producer_exit_record={"path": exit_path.relative_to(OUTPUT).as_posix(), "sha256": sha256_file(exit_path), "status": "success", "exit_code": 0,
                "evidence_class": "producer_process_only_not_scheduler_accounting"})
        Draft202012Validator(schema).validate(document)
        path = OUTPUT / "returned_handoffs_v2" / (name + ".json")
        path.parent.mkdir(exist_ok=True)
        write_json_exclusive(path, document)
        validate_handoff(path, root=OUTPUT, schema_path=PACKAGE / "handoff.schema.json")
        handoffs.append(path)
    result = {"status": "WORK_REVIEWED_CANDIDATES_NOT_ACCEPTED_RESULTS", "cases": records, "DFT_representatives": representatives,
        "duplicates": duplicates, "model_checkpoint_sha256": payload["checkpoint_sha256"], "model_promoted": False,
        "GPU_elapsed_seconds": (datetime.fromisoformat(producer["finished_at"]) - datetime.fromisoformat(producer["started_at"])).total_seconds(),
        "domain_status": request["domain"], "return_handoffs_validated": len(handoffs),
        "recovered_metadata_failure": "v1 used display backend instead of schema enum aqcat_gpu;invalid payload preserved, no model rerun",
        "source_files": source_file_manifest([PACKAGE / "request.json", OUTPUT / "collection_manifest.json", OUTPUT / "collection_receipt.json", rules_path] + handoffs)}
    write_json_exclusive(OUTPUT / "ML_results_review.json", result)
    print({"cases": len(records), "ML_endpoint_eligible": sum(r["ML_endpoint_eligible"] for r in records),
        "unique_selected_poses": len(representatives), "duplicates": duplicates,
        "fallbacks": [r["name"] for r in records if not r["ML_endpoint_eligible"]], "return_handoffs_validated": len(handoffs)}, flush=True)


if __name__ == "__main__":
    review_results()
