"""Recover exact frozen-checkpoint aggregates; do not fabricate per-frame errors."""
from __future__ import annotations

from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare import BASE, OUT

ROLES = {"adsorbate_C": "吸附C", "adsorbate_O": "吸附O", "adsorbate_H": "吸附H", "near_Fe": "近邻可动Fe", "other_Fe": "其他可动Fe"}


def aggregate_roles(metrics):
    rows = []
    for role, label in ROLES.items():
        value = metrics["forces_" + role + "_vector_mae"]
        total, count = float(value["total"]), int(value["numel"])
        if count <= 0 or abs(total / count - value["metric"]) > 1e-10:
            raise ValueError("native aggregate does not match total/count")
        rows.append({"role": role, "label": label, "atom_observations": count, "vector_MAE_eV_A": total / count, "sum_vector_error_eV_A": total})
    count = sum(r["atom_observations"] for r in rows)
    if metrics["forces_mae"]["numel"] != 3 * count:
        raise ValueError("native component and vector atom counts differ")
    total = sum(r["sum_vector_error_eV_A"] for r in rows)
    for row in rows:
        row["vector_absolute_error_share"] = row["sum_vector_error_eV_A"] / total
        row["atom_count_share"] = row["atom_observations"] / count
    fe = [r for r in rows if r["role"] in ("near_Fe", "other_Fe")]
    return {"roles": rows, "all_free_atoms": count, "atom_weighted_vector_MAE_eV_A": total / count,
            "all_movable_Fe_vector_MAE_eV_A": sum(r["sum_vector_error_eV_A"] for r in fe) / sum(r["atom_observations"] for r in fe),
            "movable_Fe_vector_absolute_error_share": sum(r["sum_vector_error_eV_A"] for r in fe) / total,
            "movable_Fe_atom_count_share": sum(r["atom_observations"] for r in fe) / count,
            "near_to_other_Fe_vector_MAE_ratio": rows[3]["vector_MAE_eV_A"] / rows[4]["vector_MAE_eV_A"],
            "native_role_weighted_per_frame_vector_MAE_eV_A": metrics["forces_role_vector_mae"]["metric"],
            "native_component_MAE_eV_A": metrics["forces_mae"]["metric"],
            "native_global_cosine_metric": metrics["forces_cosine_similarity"]["metric"],
            "RMSE_max_error_stage_composition_and_strict_subset_metrics": "UNAVAILABLE_WITHOUT_PER_ATOM_PREDICTION_VECTORS"}


def run():
    request = load_json_object(OUT / "request_context.json")
    model = Path(request["model_path"])
    if sha256_file(model) != request["model_sha256"]:
        raise ValueError("frozen536 checkpoint changed")
    metadata_path = OUT / "cpu_checkpoint_metadata.stdout"
    metadata = load_json_object(metadata_path)
    if metadata["CUDA_initialized"] or metadata["new_model_forward_or_training"]:
        raise ValueError("metadata-only inspection boundary violated")
    metrics = metadata["val_metrics"]
    if metrics["forces_role_vector_mae"]["numel"] != 78:
        raise ValueError("cached aggregate is not the frozen78 development scope")
    recovery_path = BASE / "training536_execution_20261113_v4/returned/candidate_recovery.json"
    recovery = load_json_object(recovery_path)
    if recovery["candidate_sha256"] != request["model_sha256"] or abs(recovery["best_val_metric"] - metrics["forces_role_vector_mae"]["metric"]) > 1e-12:
        raise ValueError("native best source binding mismatch")
    result = {"status": "PARTIAL_EXISTING_DEVELOPMENT_CACHE_NOT_NEW_FIXED_STRUCTURE_BATCH", "model_sha256": request["model_sha256"],
              "frames": 78, "scope": "original78 development;18 strict+60 original force-only legacy scopes;not independently separable",
              "new_predictions": 0, "new_training_or_DFT": False, "model_config": metadata["model_config"],
              "normalizers_recorded_not_reapplied": metadata["normalizers"], **aggregate_roles(metrics),
              "source_files": source_file_manifest([Path(__file__), metadata_path, recovery_path, model, OUT / "cpu_checkpoint_metadata_receipt.json"])}
    write_json_exclusive(OUT / "cached_development_role_metrics.json", result)
    print({"status": result["status"], "role_MAE": {r["label"]: r["vector_MAE_eV_A"] for r in result["roles"]},
           "Fe_vector_MAE": result["all_movable_Fe_vector_MAE_eV_A"], "native_weighted_MAE": result["native_role_weighted_per_frame_vector_MAE_eV_A"]}, flush=True)


if __name__ == "__main__":
    run()
