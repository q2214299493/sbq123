#!/usr/bin/env python3
"""Evaluate an exact TS path with three to five accepted MatRIS checkpoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.dual_model_ts_force_prediction_batch import (
    CalculatorLoader,
    _predict_all,
    validate_request,
)
from scripts.mlip_same_structure_benchmark import _load_calculator


def validate_committee_request(
    committee_path: Path, prediction_request_path: Path
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    committee = load_json_object(committee_path)
    prediction_request, structures = validate_request(prediction_request_path)
    if committee.get("schema_version") != 1 or committee.get("document_kind") != (
        "matris_ts_path_committee_request"
    ):
        raise ValueError("invalid MatRIS TS committee request")
    if committee.get("automatic_submission") is not False:
        raise ValueError("committee automatic_submission must be false")
    if committee.get("source_prediction_request_sha256") != sha256_file(
        prediction_request_path
    ):
        raise ValueError("committee is not bound to the exact prediction request")
    members = committee.get("members")
    if not isinstance(members, list) or not 3 <= len(members) <= 5:
        raise ValueError("MatRIS committee requires three to five members")
    checkpoint_hashes: set[str] = set()
    architecture_identifiers: set[str] = set()
    member_ids: set[str] = set()
    for member in members:
        if not isinstance(member, dict) or member.get("backend") != "matris":
            raise ValueError("every committee member must use the MatRIS backend")
        member_id = str(member.get("member_id", ""))
        checkpoint_sha = str(member.get("checkpoint_sha256", ""))
        architecture = str(member.get("architecture_identifier", ""))
        if not member_id or member_id in member_ids:
            raise ValueError("committee member IDs must be non-empty and unique")
        if len(checkpoint_sha) != 64 or checkpoint_sha in checkpoint_hashes:
            raise ValueError("committee checkpoint hashes must be unique SHA-256 values")
        if not architecture:
            raise ValueError("committee architecture identifier is missing")
        if member.get("production_acceptance_passed") is not True:
            raise ValueError("committee member lacks production checkpoint acceptance")
        if len(str(member.get("training_run_sha256", ""))) != 64:
            raise ValueError("committee member lacks independent training provenance")
        member_ids.add(member_id)
        checkpoint_hashes.add(checkpoint_sha)
        architecture_identifiers.add(architecture)
    if len(architecture_identifiers) != 1:
        raise ValueError("committee members must share one MatRIS architecture")
    return committee, prediction_request, structures


def run_committee(
    committee_path: Path,
    prediction_request_path: Path,
    output_path: Path,
    *,
    device: str,
    calculator_loader: CalculatorLoader = _load_calculator,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    committee, prediction_request, structures = validate_committee_request(
        committee_path, prediction_request_path
    )
    member_predictions: list[list[tuple[float, np.ndarray]]] = []
    for member in committee["members"]:
        checkpoint = Path(member["checkpoint_path"])
        if not checkpoint.is_file() or sha256_file(checkpoint) != member["checkpoint_sha256"]:
            raise ValueError(f"committee checkpoint hash mismatch: {member['member_id']}")
        member_predictions.append(
            _predict_all(
                structures,
                backend="matris",
                checkpoint=checkpoint,
                device=device,
                indexed_bond_changes=prediction_request["indexed_bond_changes"],
                calculator_loader=calculator_loader,
            )
        )

    reference_index = next(
        (
            index
            for index, row in enumerate(structures)
            if row["sample_id"] == committee.get("relative_energy_reference_sample", "pre_00")
        ),
        None,
    )
    if reference_index is None:
        raise ValueError("committee relative-energy reference sample is missing")
    fixed = set(prediction_request["fixed_atom_indices_zero_based"])
    records: list[dict[str, Any]] = []
    for sample_index, structure in enumerate(structures):
        energies = np.asarray(
            [member[sample_index][0] for member in member_predictions], dtype=float
        )
        relative_energies = np.asarray(
            [
                member[sample_index][0] - member[reference_index][0]
                for member in member_predictions
            ],
            dtype=float,
        )
        force_stack = np.asarray(
            [member[sample_index][1] for member in member_predictions], dtype=float
        )
        movable = [index for index in range(force_stack.shape[1]) if index not in fixed]
        component_std = np.std(force_stack[:, movable, :], axis=0, ddof=0)
        vector_std = np.linalg.norm(component_std, axis=1)
        values = (
            energies,
            relative_energies,
            force_stack,
            component_std,
            vector_std,
        )
        if any(not np.isfinite(value).all() for value in values):
            raise RuntimeError(f"non-finite committee result: {structure['sample_id']}")
        records.append(
            {
                "sample_id": structure["sample_id"],
                "image": structure["image"],
                "structure_sha256": structure["sha256"],
                "member_energies_eV": energies.tolist(),
                "member_relative_energies_eV": relative_energies.tolist(),
                "relative_energy_disagreement_eV": float(np.std(relative_energies)),
                "force_disagreement_eV_per_A": (
                    float(vector_std.max()) if len(vector_std) else 0.0
                ),
                "force_component_std_rms_eV_per_A": float(
                    np.sqrt(np.mean(component_std**2))
                ),
            }
        )
    result = {
        "schema_version": 1,
        "document_kind": "matris_ts_path_committee_prediction_set",
        "source_committee_request_sha256": sha256_file(committee_path),
        "source_prediction_request_sha256": sha256_file(prediction_request_path),
        "members": [
            {
                "member_id": member["member_id"],
                "checkpoint_sha256": member["checkpoint_sha256"],
                "architecture_identifier": member["architecture_identifier"],
                "training_run_sha256": member["training_run_sha256"],
            }
            for member in committee["members"]
        ],
        "relative_energy_reference_sample": committee.get(
            "relative_energy_reference_sample", "pre_00"
        ),
        "predictions": records,
        "interpretation": "committee_disagreement_for_sampling_not_quantitative_uncertainty_until_heldout_calibration",
        "automatic_submission": False,
    }
    write_json_atomic(output_path, result, ensure_ascii=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an exact-path MatRIS checkpoint committee.")
    parser.add_argument("--committee", type=Path, required=True)
    parser.add_argument("--prediction-request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    committee, _, structures = validate_committee_request(
        args.committee, args.prediction_request
    )
    if args.validate_only:
        print(
            json.dumps(
                {
                    "status": "valid",
                    "member_count": len(committee["members"]),
                    "sample_count": len(structures),
                },
                indent=2,
            )
        )
        return
    result = run_committee(
        args.committee,
        args.prediction_request,
        args.output,
        device=args.device,
    )
    print(json.dumps({"status": "complete", "sample_count": len(result["predictions"])}, indent=2))


if __name__ == "__main__":
    main()
