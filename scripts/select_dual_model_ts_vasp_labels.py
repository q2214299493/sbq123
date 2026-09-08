#!/usr/bin/env python3
"""Select dual-model TS samples and prepare exact-structure VASP force labels."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.vasp_inputs import build_fe110_active_learning_force_label


ROOT = Path(__file__).resolve().parents[1]


def _percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values, key=lambda sample_id: (values[sample_id], sample_id))
    denominator = max(1, len(ordered) - 1)
    return {sample_id: rank / denominator for rank, sample_id in enumerate(ordered)}


def _load_committee_rows(
    path: Path | None, predicted: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = load_json_object(path)
    if payload.get("document_kind") != "matris_ts_path_committee_prediction_set":
        raise ValueError("invalid MatRIS committee prediction set")
    members = payload.get("members")
    if not isinstance(members, list) or not 3 <= len(members) <= 5:
        raise ValueError("MatRIS committee requires three to five members")
    checkpoint_hashes = {str(row.get("checkpoint_sha256", "")) for row in members}
    architectures = {str(row.get("architecture_identifier", "")) for row in members}
    if len(checkpoint_hashes) != len(members) or len(architectures) != 1 or "" in architectures:
        raise ValueError("committee checkpoints must be unique and share one architecture")
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("predictions", []):
        sample_id = str(row.get("sample_id", ""))
        if sample_id not in predicted or sample_id in rows:
            raise ValueError(f"invalid committee sample: {sample_id}")
        if row.get("structure_sha256") != predicted[sample_id]["structure_sha256"]:
            raise ValueError(f"committee structure hash mismatch: {sample_id}")
        for field in ("force_disagreement_eV_per_A", "relative_energy_disagreement_eV"):
            if not math.isfinite(float(row[field])) or float(row[field]) < 0:
                raise ValueError(f"invalid committee disagreement: {sample_id} {field}")
        rows[sample_id] = row
    if set(rows) != set(predicted):
        raise ValueError("committee result does not cover the exact prediction sample set")
    return rows


def _load_descriptor_novelty(
    path: Path | None, predicted: dict[str, dict[str, Any]]
) -> dict[str, float]:
    if path is None:
        return {}
    payload = load_json_object(path)
    if payload.get("document_kind") != "ts_descriptor_novelty_assessment":
        raise ValueError("invalid descriptor novelty assessment")
    values: dict[str, float] = {}
    for row in payload.get("samples", []):
        sample_id = str(row.get("sample_id", ""))
        if sample_id not in predicted or sample_id in values:
            raise ValueError(f"invalid novelty sample: {sample_id}")
        if row.get("structure_sha256") != predicted[sample_id]["structure_sha256"]:
            raise ValueError(f"novelty structure hash mismatch: {sample_id}")
        value = float(row["descriptor_novelty"])
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid descriptor novelty: {sample_id}")
        values[sample_id] = value
    if set(values) != set(predicted):
        raise ValueError("descriptor novelty does not cover the exact sample set")
    return values


def select_samples(  # noqa: C901 - selection keeps all scientific priorities explicit.
    predictions: list[dict[str, Any]],
    *,
    boundary_pairs: list[dict[str, Any]],
    minimum: int,
    maximum: int,
    committee_rows: dict[str, dict[str, Any]] | None = None,
    descriptor_novelty: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    path_rows = sorted(
        (row for row in predictions if row["sample_id"].startswith("pre_")),
        key=lambda row: int(row["image"]),
    )
    if len(path_rows) < 5 or [int(row["image"]) for row in path_rows] != list(range(len(path_rows))):
        raise ValueError("predictions do not contain one complete contiguous preconditioning path")
    if minimum < 5 or maximum < minimum:
        raise ValueError("invalid label selection limits")
    internal = path_rows[1:-1]
    peak = max(internal, key=lambda row: float(row["primary_energy_eV"]))
    peak_index = int(peak["image"])
    count = len(path_rows)
    by_id = {str(row["sample_id"]): row for row in predictions}
    reasons: dict[str, set[str]] = {}

    def add(sample_id: str, reason: str) -> None:
        if sample_id not in by_id:
            raise ValueError(f"required active-learning sample is missing: {sample_id}")
        reasons.setdefault(sample_id, set()).add(reason)

    add(str(peak["sample_id"]), "MatRIS_TS_like_highest_predicted_energy")
    if "sella_final" in by_id:
        add("sella_final", "Sella_candidate_requires_exact_VASP_label")
    if peak_index > 1:
        add(f"pre_{max(1, peak_index // 2):02d}", "rising_path_representative")
    if peak_index < count - 2:
        falling_index = min(
            count - 2, peak_index + max(1, (count - 1 - peak_index) // 2)
        )
        add(f"pre_{falling_index:02d}", "falling_path_representative")

    for pair in boundary_pairs:
        add(str(pair["last_geometry_valid_sample"]), "last_geometry_valid_point")
        add(
            str(pair["first_geometry_valid_failure_sample"]),
            "first_geometry_valid_failure_point",
        )
    if boundary_pairs:
        largest_backtrack = max(
            boundary_pairs,
            key=lambda row: abs(
                float(row["reaction_coordinate_after_A"])
                - float(row["reaction_coordinate_before_A"])
            ),
        )
        add(
            str(largest_backtrack["first_geometry_valid_failure_sample"]),
            "maximum_reaction_coordinate_backtrack_boundary",
        )

    committee_rows = committee_rows or {}
    descriptor_novelty = descriptor_novelty or {}
    if committee_rows:
        committee_sample = max(
            committee_rows,
            key=lambda sample_id: (
                float(committee_rows[sample_id]["force_disagreement_eV_per_A"]),
                float(committee_rows[sample_id]["relative_energy_disagreement_eV"]),
            ),
        )
        add(committee_sample, "maximum_MatRIS_committee_disagreement")
    else:
        audit_sample = max(
            (row for row in predictions if row["sample_id"] not in {"pre_00", f"pre_{count - 1:02d}"}),
            key=lambda row: float(row["movable_force_difference"]["vector_max_eV_per_A"]),
        )
        add(str(audit_sample["sample_id"]), "maximum_external_auditor_disagreement")

    eligible = [
        row
        for row in predictions
        if row["sample_id"] not in {"pre_00", f"pre_{count - 1:02d}"}
    ]
    boundary_images = [int(row["image"]) for row in boundary_pairs]
    signal_values: dict[str, dict[str, float]] = {
        "external_auditor_disagreement": {
            row["sample_id"]: float(row["movable_force_difference"]["vector_max_eV_per_A"])
            for row in eligible
        },
        "ts_proximity": {
            row["sample_id"]: -abs(
                float(row["primary_energy_eV"]) - float(peak["primary_energy_eV"])
            )
            for row in eligible
        },
        "failure_boundary_proximity": {
            row["sample_id"]: (
                -min(abs(int(row["image"]) - image) for image in boundary_images)
                if boundary_images
                else 0.0
            )
            for row in eligible
        },
    }
    if committee_rows:
        signal_values["committee_force_disagreement"] = {
            sample_id: float(row["force_disagreement_eV_per_A"])
            for sample_id, row in committee_rows.items()
            if sample_id in by_id
        }
        signal_values["committee_relative_energy_disagreement"] = {
            sample_id: float(row["relative_energy_disagreement_eV"])
            for sample_id, row in committee_rows.items()
            if sample_id in by_id
        }
    if descriptor_novelty:
        signal_values["descriptor_novelty"] = {
            sample_id: float(value)
            for sample_id, value in descriptor_novelty.items()
            if sample_id in by_id
        }
    ranked_signals = {name: _percentile_ranks(values) for name, values in signal_values.items()}
    scores: dict[str, dict[str, Any]] = {}
    for row in eligible:
        sample_id = str(row["sample_id"])
        available = {
            name: ranks[sample_id]
            for name, ranks in ranked_signals.items()
            if sample_id in ranks
        }
        scores[sample_id] = {
            "available_signal_percentiles": available,
            "composite_rank_score": sum(available.values()) / len(available),
            "interpretation": "sampling_priority_only_not_calibrated_uncertainty",
        }

    # Sella can return the unchanged peak. Merge exact duplicates before spending labels.
    mandatory_ids = []
    mandatory_by_hash = {}
    for sample_id in reasons:
        digest = by_id[sample_id]["structure_sha256"]
        if digest in mandatory_by_hash:
            reasons[mandatory_by_hash[digest]].update(reasons[sample_id])
        else:
            mandatory_by_hash[digest] = sample_id
            mandatory_ids.append(sample_id)
    if len(mandatory_ids) > maximum:
        raise ValueError("mandatory active-learning roles exceed maximum labels per round")
    selected_ids = list(mandatory_ids)
    selected_hashes = {by_id[sample_id]["structure_sha256"] for sample_id in selected_ids}
    selected_bins = {
        round(float(by_id[sample_id]["reaction_coordinate_value_A"]) / 0.10)
        for sample_id in selected_ids
    }
    for sample_id in sorted(scores, key=lambda value: (-scores[value]["composite_rank_score"], value)):
        if len(selected_ids) >= maximum:
            break
        row = by_id[sample_id]
        coordinate_bin = round(float(row["reaction_coordinate_value_A"]) / 0.10)
        if row["structure_sha256"] in selected_hashes or coordinate_bin in selected_bins:
            continue
        reasons.setdefault(sample_id, set()).add("composite_sampling_score_fill")
        selected_ids.append(sample_id)
        selected_hashes.add(row["structure_sha256"])
        selected_bins.add(coordinate_bin)
    if len(selected_ids) < minimum:
        raise ValueError("clustering left too few distinct VASP label structures")

    selected: list[dict[str, Any]] = []
    for sample_id in selected_ids:
        row = by_id[sample_id]
        row_reasons = reasons[sample_id]
        if "first_geometry_valid_failure_point" in row_reasons:
            role = "first_geometry_valid_failure_point"
        elif "last_geometry_valid_point" in row_reasons:
            role = "last_geometry_valid_point"
        elif ("MatRIS_TS_like_highest_predicted_energy" in row_reasons
              or "Sella_candidate_requires_exact_VASP_label" in row_reasons):
            role = "ts_like"
        elif int(row["image"]) < peak_index:
            role = "rising_path"
        elif int(row["image"]) > peak_index:
            role = "falling_path"
        else:
            role = "high_information"
        selected.append(
            {
                "sample_id": row["sample_id"],
                "image": row["image"],
                "role": role,
                "reasons": sorted(row_reasons),
                "structure_sha256": row["structure_sha256"],
                "primary_energy_eV": row["primary_energy_eV"],
                "secondary_energy_eV": row["secondary_energy_eV"],
                "model_disagreement": row["movable_force_difference"],
                "reaction_coordinate_value_A": row["reaction_coordinate_value_A"],
                "candidate_score": scores[sample_id],
            }
        )
    return selected


def prepare_vasp_labels(  # noqa: C901 - preparation is one linear evidence gate.
    state_path: Path,
    prediction_path: Path,
    destination: Path,
    *,
    profile_path: Path,
    committee_assessment_path: Path | None = None,
    descriptor_novelty_path: Path | None = None,
) -> dict[str, Any]:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"destination is not empty: {destination}")
    state = load_json_object(state_path)
    predictions = load_json_object(prediction_path)
    if state.get("document_kind") != "dual_model_ts_active_learning_state":
        raise ValueError("invalid dual-model active-learning state")
    if state.get("status") != "awaiting_exact_dual_model_gpu_predictions":
        raise ValueError("active-learning round is not awaiting predictions")
    request_path = Path(state["prediction_batch"]["path"])
    if sha256_file(request_path) != state["prediction_batch"]["sha256"]:
        raise ValueError("prediction request changed after round preparation")
    request = load_json_object(request_path)
    if predictions.get("document_kind") != "dual_model_ts_path_force_prediction_set":
        raise ValueError("invalid dual-model prediction set")
    if predictions.get("source_request_sha256") != sha256_file(request_path):
        raise ValueError("prediction set is not bound to the round request")
    requested = {row["sample_id"]: row for row in request["structures"]}
    predicted = {row["sample_id"]: row for row in predictions.get("predictions", [])}
    if set(requested) != set(predicted):
        raise ValueError("prediction result sample set mismatch")
    for sample_id, row in predicted.items():
        if row.get("structure_sha256") != requested[sample_id]["sha256"]:
            raise ValueError(f"prediction structure hash mismatch: {sample_id}")
        for name in ("primary_energy_eV", "secondary_energy_eV"):
            if not math.isfinite(float(row[name])):
                raise ValueError(f"non-finite {name}: {sample_id}")

    policy_path = Path(state["source_bindings"]["policy"]["path"])
    if sha256_file(policy_path) != state["source_bindings"]["policy"]["sha256"]:
        raise ValueError("active-learning policy changed after round initialization")
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    source_names = ("candidate_manifest", "candidate_review", "source_request") if "candidate_method" in state else (
        "failure_guard", "snapshot_manifest")
    if state.get("candidate_method") == "ml_neb_sella":
        source_names += ("sella_manifest",)
    for name in source_names:
        reference = state["source_bindings"][name]
        path = Path(reference["path"])
        if not path.is_file() or sha256_file(path) != reference["sha256"]:
            raise ValueError(f"{name} evidence changed after round initialization")
    selected = select_samples(
        list(predicted.values()),
        boundary_pairs=list(state["round_trigger"].get("failure_boundary_pairs", [])),
        minimum=int(policy["sampling"]["minimum_vasp_labels_per_round"]),
        maximum=int(policy["sampling"]["maximum_vasp_labels_per_round"]),
        committee_rows=_load_committee_rows(committee_assessment_path, predicted),
        descriptor_novelty=_load_descriptor_novelty(descriptor_novelty_path, predicted),
    )

    destination.mkdir(parents=True, exist_ok=True)
    labels: list[dict[str, Any]] = []
    for selection in selected:
        source_row = requested[selection["sample_id"]]
        source = request_path.parent / source_row["path"]
        sample_dir = destination / selection["sample_id"]
        sample_dir.mkdir()
        target = sample_dir / "POSCAR"
        shutil.copy2(source, target)
        if sha256_file(target) != selection["structure_sha256"]:
            raise RuntimeError(f"copied VASP label structure changed: {selection['sample_id']}")
        inputs = build_fe110_active_learning_force_label(sample_dir, profile_path=profile_path)
        label_request = {
            "schema_version": 1,
            "document_kind": "dual_model_ts_vasp_force_label_request",
            "reaction_id": state["reaction_id"],
            "round_index": state["round_index"],
            "sample_id": selection["sample_id"],
            "image": selection["image"],
            "role": selection["role"],
            "reasons": selection["reasons"],
            "candidate_score": selection["candidate_score"],
            "structure_sha256": selection["structure_sha256"],
            "prediction_set_sha256": sha256_file(prediction_path),
            "model_checkpoint_sha256": {
                role: predictions["models"][role]["checkpoint_sha256"]
                for role in ("primary", "secondary")
            },
            "requested_backend": "sunboquan-codex",
            "input_profile": inputs,
            "result_class": "vasp_completed_electronic_converged_force_label_only",
            "required_outputs": [
                "final_TOTEN",
                "complete_all_atom_force_block",
                "total_magnetic_moment",
                "atom_resolved_magnetic_moments",
            ],
            "reportable_final_energy": False,
            "automatic_submission": False,
        }
        request_file = sample_dir / "label_request.json"
        write_json_atomic(request_file, label_request, ensure_ascii=True)
        labels.append(
            {
                **selection,
                "directory": sample_dir.relative_to(destination).as_posix(),
                "label_request_sha256": sha256_file(request_file),
                "status": "prepared_not_submitted",
            }
        )

    batch = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_vasp_force_label_batch_request",
        "reaction_id": state["reaction_id"],
        "round_index": state["round_index"],
        "source_prediction_set_sha256": sha256_file(prediction_path),
        "labels": labels,
        "submission_policy": {
            "automatic_submission": False,
            "direct_gpu_to_vasp_handoff": False,
            "requires_separate_bounded_user_authorization": True,
        },
    }
    batch_path = destination / "path_label_batch_request.json"
    write_json_atomic(batch_path, batch, ensure_ascii=True)
    state["prediction_result"] = {
        "path": str(prediction_path.resolve()),
        "sha256": sha256_file(prediction_path),
        "status": "reviewed_for_sampling",
    }
    state["sampling_evidence"] = {
        "committee_assessment": (
            {
                "path": str(committee_assessment_path.resolve()),
                "sha256": sha256_file(committee_assessment_path),
                "status": "real_MatRIS_committee_available",
            }
            if committee_assessment_path
            else {"status": "unavailable_fallback_to_external_auditor_and_vasp_error"}
        ),
        "descriptor_novelty": (
            {
                "path": str(descriptor_novelty_path.resolve()),
                "sha256": sha256_file(descriptor_novelty_path),
            }
            if descriptor_novelty_path
            else {"status": "unavailable"}
        ),
    }
    state["selected_vasp_labels"] = labels
    state["vasp_label_batch"] = {
        "path": str(batch_path.resolve()),
        "sha256": sha256_file(batch_path),
        "status": "prepared_not_submitted",
    }
    state["status"] = "awaiting_bounded_VASP_force_label_authorization"
    state["scientific_status"] = "round_0_sampled_not_calibrated"
    write_json_atomic(state_path, state, ensure_ascii=True)
    return batch


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select dual-model TS structures and prepare VASP force labels without submission."
    )
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--committee-assessment", type=Path)
    parser.add_argument("--descriptor-novelty", type=Path)
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "configs" / "true_fe110_production.yaml"
    )
    args = parser.parse_args()
    batch = prepare_vasp_labels(
        args.state,
        args.predictions,
        args.destination,
        profile_path=args.profile,
        committee_assessment_path=args.committee_assessment,
        descriptor_novelty_path=args.descriptor_novelty,
    )
    print(
        json.dumps(
            {
                "status": "prepared_not_submitted",
                "label_count": len(batch["labels"]),
                "vasp_jobs_submitted": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
