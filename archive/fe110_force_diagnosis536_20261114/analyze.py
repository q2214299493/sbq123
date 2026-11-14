"""Consume real frozen-model vectors only; fail on missing or protected samples."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from .prepare import OUT


def validate_packet(references, packet, model_sha):
    if packet.get("checkpoint_sha256") != model_sha:
        raise ValueError("wrong frozen checkpoint")
    expected = {r["sample_id"]: r for r in references}
    samples = packet["samples"]
    supplied = {r["sample_id"]: r for r in samples}
    if len(supplied) != len(samples) or set(supplied) != set(expected):
        raise ValueError("missing, duplicate or extra samples;protected frames are forbidden")
    result = []
    for name, reference in expected.items():
        if reference["partition"] not in {"train", "development"}:
            raise ValueError("protected partition is not a diagnostic input")
        prediction = supplied[name]
        if prediction["structure_sha256"] != reference["structure_sha256"]:
            raise ValueError("not the same source coordinates")
        values = np.asarray(prediction["predicted_forces_eV_per_A"], dtype=float)
        target = np.asarray(reference["DFT_forces_eV_per_A"], dtype=float)
        if values.shape != target.shape or values.shape != (len(reference["symbols"]), 3) or not np.isfinite(values).all():
            raise ValueError("prediction shape or finite-value check failed")
        result.append((reference, target, values))
    return result


def vector_metrics(reference, predicted):
    reference, predicted = np.asarray(reference, dtype=float), np.asarray(predicted, dtype=float)
    if reference.ndim != 2 or reference.shape[1] != 3 or reference.shape != predicted.shape:
        raise ValueError("force array shape mismatch")
    if not len(reference) or not np.isfinite(reference).all() or not np.isfinite(predicted).all():
        raise ValueError("empty or nonfinite force arrays")
    error = predicted - reference
    norms = np.linalg.norm(error, axis=1)
    true_norm, pred_norm = np.linalg.norm(reference, axis=1), np.linalg.norm(predicted, axis=1)
    usable = (true_norm > 1e-8) & (pred_norm > 1e-8)
    cosine = np.sum(reference[usable] * predicted[usable], axis=1) / (true_norm[usable] * pred_norm[usable])
    return {"atom_observations": len(reference), "vector_RMSE_eV_A": float(np.sqrt(np.mean(norms**2))),
            "vector_MAE_eV_A": float(norms.mean()), "component_MAE_eV_A": float(np.abs(error).mean()),
            "maximum_vector_error_eV_A": float(norms.max()), "sum_squared_vector_error": float(np.sum(norms**2)),
            "cosine_usable_atoms": len(cosine), "mean_cosine_nonzero": float(cosine.mean()) if len(cosine) else None,
            "reversed_direction_fraction_nonzero": float((cosine < 0).mean()) if len(cosine) else None,
            "maximum_DFT_force_eV_A": float(true_norm.max()), "maximum_predicted_force_eV_A": float(pred_norm.max())}


def diagnose(references, packet, model_sha):
    data = validate_packet(references, packet, model_sha)
    grouped = defaultdict(lambda: [[], []])
    frames = []
    for row, target, prediction in data:
        free = [i for i in range(len(target)) if i not in row["fixed_atom_indices_0based"]]
        groups = {**row["force_role_groups"], "all_movable": free}
        groups["all_movable_Fe"] = sorted(row["force_role_groups"].get("near_Fe", []) + row["force_role_groups"].get("other_Fe", []))
        values = {role: vector_metrics(target[indices], prediction[indices]) for role, indices in groups.items() if indices}
        for role, indices in groups.items():
            if indices:
                key = (row["partition"], row["qualification_scope"], row["composition"], row["force_stage"], role)
                grouped[key][0].extend(target[indices].tolist())
                grouped[key][1].extend(prediction[indices].tolist())
        all_forces = values["all_movable"]
        frames.append({"sample_id": row["sample_id"], "partition": row["partition"], "qualification_scope": row["qualification_scope"],
                       "composition": row["composition"], "force_stage": row["force_stage"], "structure_sha256": row["structure_sha256"],
                       "groups": values, "ML_fmax_le0p05_DFT_fmax_gt0p10": all_forces["maximum_predicted_force_eV_A"] <= .05 and all_forces["maximum_DFT_force_eV_A"] > .10,
                       "same_coordinate_labels_already_exist_new_DFT_for_this_frame": False})
    summaries = [{"partition": key[0], "qualification_scope": key[1], "composition": key[2], "force_stage": key[3], "role": key[4],
                  **vector_metrics(*arrays)} for key, arrays in sorted(grouped.items())]
    return {"frames": frames, "grouped_metrics": summaries, "heldout_used": False,
            "strict_and_legacy_scopes_separated": True, "same_coordinate_only": True,
            "no_structure_optimization_or_speedup_evidence": True}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    args = parser.parse_args()
    labels_path = OUT / "qualified_reference_labels.json"
    scope_path = OUT / "prediction_scope.json"
    result = diagnose(load_json_object(labels_path)["records"], load_json_object(args.predictions), load_json_object(scope_path)["model_sha256"])
    result["source_files"] = source_file_manifest([Path(__file__), labels_path, scope_path, args.predictions])
    write_json_exclusive(OUT / "full_fixed_structure_force_diagnosis.json", result)


if __name__ == "__main__":
    main()
