#!/usr/bin/env python3
"""Compare exact MatRIS/AQCat25 predictions with hash-bound VASP force labels."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic


def model_metrics(
    prediction_rows: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
    *,
    model_prefix: str,
    fixed_indices: list[int],
) -> dict[str, Any]:
    labels = {str(row["sample_id"]): row for row in label_rows}
    component_errors: list[float] = []
    vector_errors: list[float] = []
    predicted_energies: list[float] = []
    vasp_energies: list[float] = []
    per_sample: list[dict[str, Any]] = []
    fixed = set(fixed_indices)
    for prediction in prediction_rows:
        sample_id = str(prediction["sample_id"])
        label = labels[sample_id]
        predicted = np.asarray(prediction[f"{model_prefix}_forces_eV_per_A"], dtype=float)
        reference = np.asarray(label["vasp_forces_eV_per_A"], dtype=float)
        if predicted.shape != reference.shape or predicted.ndim != 2 or predicted.shape[1] != 3:
            raise ValueError(f"force shape mismatch: {sample_id}")
        movable = [index for index in range(len(predicted)) if index not in fixed]
        if not movable:
            raise ValueError("no movable atoms remain for force assessment")
        errors = predicted[movable] - reference[movable]
        norms = np.linalg.norm(errors, axis=1)
        component_errors.extend(errors.reshape(-1).tolist())
        vector_errors.extend(norms.tolist())
        predicted_energies.append(float(prediction[f"{model_prefix}_energy_eV"]))
        vasp_energies.append(float(label["vasp_energy_eV"]))
        per_sample.append(
            {
                "sample_id": sample_id,
                "component_mae_eV_per_A": float(np.mean(np.abs(errors))),
                "vector_rmse_eV_per_A": float(np.sqrt(np.mean(norms**2))),
                "vector_max_eV_per_A": float(norms.max()),
            }
        )
    components = np.asarray(component_errors, dtype=float)
    vectors = np.asarray(vector_errors, dtype=float)
    predicted_relative = np.asarray(predicted_energies) - min(predicted_energies)
    vasp_relative = np.asarray(vasp_energies) - min(vasp_energies)
    energy_errors = predicted_relative - vasp_relative
    return {
        "sample_count": len(prediction_rows),
        "movable_atom_force_vector_count": int(vectors.size),
        "component_mae_eV_per_A": float(np.mean(np.abs(components))),
        "component_rmse_eV_per_A": float(np.sqrt(np.mean(components**2))),
        "vector_rmse_eV_per_A": float(np.sqrt(np.mean(vectors**2))),
        "vector_p95_eV_per_A": float(np.percentile(vectors, 95)),
        "vector_max_eV_per_A": float(vectors.max()),
        "relative_energy_mae_eV": float(np.mean(np.abs(energy_errors))),
        "relative_energy_rmse_eV": float(np.sqrt(np.mean(energy_errors**2))),
        "lowest_energy_structure_match": bool(
            int(np.argmin(predicted_relative)) == int(np.argmin(vasp_relative))
        ),
        "per_sample": per_sample,
    }


def _passes(metrics: dict[str, Any], ceilings: dict[str, Any]) -> tuple[bool, list[str]]:
    checks = {
        "force_component_mae": metrics["component_mae_eV_per_A"]
        <= float(ceilings["force_component_mae_eV_per_A_max"]),
        "force_vector_rmse": metrics["vector_rmse_eV_per_A"]
        <= float(ceilings["force_vector_rmse_eV_per_A_max"]),
        "force_vector_max": metrics["vector_max_eV_per_A"]
        <= float(ceilings["force_vector_max_eV_per_A_max"]),
        "relative_energy_rmse": metrics["relative_energy_rmse_eV"]
        <= float(ceilings["relative_energy_rmse_eV_max"]),
    }
    return all(checks.values()), [name for name, passed in checks.items() if not passed]


def assess(  # noqa: C901 - assessment is a linear evidence and decision gate.
    state_path: Path,
    label_set_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    state = load_json_object(state_path)
    if state.get("document_kind") != "dual_model_ts_active_learning_state":
        raise ValueError("invalid dual-model active-learning state")
    if state.get("status") != "awaiting_completed_VASP_force_labels":
        raise ValueError("state is not ready for completed VASP label assessment")
    prediction_ref = state.get("prediction_result") or {}
    prediction_path = Path(str(prediction_ref.get("path", "")))
    if not prediction_path.is_file() or sha256_file(prediction_path) != prediction_ref.get("sha256"):
        raise ValueError("bound dual-model prediction result is missing or changed")
    predictions = load_json_object(prediction_path)
    labels = load_json_object(label_set_path)
    if labels.get("document_kind") != "dual_model_ts_vasp_force_label_set":
        raise ValueError("invalid dual-model VASP force-label set")
    batch_ref = state.get("vasp_label_batch") or {}
    if labels.get("source_batch_sha256") != batch_ref.get("sha256"):
        raise ValueError("VASP labels are not bound to the selected label batch")
    selected_ids = {str(row["sample_id"]) for row in state.get("selected_vasp_labels", [])}
    label_rows = labels.get("labels")
    if not isinstance(label_rows, list) or {str(row.get("sample_id")) for row in label_rows} != selected_ids:
        raise ValueError("completed VASP label set does not match selected samples")
    for row in label_rows:
        if row.get("structure_sha256") != next(
            selected["structure_sha256"]
            for selected in state["selected_vasp_labels"]
            if selected["sample_id"] == row["sample_id"]
        ):
            raise ValueError(f"VASP label structure hash mismatch: {row['sample_id']}")
        evidence = row.get("acceptance_evidence") or {}
        required = (
            "scheduler_DONE",
            "normal_vasp_completion",
            "electronically_converged",
            "complete_atom_aligned_force_block",
            "total_magnetic_moment_available",
            "atom_resolved_magnetic_moments_available",
            "sigma_0p20_compatibility",
        )
        if not all(evidence.get(name) is True for name in required):
            raise ValueError(f"VASP label evidence is incomplete: {row['sample_id']}")
        if not math.isfinite(float(row["vasp_energy_eV"])):
            raise ValueError(f"non-finite VASP energy: {row['sample_id']}")

    prediction_by_id = {row["sample_id"]: row for row in predictions["predictions"]}
    selected_predictions = [prediction_by_id[row["sample_id"]] for row in label_rows]
    fixed = list(predictions["fixed_atom_indices_zero_based"])
    matris_metrics = model_metrics(
        selected_predictions, label_rows, model_prefix="primary", fixed_indices=fixed
    )
    aqcat_metrics = model_metrics(
        selected_predictions, label_rows, model_prefix="secondary", fixed_indices=fixed
    )
    policy_path = Path(state["source_bindings"]["policy"]["path"])
    if sha256_file(policy_path) != state["source_bindings"]["policy"]["sha256"]:
        raise ValueError("active-learning policy changed before VASP assessment")
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    ceilings = policy["screening_safety_ceilings"]
    matris_pass, matris_failures = _passes(matris_metrics, ceilings)
    aqcat_pass, aqcat_failures = _passes(aqcat_metrics, ceilings)
    quadrant_assessment: dict[str, Any]
    committee_ref = (state.get("sampling_evidence") or {}).get("committee_assessment") or {}
    if committee_ref.get("status") == "real_MatRIS_committee_available":
        committee_path = Path(committee_ref["path"])
        if sha256_file(committee_path) != committee_ref["sha256"]:
            raise ValueError("MatRIS committee assessment changed before VASP error assessment")
        committee = load_json_object(committee_path)
        committee_by_id = {row["sample_id"]: row for row in committee["predictions"]}
        selected_disagreement = [
            float(committee_by_id[row["sample_id"]]["force_disagreement_eV_per_A"])
            for row in label_rows
        ]
        routing_cutoff = float(np.median(selected_disagreement))
        errors_by_id = {row["sample_id"]: row for row in matris_metrics["per_sample"]}
        quadrants = []
        actions = {
            (True, True): "train_high_priority",
            (True, False): "retain_for_disagreement_calibration_not_training_priority",
            (False, True): "blind_spot_train_high_priority_and_expand_novelty_sampling",
            (False, False): "covered_candidate_or_heldout",
        }
        for label in label_rows:
            sample_id = label["sample_id"]
            error = errors_by_id[sample_id]
            disagreement = float(
                committee_by_id[sample_id]["force_disagreement_eV_per_A"]
            )
            high_disagreement = disagreement >= routing_cutoff
            high_error = (
                error["vector_rmse_eV_per_A"]
                > float(ceilings["force_vector_rmse_eV_per_A_max"])
                or error["vector_max_eV_per_A"]
                > float(ceilings["force_vector_max_eV_per_A_max"])
            )
            quadrants.append(
                {
                    "sample_id": sample_id,
                    "committee_force_disagreement_eV_per_A": disagreement,
                    "MatRIS_VASP_vector_rmse_eV_per_A": error["vector_rmse_eV_per_A"],
                    "MatRIS_VASP_vector_max_eV_per_A": error["vector_max_eV_per_A"],
                    "high_disagreement": high_disagreement,
                    "high_actual_error": high_error,
                    "action": actions[(high_disagreement, high_error)],
                }
            )
        quadrant_assessment = {
            "status": "routing_quadrants_available_not_quantitative_uncertainty",
            "high_disagreement_cutoff": {
                "value_eV_per_A": routing_cutoff,
                "source": "within_selected_batch_median_for_routing_only",
            },
            "samples": quadrants,
        }
    else:
        quadrant_assessment = {
            "status": "unavailable_without_real_MatRIS_committee",
            "fallback": "decide_from_model_specific_VASP_error_and_available_novelty",
        }
    decision = (
        "fine_tune_MatRIS_then_require_new_checkpoint_and_complete_path_rerun"
        if not matris_pass
        else "retain_MatRIS_checkpoint_then_run_disjoint_heldout_TS_validation"
    )
    result = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_vasp_error_assessment",
        "reaction_id": state["reaction_id"],
        "round_index": state["round_index"],
        "source_state_sha256_before_assessment": sha256_file(state_path),
        "source_prediction_set_sha256": sha256_file(prediction_path),
        "source_vasp_label_set_sha256": sha256_file(label_set_path),
        "screening_safety_ceilings": ceilings,
        "models": {
            "matris_primary": {
                "checkpoint_sha256": predictions["models"]["primary"]["checkpoint_sha256"],
                "metrics": matris_metrics,
                "screening_passed": matris_pass,
                "failed_checks": matris_failures,
            },
            "aqcat25_secondary": {
                "checkpoint_sha256": predictions["models"]["secondary"]["checkpoint_sha256"],
                "metrics": aqcat_metrics,
                "screening_passed": aqcat_pass,
                "failed_checks": aqcat_failures,
            },
        },
        "uncertainty_error_quadrants": quadrant_assessment,
        "decision": decision,
        "calibrated_active_learning_acceleration": False,
        "reason_not_calibrated": "independent disjoint held-out TS validation has not passed",
    }
    write_json_atomic(output_path, result, ensure_ascii=True)
    state["vasp_error_assessment"] = {
        "path": str(output_path.resolve()),
        "sha256": sha256_file(output_path),
        "decision": decision,
    }
    state["status"] = (
        "awaiting_energy_force_aware_MatRIS_fine_tuning"
        if not matris_pass
        else "awaiting_disjoint_heldout_TS_validation"
    )
    state["scientific_status"] = "VASP_screened_not_calibrated"
    write_json_atomic(state_path, state, ensure_ascii=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Assess MatRIS and AQCat25 against exact VASP labels.")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.state, args.labels, args.output)
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "matris_passed": result["models"]["matris_primary"]["screening_passed"],
                "aqcat25_passed": result["models"]["aqcat25_secondary"]["screening_passed"],
                "calibrated": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
