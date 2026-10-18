"""Prepare/review one exact-force diagnostic on 24 existing untrained frames."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import tarfile
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.artifact_io import sha256_file, write_json_exclusive

from .prepare import BASE, DEST as PREVIOUS, ROOT
from .runtime import local_path, verify
from .validation_helpers import force_metrics

DEST = BASE / "adsorption_force24_2185_20261018_v1"
REMOTE = "/home/sbq/sbq/aqcat25_ts_pilot/" + DEST.name
SOURCE = BASE / "adsorption_calibration_20261018_v1/current_trajectories"


def prepare() -> None:
    plan = json.loads((PREVIOUS / "next_exact_force_comparison_plan.json").read_bytes())
    source_path = SOURCE / "dataset_review.json"
    if sha256_file(source_path) != plan["source_dataset_sha256"]:
        raise ValueError("reviewed source pool changed")
    source = json.loads(source_path.read_bytes())
    planned = {s["sample_id"]: s for s in plan["samples"]}
    if len(source["samples"]) != 24 or Counter(r["source_name"] for r in source["samples"]) != {"06_C": 8, "07_B": 8, "08_A": 8}:
        raise ValueError("expected exactly eight frames per reviewed trajectory")
    if set(planned) != {s["sample_id"] for s in source["samples"]}:
        raise ValueError("reviewed selection changed")
    DEST.mkdir(exist_ok=False)
    artifacts = []

    def copy(path: Path, relative: str) -> str:
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(target)
        shutil.copyfile(path, target)
        artifacts.append({"path": relative, "sha256": sha256_file(target)})
        return relative

    samples = []
    for row in source["samples"]:
        if any(row[key] != planned[row["sample_id"]][key] for key in ("structure_sha256", "source_name", "source_OUTCAR_sha256")):
            raise ValueError("sample not bound to reviewed plan")
        path = copy(local_path(SOURCE, row["structure_path"]), "samples/" + row["sample_id"] + ".vasp")
        samples.append({**row, "structure_path": path})
    manifest = copy(source_path, "evidence/source_dataset_review.json")
    copy(SOURCE / "split_review.json", "evidence/split_review.json")
    copy(PREVIOUS / "next_exact_force_comparison_plan.json", "evidence/previous_plan.json")
    policy = copy(ROOT / "configs/execution_backends.yaml", "backend_policy.yaml")
    for name in ("runtime.py", "validation_helpers.py"):
        copy(Path(__file__).with_name(name), "runtime/" + name)
    request = {"document_kind": "adsorption_exact_trajectory_force_comparison", "schema_version": 1,
        "run_id": "direct-fe110-adsorption-force24-2185-20261018-v1", "remote_root": REMOTE,
        "exception_id": "fe110_adsorption_force24_2185_20261018", "execution_mode": "direct_no_scheduler",
        "scheduler_job_id": None, "gpu_index": 1, "gpu_uuid": "GPU-450609b3-d1fd-ac33-d03a-79891be402da",
        "max_wall_seconds": 600, "models": plan["models"], "samples": samples,
        "sample_role": "screened_untrained_diagnostic_not_independent_heldout", "geometry_cases": [], "limits": {},
        "source_manifest_path": manifest, "source_manifest_sha256": sha256_file(source_path),
        "scientific_boundaries": {"training": False, "new_VASP": False, "default_model_change": False,
            "geometry_optimization": False, "independent_heldout": False, "speedup_proved": False},
        "policy": {"path": policy, "sha256": sha256_file(DEST / policy)}, "artifacts": artifacts}
    path = DEST / "validation_request.json"
    write_json_exclusive(path, request)
    write_json_exclusive(DEST / "submission_authorization.json", {
        "action": "RUN_GPU_ADSORPTION_EXACT_FORCES", "user_request": "可以继续", "user_authorized": True,
        "request_sha256": sha256_file(path), "scope": "one24-frame diagnostic; no relaxation/training/VASP/promotion"})
    verify(path, DEST / "submission_authorization.json")
    archive = DEST / "validation_bundle.tar"
    with tarfile.open(archive, "x") as handle:
        for name in [item["path"] for item in artifacts] + ["validation_request.json", "submission_authorization.json"]:
            handle.add(DEST / name, arcname=name, recursive=False)
    write_json_exclusive(DEST / "preparation_receipt.json", {"request_sha256": sha256_file(path),
        "archive_sha256": sha256_file(archive), "sample_count": 24, "model_executed": False})
    print(json.dumps({"status": "EXACT_FORCE_PACKAGE_PASS", "samples": 24, "request_sha256": sha256_file(path)}))


def stage(row: dict) -> str:
    if row["ionic_step"] <= 5:
        return "early_steps_1_2_5"
    if row["ionic_step"] >= row["source_total_steps"] - 1:
        return "last_two_steps"
    return "intermediate_sampled_steps"


def aggregate(rows: list, predictions: dict) -> dict:
    reference, predicted, symbols, fixed = [], [], [], []
    offset = 0
    for row in rows:
        reference.extend(row["forces_eV_per_A"])
        predicted.extend(predictions[row["sample_id"]])
        symbols.extend(row["symbols"])
        fixed.extend(offset + i for i in row["fixed_atom_indices_0based"])
        offset += len(row["symbols"])
    return force_metrics(reference, predicted, symbols, fixed)


def read_predictions(request: dict, returned: Path, model: str) -> dict:
    payload = json.loads((returned / "output" / (model + "_forces.json")).read_bytes())
    if payload["checkpoint_sha256"] != request["models"][model]["sha256"]:
        raise ValueError("wrong checkpoint")
    expected = {s["sample_id"]: s for s in request["samples"]}
    if len(payload["samples"]) != len(expected) or {s["sample_id"] for s in payload["samples"]} != set(expected):
        raise ValueError("incomplete or duplicate predictions")
    predictions = {}
    for sample in payload["samples"]:
        row = expected[sample["sample_id"]]
        if sample["structure_sha256"] != row["structure_sha256"]:
            raise ValueError("not an exact-structure prediction")
        force_metrics(row["forces_eV_per_A"], sample["predicted_forces_eV_per_A"], row["symbols"], row["fixed_atom_indices_0based"])
        predictions[row["sample_id"]] = sample["predicted_forces_eV_per_A"]
    return predictions


def review() -> None:
    request_path = DEST / "validation_request.json"
    request = verify(request_path, DEST / "submission_authorization.json")
    returned = DEST / "returned"
    manifest = json.loads((returned / "return_manifest.json").read_bytes())
    for entry in manifest["files"]:
        if sha256_file(local_path(returned, entry["path"])) != entry["sha256"]:
            raise ValueError("returned bytes changed")
    record = json.loads((returned / "output/producer_exit_record.json").read_bytes())
    if record["exit_code"] or record["request_sha256"] != sha256_file(request_path):
        raise ValueError("producer failed or stale request")
    predictions = {}
    for name in request["models"]:
        device = json.loads((returned / "output" / (name + "_device.json")).read_bytes())
        if not device["model_device"].startswith("cuda") or device["physical_gpu_uuid"] != request["gpu_uuid"]:
            raise ValueError("not on authorized GPU")
        predictions[name] = read_predictions(request, returned, name)
    rows = request["samples"]
    selections = {"all24": rows}
    for source in sorted({r["source_name"] for r in rows}):
        selections[source] = [r for r in rows if r["source_name"] == source]
        for label in sorted({stage(r) for r in rows}):
            selections[source + "/" + label] = [r for r in selections[source] if stage(r) == label]
    groups = {label: {"sample_count": len(selection), **{name: aggregate(selection, pred) for name, pred in predictions.items()}}
              for label, selection in selections.items()}
    frames = []
    for row in rows:
        metrics = {name: force_metrics(row["forces_eV_per_A"], pred[row["sample_id"]], row["symbols"], row["fixed_atom_indices_0based"])
                   for name, pred in predictions.items()}
        worst = {}
        for name, pred in predictions.items():
            error = np.linalg.norm(np.asarray(pred[row["sample_id"]]) - np.asarray(row["forces_eV_per_A"]), axis=1)
            index = 18 + int(np.argmax(error[18:]))
            worst[name] = {"atom_index_0based": index, "symbol": row["symbols"][index], "vector_error_eV_A": float(error[index])}
        frames.append({"sample_id": row["sample_id"], "source_name": row["source_name"], "ionic_step": row["ionic_step"],
                       "stage": stage(row), "DFT_movable_fmax_eV_A": row["movable_fmax_eV_A"], "metrics": metrics, "worst_atom": worst})
    result = {"status": "EXACT_FORCE_DIAGNOSTIC_COMPLETE_NOT_MODEL_PROMOTION", "request_sha256": sha256_file(request_path),
        "models": request["models"], "sample_role": request["sample_role"], "groups": groups, "frames": frames,
        "limits": ["screened24 frames are not an independent heldout test", "no predictions at failed ML06_C geometry",
                   "small-force cosine near a minimum is not a robust direction metric", "force agreement alone does not prove geometry or VASP speedup"],
        "training_performed": False, "new_VASP": False, "model_promoted": False}
    write_json_exclusive(DEST / "force_comparison_review.json", result)
    with (DEST / "frame_comparison.csv").open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_id", "stage", "DFT_movable_fmax_eV_A", "model", "adsorbate_vector_RMSE_eV_A", "adsorbate_max_error_eV_A", "movable_Fe_vector_RMSE_eV_A", "adsorbate_mean_cosine", "worst_movable_atom_0based"])
        for frame in frames:
            for name, metric in frame["metrics"].items():
                writer.writerow([frame["sample_id"], frame["stage"], frame["DFT_movable_fmax_eV_A"], name,
                    metric["adsorbate"]["vector_rmse_eV_A"], metric["adsorbate"]["vector_max_eV_A"], metric["Fe"]["vector_rmse_eV_A"],
                    metric["adsorbate"]["mean_cosine_nonzero_forces"], frame["worst_atom"][name]["atom_index_0based"]])
    print(json.dumps({label: {name: group[name]["adsorbate"]["vector_rmse_eV_A"] for name in request["models"]}
                      for label, group in groups.items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "review"))
    args = parser.parse_args()
    {"prepare": prepare, "review": review}[args.action]()
