"""One authorized baseline/control force-only test; never fit or promote."""
from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from collections import Counter
from pathlib import Path

import numpy as np

from archive.fe110_adsorption_candidate_review_20261020.review import frozen_validation_rows
from archive.fe110_adsorption_validation_20261018.force24 import read_predictions
from archive.fe110_adsorption_validation_20261018.runtime import local_path, verify
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012"
SOURCE = BASE / "adsorption_candidate_review_20261020_v1/independent_validation_proposal.json"
PROPOSAL_SHA = "bf2e4a7c745ae6569f69c70a262c8854566d8b6a123592ca123cbfc6dbfe0c92"
DEST = BASE / "adsorption_control_heldout46_20261020_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/" + DEST.name
ROLES = ("movable", "adsorbate", "adsorbate_C", "adsorbate_O", "adsorbate_H", "near_Fe", "other_Fe")


def prepare() -> None:
    if sha256_file(SOURCE) != PROPOSAL_SHA:
        raise ValueError("reviewed independent proposal changed")
    source = load_json_object(SOURCE)
    manifest_path, bound, rows, _ = frozen_validation_rows()
    if (source["training_manifest"]["sha256"] != bound or len(rows) != 46
            or source["whole_job_counts"] != {"09_C": 23, "10_A": 23}):
        raise ValueError("reviewed independent source scope changed")
    DEST.mkdir(exist_ok=False)
    artifacts = []

    def copy(path: Path, relative: str) -> str:
        target = local_path(DEST, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha256_file(target) != sha256_file(path):
                raise ValueError("conflicting package artifact")
            return relative
        shutil.copyfile(path, target)
        artifacts.append({"path": relative, "sha256": sha256_file(target)})
        return relative

    samples = []
    for row in source["samples"]:
        structure = copy(local_path(ROOT, row["structure_path"]), "samples/" + row["sample_id"] + ".vasp")
        label = copy(local_path(ROOT, row["label_source"]["path"]), "evidence/candidate_labels.json")
        samples.append({**row, "structure_path": structure,
                        "label_source": {**row["label_source"], "path": label}})
    proposal = copy(SOURCE, "evidence/frozen_proposal.json")
    manifest = copy(manifest_path, "evidence/training_manifest.json")
    policy = copy(ROOT / "configs/execution_backends.yaml", "backend_policy.yaml")
    runtime = ROOT / "archive/fe110_adsorption_validation_20261018"
    for name in ("runtime.py", "validation_helpers.py"):
        copy(runtime / name, "runtime/" + name)
    request = {"document_kind": "adsorption_independent_force_validation", "schema_version": 1,
        "run_id": "direct-fe110-adsorption-control-heldout46-20261020-v1", "remote_root": REMOTE,
        "exception_id": "fe110_adsorption_control_heldout46_20261020", "execution_mode": "direct_no_scheduler",
        "scheduler_job_id": None, "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da",
        "max_wall_seconds": 600, "models": source["models"], "samples": samples,
        "sample_role": "frozen_whole_job_heldout_not_used_for_current_fit_or_selection",
        "geometry_cases": [], "limits": {}, "source_manifest_path": proposal,
        "source_manifest_sha256": PROPOSAL_SHA, "frozen_training_manifest": {"path": manifest, "sha256": bound},
        "policy": {"path": policy, "sha256": sha256_file(DEST / policy)}, "artifacts": artifacts,
        "scientific_boundaries": {"training": False, "relaxation": False, "new_VASP": False,
            "energy_ranking": False, "production_promotion": False, "heldout_driven_model_reselection": False,
            "measured_acceleration": False}}
    path = DEST / "validation_request.json"
    write_json_exclusive(path, request)
    write_json_exclusive(DEST / "submission_authorization.json", {
        "action": "RUN_GPU_ADSORPTION_EXACT_FORCES", "user_request": "验证", "user_authorized": True,
        "request_sha256": sha256_file(path), "scope": "one frozen46 baseline/control batch;92 predictions;600s;zero retries"})
    verify(path, DEST / "submission_authorization.json")
    archive = DEST / "validation_bundle.tar"
    with tarfile.open(archive, "x") as handle:
        for name in [a["path"] for a in artifacts] + ["validation_request.json", "submission_authorization.json"]:
            handle.add(DEST / name, arcname=name, recursive=False)
    write_json_exclusive(DEST / "preparation_receipt.json", {"request_sha256": sha256_file(path),
        "proposal_sha256": PROPOSAL_SHA, "bundle_sha256": sha256_file(archive), "sample_count": 46,
        "prediction_count": 92, "new_model_predictions": 0,
        "preparation_source": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha256_file(Path(__file__))}})
    print(json.dumps({"status": "FROZEN46_FORCE_PACKAGE_VERIFIED", "request_sha256": sha256_file(path),
                      "samples": 46, "predictions": 92, "max_wall_seconds": 600}))


def indices(row: dict, role: str) -> list[int]:
    free = [i for i in range(len(row["symbols"])) if i not in row["fixed_atom_indices_0based"]]
    if role == "movable":
        return free
    if role == "adsorbate":
        return [i for i in free if row["symbols"][i] != "Fe"]
    return row["force_role_groups"][role]


