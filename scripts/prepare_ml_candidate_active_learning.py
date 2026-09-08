"""Join reviewed NEB/Sella candidates to the existing MatRIS/VASP learning loop."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.dual_model_ml_neb import _geometry_guard_evidence, _load_request
from scripts.ml_candidate_source import _structure_row, load_candidate_path
from scripts.matris_sella_local_peak import candidate_geometry, validate_candidate_entry
from scripts.dual_model_ts_force_prediction_batch import validate_request
from scripts.prepare_dual_model_ts_active_learning_round import _safe_snapshot_file


def _binding(path):
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def _reviewed_source(source_request_path, manifest_path, review_path):
    request = _load_request(source_request_path)
    manifest = load_json_object(manifest_path)
    review = load_json_object(review_path)
    if (manifest.get("document_kind") != "dual_model_gpu_ml_neb_path_manifest"
            or manifest.get("source_request", {}).get("sha256") != sha256_file(source_request_path)
            or manifest.get("models") != request["models"]
            or manifest.get("reaction") != request["reaction"]):
        raise ValueError("candidate manifest source/model/reaction binding mismatch")
    if (review.get("document_kind") != "dual_model_candidate_work_review"
            or review.get("candidate_manifest_sha256") != sha256_file(manifest_path)
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
            or review.get("decision") != "accepted_for_force_diagnosis_only"):
        raise ValueError("a hash-bound work candidate review is required")
    if manifest.get("geometry_guards", {}).get("passed") is not True:
        raise ValueError("candidate path did not pass geometry gates")
    return request, manifest


def _sella_result(request, manifest, manifest_path, source_request_path):
    ref = manifest.get("sella_refinement", {})
    if ref.get("status") not in {"needs_work_review", "optimizer_not_converged", "budget_exhausted"}:
        raise ValueError("Sella branch has no reviewable result")
    sella_path = _safe_snapshot_file(manifest_path.parent, ref["path"])
    if sha256_file(sella_path) != ref["sha256"]:
        raise ValueError("Sella manifest changed")
    sella = load_json_object(sella_path)
    source = sella.get("source", {})
    if (sella.get("document_kind") != "ml_sella_candidate_manifest"
            or sella.get("status") != ref["status"]
            or source.get("checkpoint_sha256") != request["models"]["primary"]["checkpoint_sha256"]
            or source.get("source_request_sha256") != sha256_file(source_request_path)):
        raise ValueError("Sella checkpoint/source binding mismatch")
    peak = int(source["peak_image"])
    images = manifest["images"]
    if not 0 < peak < len(images) - 1 or source["seed_structure_sha256"] != images[peak]["structure_sha256"]:
        raise ValueError("Sella seed binding mismatch")
    if "local_peak_entry" in manifest or source.get("entry_mode") == "reviewed_rough_local_peak":
        validate_candidate_entry(manifest, manifest_path, sella)
    last = sella.get("last_valid_structure")
    if not isinstance(last, dict):
        raise ValueError("Sella branch has no last valid structure for diagnosis")
    return peak, last, sella_path



def prepare_candidate_round(source_request_path, manifest_path, review_path, policy_path, destination, *, method):
    """New state starts at the current checkpoint; no model or strategy reset."""
    if method not in {"ml_neb", "ml_neb_sella"}:
        raise ValueError("method must be ml_neb or ml_neb_sella")
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")
    request, manifest = _reviewed_source(source_request_path, manifest_path, review_path)
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if policy.get("workflow_kind") != "matris_primary_aqcat25_secondary_ts_active_learning":
        raise ValueError("wrong active-learning policy")
    round_index = request.get("active_learning_round", 0)
    if type(round_index) is not int or not 0 <= round_index < policy["round_control"]["maximum_rounds"]:
        raise ValueError("active-learning round budget exceeded or invalid")
    atoms, rows = load_candidate_path(request, manifest, manifest_path, source_request_path, method=method)
    bindings = {"source_request": _binding(source_request_path), "candidate_manifest": _binding(manifest_path),
                "candidate_review": _binding(review_path), "policy": _binding(policy_path)}
    if method == "ml_neb_sella":
        peak, last, sella_path = _sella_result(request, manifest, manifest_path, source_request_path)
        path = _safe_snapshot_file(sella_path.parent, last["path"])
        trial = list(atoms)
        trial[peak], row = _structure_row(path, last["sha256"], "sella_final", f"{peak:02d}",
                                          "near_saddle", method, atoms[0])
        rows.append(row)
        if _geometry_guard_evidence(trial, request).get("passed") is not True:
            raise ValueError("Sella result failed recomputed parent path geometry gates")
        bindings["sella_manifest"] = _binding(sella_path)
        if "local_peak_entry" in manifest:
            sella = load_json_object(sella_path)
            entry, parent_images, _ = validate_candidate_entry(manifest, manifest_path, sella)
            if not candidate_geometry(trial[peak], parent_images, request, entry["segment"], entry["limits"])["passed"]:
                raise ValueError("Sella result exceeded reviewed local-search geometry limits")
            bindings["local_peak_entry"] = _binding((manifest_path.parent / manifest["local_peak_entry"]["path"]).resolve())
    models = {role: {"backend": item["backend"], "identifier": item.get("identifier"),
                     "checkpoint_path": item["remote_checkpoint_path"], "checkpoint_sha256": item["checkpoint_sha256"]}
              for role, item in request["models"].items()}
    destination.mkdir(parents=True)
    (destination / "structures").mkdir()
    for row in rows:
        source = row.pop("source_path")
        target = destination / row["path"]
        shutil.copy2(source, target)
        if sha256_file(target) != row["sha256"]:
            raise ValueError("source structure changed while copying")
    batch = {"schema_version": 1, "document_kind": "dual_model_ts_path_force_prediction_batch_request",
             "reaction_id": request["reaction"]["reaction_id"], "round_index": round_index,
             "source": {"candidate_manifest_sha256": sha256_file(manifest_path), "candidate_method": method},
             "models": models, "structures": rows,
             "indexed_bond_changes": request["reaction"]["indexed_bond_changes"],
             "fixed_atom_indices_zero_based": request["fixed_atom_indices_zero_based"],
             "automatic_vasp_submission": False}
    batch_path = destination / "dual_model_prediction_batch_request.json"
    write_json_atomic(batch_path, batch)
    validate_request(batch_path)
    state = {"schema_version": 1, "document_kind": "dual_model_ts_active_learning_state",
             "workflow_kind": policy["workflow_kind"], "reaction_id": batch["reaction_id"], "round_index": round_index,
             "candidate_method": method, "status": "awaiting_exact_dual_model_gpu_predictions",
             "source_bindings": bindings,
             "round_trigger": {"model_error_assumed": False, "failure_boundary_pairs": []},
             "prediction_batch": {**_binding(batch_path), "sample_count": len(rows), "status": "prepared_not_submitted"},
             "required_next_stages": ["exact_predictions", "compatible_VASP_labels", "model_specific_VASP_error",
                                      "fine_tune_only_if_error_gate_fails", "new_checkpoint_complete_path_rerun",
                                      "repeat_Sella_if_selected", "disjoint_heldout_validation"],
             "scientific_status": "candidate_diagnosis_prepared_not_calibrated",
             "automatic_submission": False, "automatic_vasp_submission": False}
    write_json_atomic(destination / "active_learning_state.json", state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-request", "manifest", "review", "policy", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--method", choices=["ml_neb", "ml_neb_sella"], required=True)
    args = parser.parse_args()
    state = prepare_candidate_round(args.source_request, args.manifest, args.review, args.policy,
                                    args.destination, method=args.method)
    print(json.dumps({"status": state["status"], "samples": state["prediction_batch"]["sample_count"],
                      "jobs_submitted": 0}))


if __name__ == "__main__":
    main()
