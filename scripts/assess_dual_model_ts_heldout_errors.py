#!/usr/bin/env python3
"""Assess frozen dual-model predictions on a disjoint VASP held-out TS set."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.assess_dual_model_ts_vasp_errors import _passes, model_metrics


def _validate_label(row: dict[str, Any]) -> None:
    required = (
        "scheduler_DONE",
        "normal_vasp_completion",
        "electronically_converged",
        "complete_atom_aligned_force_block",
        "total_magnetic_moment_available",
        "atom_resolved_magnetic_moments_available",
        "sigma_0p20_compatibility",
        "remote_to_local_output_hashes_match",
    )
    evidence = row.get("acceptance_evidence") or {}
    if not all(evidence.get(key) is True for key in required):
        raise ValueError(f"incomplete VASP acceptance evidence: {row.get('sample_id')}")
    if not math.isfinite(float(row["vasp_energy_eV"])):
        raise ValueError(f"non-finite VASP energy: {row.get('sample_id')}")


def assess(
    plan_path: Path,
    prediction_path: Path,
    label_path: Path,
    policy_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    plan = load_json_object(plan_path)
    predictions = load_json_object(prediction_path)
    labels = load_json_object(label_path)
    if plan.get("document_kind") != "dual_model_ts_heldout_validation_candidate_plan":
        raise ValueError("invalid held-out validation plan")
    if predictions.get("document_kind") != "dual_model_ts_path_force_prediction_set":
        raise ValueError("invalid frozen prediction set")
    if labels.get("document_kind") != "dual_model_ts_vasp_force_label_set":
        raise ValueError("invalid VASP label set")

    candidates = {str(row["sample_id"]): row for row in plan.get("candidates", [])}
    prediction_rows = {
        str(row["sample_id"]): row for row in predictions.get("predictions", [])
    }
    label_rows = {str(row["sample_id"]): row for row in labels.get("labels", [])}
    if not candidates or set(candidates) != set(prediction_rows) or set(candidates) != set(label_rows):
        raise ValueError("held-out plan, prediction, and VASP sample sets differ")
    for sample_id, candidate in candidates.items():
        expected_hash = candidate["structure_sha256"]
        if prediction_rows[sample_id].get("structure_sha256") != expected_hash:
            raise ValueError(f"prediction structure hash mismatch: {sample_id}")
        if label_rows[sample_id].get("structure_sha256") != expected_hash:
            raise ValueError(f"VASP structure hash mismatch: {sample_id}")
        _validate_label(label_rows[sample_id])

    for key in ("primary", "secondary"):
        if (
            predictions["models"][key]["checkpoint_sha256"]
            != plan["frozen_models"][key]["checkpoint_sha256"]
        ):
            raise ValueError(f"frozen checkpoint mismatch: {key}")

    primary_ids = [
        sample_id
        for sample_id, row in candidates.items()
        if row.get("primary_heldout_metric_eligible") is True
    ]
    diagnostic_ids = [sample_id for sample_id in candidates if sample_id not in primary_ids]
    if len(primary_ids) != 6 or len(diagnostic_ids) != 1:
        raise ValueError("expected six primary held-out samples and one diagnostic")

    primary_predictions = [prediction_rows[sample_id] for sample_id in primary_ids]
    primary_labels = [label_rows[sample_id] for sample_id in primary_ids]
    fixed = list(predictions["fixed_atom_indices_zero_based"])
    matris = model_metrics(
        primary_predictions, primary_labels, model_prefix="primary", fixed_indices=fixed
    )
    aqcat25 = model_metrics(
        primary_predictions, primary_labels, model_prefix="secondary", fixed_indices=fixed
    )
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    ceilings = policy["screening_safety_ceilings"]
    matris_pass, matris_failures = _passes(matris, ceilings)
    aqcat_pass, aqcat_failures = _passes(aqcat25, ceilings)

    diagnostic_id = diagnostic_ids[0]
    diagnostic_prediction = prediction_rows[diagnostic_id]
    diagnostic_label = label_rows[diagnostic_id]
    diagnostic_matris = model_metrics(
        [diagnostic_prediction],
        [diagnostic_label],
        model_prefix="primary",
        fixed_indices=fixed,
    )
    diagnostic_aqcat = model_metrics(
        [diagnostic_prediction],
        [diagnostic_label],
        model_prefix="secondary",
        fixed_indices=fixed,
    )
    diagnostic = {
        "sample_id": diagnostic_id,
        "included_in_primary_aggregate": False,
        "reason": "interpolated_from_two_round0_labeled_parents",
        "matris_force_metrics": diagnostic_matris["per_sample"][0],
        "aqcat25_force_metrics": diagnostic_aqcat["per_sample"][0],
        "relative_energy_metrics_eligible": False,
    }

    result = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_disjoint_heldout_error_assessment",
        "reaction_id": plan["reaction_id"],
        "round_index": plan["round_index"],
        "source_hashes": {
            "heldout_plan_sha256": sha256_file(plan_path),
            "frozen_prediction_set_sha256": sha256_file(prediction_path),
            "vasp_label_set_sha256": sha256_file(label_path),
            "policy_sha256": sha256_file(policy_path),
        },
        "primary_heldout_sample_ids": primary_ids,
        "screening_safety_ceilings": ceilings,
        "models": {
            "matris_primary": {
                "checkpoint_sha256": predictions["models"]["primary"]["checkpoint_sha256"],
                "metrics": matris,
                "heldout_passed": matris_pass,
                "failed_checks": matris_failures,
            },
            "aqcat25_secondary": {
                "checkpoint_sha256": predictions["models"]["secondary"]["checkpoint_sha256"],
                "metrics": aqcat25,
                "heldout_passed": aqcat_pass,
                "failed_checks": aqcat_failures,
            },
        },
        "boundary_diagnostic": diagnostic,
        "decision": (
            "heldout_pass_retain_frozen_MatRIS_for_reviewed_current_TS_path"
            if matris_pass
            else "heldout_fail_fine_tune_MatRIS_on_round0_pool_then_revalidate"
        ),
        "current_TS_path_acceleration_eligible": matris_pass,
        "fine_tuning_required": not matris_pass,
        "quantitative_uncertainty_calibrated": False,
        "uncertainty_boundary": "no_real_MatRIS_committee; VASP error validation only",
        "automatic_followup_submission": False,
        "reportable_final_energy": False,
        "barrier_or_TS_claim": False,
    }
    write_json_atomic(output_path, result, ensure_ascii=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.plan, args.predictions, args.labels, args.policy, args.output)
    print(
        {
            "decision": result["decision"],
            "MatRIS_heldout_passed": result["models"]["matris_primary"]["heldout_passed"],
            "AQCat25_heldout_passed": result["models"]["aqcat25_secondary"]["heldout_passed"],
        }
    )


if __name__ == "__main__":
    main()
