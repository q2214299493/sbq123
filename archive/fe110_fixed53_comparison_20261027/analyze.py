"""Recompute paired, unconstrained force errors from the frozen159 predictions."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.adsorption.fixed_force_comparison import verify
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare import MODELS, OUTPUT, PACKAGE

ROLES = ("movable", "adsorbate", "C", "O", "H", "Fe", "near_Fe", "other_Fe")
DIRECTION_MIN = 0.001  # eV/A; excludes nearly-zero vectors from direction statistics only.
BIN_EDGES = (0, 0.05, 0.1, 0.5, 1, 2, 5, 10, float("inf"))
BIN_NAMES = ("[0,0.05]", "(0.05,0.1]", "(0.1,0.5]", "(0.5,1]", "(1,2]", "(2,5]", "(5,10]", "(10,inf)")


def force_metrics(reference, predicted):
    reference, predicted = np.asarray(reference, dtype=float), np.asarray(predicted, dtype=float)
    if reference.ndim != 2 or reference.shape[1] != 3 or predicted.shape != reference.shape:
        raise ValueError("force arrays must have identical Nx3 shape")
    if not np.isfinite(reference).all() or not np.isfinite(predicted).all():
        raise ValueError("nonfinite force array")
    if not len(reference):
        return {"atom_count": 0, "vector_rmse_eV_A": None, "coverage": "NO_ATOMS"}
    delta = predicted - reference
    errors = np.linalg.norm(delta, axis=1)
    ref_norm, pred_norm = np.linalg.norm(reference, axis=1), np.linalg.norm(predicted, axis=1)
    eligible = (ref_norm > DIRECTION_MIN) & (pred_norm > DIRECTION_MIN)
    cosines = np.clip(np.sum(reference[eligible] * predicted[eligible], axis=1) / (ref_norm[eligible] * pred_norm[eligible]), -1, 1)
    return {"atom_count": len(reference), "coverage": "PRESENT", "component_mae_eV_A": float(np.abs(delta).mean()),
        "vector_mae_eV_A": float(errors.mean()), "vector_rmse_eV_A": float(np.sqrt(np.mean(errors**2))),
        "vector_p95_eV_A": float(np.percentile(errors, 95)), "vector_max_eV_A": float(errors.max()),
        "direction_eligible_count": int(eligible.sum()), "mean_direction_cosine": float(cosines.mean()) if len(cosines) else None,
        "opposed_direction_count": int((cosines < 0).sum())}


def role_indices(row):
    symbols = row["symbols"]
    fixed = row["fixed_atom_indices_0based"]
    if fixed != list(range(18)) or any(symbols[i] != "Fe" for i in fixed) or symbols.count("Fe") != 45:
        raise ValueError("frozen Fe45/fixed18 convention changed")
    movable = [i for i in range(len(symbols)) if i not in fixed]
    roles = {"movable": movable, "adsorbate": [i for i in movable if symbols[i] != "Fe"],
        **{s: [i for i in movable if symbols[i] == s] for s in ("C", "O", "H", "Fe")}}
    supplied = row["force_role_groups"]
    for symbol in ("C", "O", "H"):
        if supplied["adsorbate_" + symbol] != roles[symbol]:
            raise ValueError("force role element membership changed")
    near, other = supplied["near_Fe"], supplied["other_Fe"]
    if len(set(near + other)) != len(near + other) or sorted(near + other) != roles["Fe"]:
        raise ValueError("Fe role groups do not partition movableFe")
    roles.update(near_Fe=near, other_Fe=other)
    return roles


def force_bin(value):
    if not np.isfinite(value) or value < 0:
        raise ValueError("invalid reference fmax")
    for upper, name in zip(BIN_EDGES[1:], BIN_NAMES, strict=True):
        if value <= upper:
            return name
    raise AssertionError("unreachable force bin")


def summarize(records):
    if not records:
        return {"frame_count": 0, "coverage": "NO_TEST_COVERAGE", "models": None, "paired": None}
    models = {}
    for model in MODELS:
        models[model] = {}
        for role in ROLES:
            ref = np.concatenate([r["reference"][r["roles"][role]] for r in records])
            pred = np.concatenate([r["predictions"][model][r["roles"][role]] for r in records])
            models[model][role] = force_metrics(ref, pred)
    deltas = []
    for record in records:
        deltas.append(record["frame"]["adsorbate_rmse"]["new512"] - record["frame"]["adsorbate_rmse"]["control"])
    paired = {"improved_frame_count": sum(d < -1e-9 for d in deltas), "worsened_frame_count": sum(d > 1e-9 for d in deltas),
        "tied_frame_count": sum(abs(d) <= 1e-9 for d in deltas), "mean_frame_rmse_delta_eV_A": float(np.mean(deltas)), "roles": {}}
    for role in ROLES:
        old = models["control"][role]["vector_rmse_eV_A"]
        new = models["new512"][role]["vector_rmse_eV_A"]
        paired["roles"][role] = {"delta_eV_A": new - old if old is not None else None,
            "reduction_percent": 100 * (old - new) / old if old else None}
    return {"frame_count": len(records), "coverage": "PRESENT", "models": models, "paired": paired,
        "composition_counts": dict(Counter(r["row"]["composition"] for r in records)),
        "magnetic_review_counts": dict(Counter(r["row"]["magnetic_review_level"] for r in records))}


def verified_predictions(request):
    result_path = OUTPUT / "result.json"
    result = load_json_object(result_path)
    for source in result["source_files"]:
        if sha256_file(Path(source["path"])) != source["sha256"]:
            raise ValueError("collected source changed")
    raw = load_json_object(OUTPUT / "result.stdout")
    if {k: v for k, v in result.items() if k != "source_files"} != raw:
        raise ValueError("decoded collection differs from raw SSH evidence")
    digest = sha256_file(PACKAGE / "request.json")
    for name in ("output/controller_exit_record.json", "output/producer_exit_record.json"):
        if raw[name]["exit_code"] != 0 or raw[name]["request_sha256"] != digest:
            raise ValueError("comparison did not complete successfully")
    producer = raw["output/producer_exit_record.json"]
    if any(producer[k] for k in ("training_performed", "geometry_optimized", "model_reselected")):
        raise ValueError("forbidden scientific scope expansion")
    predictions = {}
    for model, checkpoint in MODELS.items():
        payload = raw["predictions"][model]
        if payload["checkpoint_sha256"] != checkpoint["sha256"] or [r["sample_id"] for r in payload["samples"]] != request["sample_ids"]:
            raise ValueError("model or paired frame identity mismatch")
        device = raw[model + "_device"]
        if device["model_device"] != "cuda:0" or device["physical_gpu_uuid"] != request["gpu_uuid"]:
            raise ValueError("actual model GPU binding mismatch")
        predictions[model] = {r["sample_id"]: r for r in payload["samples"]}
    return predictions, producer


def frame_records(rows, predictions):
    records = []
    for row in rows:
        roles = role_indices(row)
        reference = np.asarray(row["forces_eV_per_A"], dtype=float)
        if reference.shape != (len(row["symbols"]), 3):
            raise ValueError("reference force shape mismatch")
        fmax = float(np.max(np.linalg.norm(reference[roles["movable"]], axis=1)))
        if "movable_fmax_eV_A" in row and not np.isclose(fmax, row["movable_fmax_eV_A"], rtol=1e-10, atol=1e-12):
            raise ValueError("DFT fmax provenance mismatch")
        adsorbate_fmax = float(np.max(np.linalg.norm(reference[roles["adsorbate"]], axis=1)))
        if "adsorbate_fmax_eV_A" in row and not np.isclose(adsorbate_fmax, row["adsorbate_fmax_eV_A"], rtol=1e-10, atol=1e-12):
            raise ValueError("DFT adsorbate fmax provenance mismatch")
        model_forces, frame_scores = {}, {}
        for model in MODELS:
            predicted_row = predictions[model][row["sample_id"]]
            if predicted_row["structure_sha256"] != row["structure_sha256"]:
                raise ValueError("geometry-force correspondence mismatch")
            pred = np.asarray(predicted_row["predicted_forces_eV_per_A"], dtype=float)
            force_metrics(reference, pred)  # Validate all atoms, including excluded fixed atoms.
            model_forces[model] = pred
            frame_scores[model] = force_metrics(reference[roles["adsorbate"]], pred[roles["adsorbate"]])["vector_rmse_eV_A"]
        frame = {"sample_id": row["sample_id"], "composition": row["composition"], "source_collection": row["source_collection"],
            "calculation_group": row["calculation_group"], "source_job_id": row["source_job_id"],
            "magnetic_review_level": row["magnetic_review_level"], "DFT_movable_fmax_eV_A": fmax, "force_bin": force_bin(fmax),
            "adsorbate_rmse": frame_scores, "new_minus_old_adsorbate_rmse_eV_A": frame_scores["new512"] - frame_scores["control"]}
        records.append({"row": row, "roles": roles, "reference": reference, "predictions": model_forces, "frame": frame})
    return records


def analyze():
    request, _, rows = verify(PACKAGE / "request.json")
    predictions, producer = verified_predictions(request)
    records = frame_records(rows, predictions)
    dimensions = {}
    for field in ("source_collection", "composition", "calculation_group", "force_bin"):
        groups = defaultdict(list)
        for record in records:
            groups[record["frame"][field]].append(record)
        if field == "force_bin":
            for name in BIN_NAMES:
                groups.setdefault(name, [])
        dimensions[field] = {key: summarize(group) for key, group in sorted(groups.items())}
    joint = {}
    for composition in sorted({r["row"]["composition"] for r in records}):
        joint[composition] = {name: summarize([r for r in records if r["row"]["composition"] == composition and r["frame"]["force_bin"] == name]) for name in BIN_NAMES}
    output = {"status": "FIXED53_FORCE_COMPARISON_ANALYZED", "request_sha256": sha256_file(PACKAGE / "request.json"),
        "training_manifest_sha256": request["training_manifest_sha256"], "model_checkpoint_sha256": request["model_checkpoint_sha256"],
        "force_unit": "eV/Angstrom", "error_aggregation": "unweighted atoms;vectorRMSE=sqrt(mean(sum_xyz(deltaF**2)))",
        "direction_min_reference_and_prediction_norm_eV_A": DIRECTION_MIN,
        "evaluation_exposure": {"historical_observed": 46, "reico_reserved": 7, "all53_are_new_blind_test": False,
            "new_checkpoint_frozen_before_prediction": True, "reselection_or_promotion": False},
        "all53": summarize(records), "dimensions": dimensions, "composition_force_bin": joint,
        "frames": [r["frame"] for r in records],
        "elapsed_seconds": (datetime.fromisoformat(producer["finished_at"]) - datetime.fromisoformat(producer["started_at"])).total_seconds(),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "source_files": source_file_manifest([Path(__file__), PACKAGE / "request.json", PACKAGE / "data/training_manifest.json", OUTPUT / "result.json", OUTPUT / "result.stdout"])}
    write_json_exclusive(OUTPUT / "analysis.json", output)
    for label, group in [("all53", output["all53"]), *dimensions["source_collection"].items(), *dimensions["composition"].items()]:
        print(label, group["frame_count"], {m: round(v["adsorbate"]["vector_rmse_eV_A"], 6) for m, v in group["models"].items()}, group["paired"]["roles"]["adsorbate"], flush=True)


if __name__ == "__main__":
    analyze()