def metrics(rows: list, predictions: dict, role: str) -> dict:
    reference, predicted = [], []
    for row in rows:
        selected = indices(row, role)
        reference.extend(np.asarray(row["forces_eV_per_A"])[selected])
        predicted.extend(np.asarray(predictions[row["sample_id"]])[selected])
    if not reference:
        return {"atom_count": 0}
    reference, predicted = np.asarray(reference), np.asarray(predicted)
    norms = np.linalg.norm(predicted-reference, axis=1)
    refnorm, prednorm = np.linalg.norm(reference, axis=1), np.linalg.norm(predicted, axis=1)
    mask = (refnorm > .001) & (prednorm > .001)
    cos = np.sum(reference*predicted, axis=1)[mask] / (refnorm*prednorm)[mask]
    return {"atom_count": len(norms), "component_mae_eV_A": float(np.abs(predicted-reference).mean()),
        "vector_mae_eV_A": float(norms.mean()), "vector_rmse_eV_A": float(np.sqrt(np.mean(norms**2))),
        "vector_p95_eV_A": float(np.quantile(norms, .95)), "vector_max_eV_A": float(norms.max()),
        "direction_norm_floor_eV_A": .001, "direction_atom_count": int(mask.sum()),
        "mean_cosine": float(cos.mean()) if len(cos) else None,
        "opposed_force_vectors": int((cos < 0).sum()),
        "reference_fmax_eV_A": float(refnorm.max()), "predicted_fmax_eV_A": float(prednorm.max())}


def summarize(rows: list, predictions: dict) -> dict:
    subsets = {"all46": rows}
    for source in sorted({r["source_name"] for r in rows}):
        subsets[source] = [r for r in rows if r["source_name"] == source]
        for stage in sorted({r["stage"] for r in subsets[source]}):
            subsets[source + "/" + stage] = [r for r in subsets[source] if r["stage"] == stage]
    return {name: {"sample_count": len(subset), **{
        model: {role: metrics(subset, pred, role) for role in ROLES}
        for model, pred in predictions.items()}} for name, subset in subsets.items()}


def frame_review(row: dict, predictions: dict) -> dict:
    result = {key: row[key] for key in ("sample_id", "source_name", "source_job_id", "ionic_step", "stage",
        "formula_without_slab", "original_graph_preserved", "parent_ionic_converged", "accepted_endpoint")}
    result["DFT_movable_fmax_eV_A"] = row["movable_fmax_eV_A"]
    result["metrics"] = {model: {role: metrics([row], pred, role) for role in ROLES} for model, pred in predictions.items()}
    worst = {}
    for model, pred in predictions.items():
        error = np.linalg.norm(np.asarray(pred[row["sample_id"]])-np.asarray(row["forces_eV_per_A"]), axis=1)
        carbons = indices(row, "adsorbate_C")
        index = max(carbons, key=lambda i: error[i])
        worst[model] = {"atom_index_0based": index, "vector_error_eV_A": float(error[index]),
            "reference_force_eV_A": row["forces_eV_per_A"][index], "predicted_force_eV_A": pred[row["sample_id"]][index]}
    result["worst_carbon"] = worst
    return result


def review() -> None:
    request_path = DEST / "validation_request.json"
    request = verify(request_path, DEST / "submission_authorization.json")
    returned = DEST / "returned"
    manifest = load_json_object(returned / "return_manifest.json")
    for entry in manifest["files"]:
        if sha256_file(local_path(returned, entry["path"])) != entry["sha256"]:
            raise ValueError("returned source bytes changed")
    record = load_json_object(returned / "output/producer_exit_record.json")
    if (record["exit_code"] or record["request_sha256"] != sha256_file(request_path)
            or any(record[k] for k in ("training_performed", "model_promoted", "vasp_submitted"))):
        raise ValueError("failed/stale/out-of-scope producer")
    predictions = {}
    for model in request["models"]:
        device = load_json_object(returned / "output" / (model + "_device.json"))
        if not device["model_device"].startswith("cuda") or device["physical_gpu_uuid"] != request["gpu_uuid"]:
            raise ValueError("predictions did not use authorized CUDA device")
        predictions[model] = read_predictions(request, returned, model)
    frames = [frame_review(row, predictions) for row in request["samples"]]
    result = {"status": "FROZEN46_INDEPENDENT_FORCE_TEST_COMPLETE_NOT_PROMOTION",
        "request_sha256": sha256_file(request_path), "proposal_sha256": PROPOSAL_SHA, "models": request["models"],
        "groups": summarize(request["samples"], predictions), "frames": frames,
        "near_DFT_minimum_samples": [r for r in frames if r["stage"] == "last2"],
        "worst_carbon_by_candidate": sorted(frames, key=lambda r: r["worst_carbon"]["candidate"]["vector_error_eV_A"], reverse=True)[:5],
        "framewise_adsorbate_RMSE_lower_count": sum(r["metrics"]["candidate"]["adsorbate"]["vector_rmse_eV_A"] <
            r["metrics"]["baseline"]["adsorbate"]["vector_rmse_eV_A"] for r in frames),
        "whole_job_counts": dict(Counter(r["source_name"] for r in request["samples"])),
        "limits": ["46 correlated frames from only two previously screened jobs;not46independent chemical environments",
            "heldout from current fine-tuning only;baseline pretraining overlap unknown",
            "C2H3 has no current-training coverage;10_C failure region not validated by this batch",
            "force agreement is not geometry preservation or measured VASP acceleration",
            "candidate was frozen before testing;no test-driven model reselection or training"],
        "training_performed": False, "new_VASP": False, "model_promoted": False, "measured_VASP_acceleration": False}
    write_json_exclusive(DEST / "independent_force_review.json", result)
    print(json.dumps({label: {model: {role: values["vector_rmse_eV_A"] for role, values in group[model].items() if values["atom_count"]}
        for model in request["models"]} for label, group in result["groups"].items() if "/" not in label}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "review"))
    args = parser.parse_args()
    {"prepare": prepare, "review": review}[args.action]()
