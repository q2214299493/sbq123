#!/usr/bin/env python3
"""Prepare a review-only MatRIS replay fine-tuning package.

The package binds accepted TS labels, adsorption-retention replay data, and a
frozen held-out exclusion set.  It never submits or runs a GPU calculation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.matris_training_exclusions import (
    geometry_fingerprint,
    write_heldout_exclusion_manifest,
)
from scripts.neb_agent.utils_structure import read_poscar
from scripts.prepare_matris_finetune_request import preflight_and_prepare


LABEL_KIND = "dual_model_ts_vasp_force_label_set"
EXPECTED_CONVENTION = "fe110_converged_toten_sigma0p20_v1"


def _binding(path: Path) -> dict[str, str]:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256_file(path)}


def _fixed_indices(path: Path) -> list[int]:
    structure = read_poscar(path)
    if not structure.selective:
        return []
    return [
        index
        for index, flags in enumerate(structure.flags)
        if tuple(value.upper() for value in flags) == ("F", "F", "F")
    ]


def _validate_label_set(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = path.resolve()
    payload = load_json_object(path)
    if payload.get("document_kind") != LABEL_KIND:
        raise ValueError(f"invalid TS label set: {path}")
    if payload.get("scientific_status") != "accepted_force_labels_only":
        raise ValueError(f"TS label set is not accepted: {path}")
    checks = payload.get("checks", {})
    required_checks = (
        "all_scheduler_DONE",
        "all_normal_vasp_completion",
        "all_electronically_converged",
        "all_exact_structure_hashes_match",
        "all_complete_force_blocks",
    )
    if not all(checks.get(field) is True for field in required_checks):
        raise ValueError(f"TS label set quality checks failed: {path}")
    compatibility = payload.get("compatibility", {})
    if (
        compatibility.get("final_energy_convention") != EXPECTED_CONVENTION
        or compatibility.get("ISMEAR") != 1
        or float(compatibility.get("SIGMA_eV", -1.0)) != 0.2
    ):
        raise ValueError(f"incompatible TS label set: {path}")
    batch_path = Path(str(payload.get("source_batch_path", ""))).resolve()
    if (
        not batch_path.is_file()
        or sha256_file(batch_path) != payload.get("source_batch_sha256")
    ):
        raise ValueError(f"TS source batch binding failed: {path}")
    batch = load_json_object(batch_path)
    return payload, batch


def _ts_samples(label_set_path: Path, dataset_id: str) -> list[dict[str, Any]]:
    label_set, batch = _validate_label_set(label_set_path)
    batch_rows = {str(row["sample_id"]): row for row in batch.get("labels", [])}
    samples: list[dict[str, Any]] = []
    for label in label_set.get("labels", []):
        source_id = str(label.get("sample_id", ""))
        batch_row = batch_rows.get(source_id)
        if not source_id or not isinstance(batch_row, dict):
            raise ValueError(f"TS label lacks a source batch row: {source_id!r}")
        structure_path = label_set_path.resolve().parent / str(batch_row["directory"]) / "POSCAR"
        expected_hash = str(label.get("structure_sha256", ""))
        if not structure_path.is_file() or sha256_file(structure_path) != expected_hash:
            raise ValueError(f"TS structure binding failed: {dataset_id}/{source_id}")
        structure = read_poscar(structure_path)
        forces = np.asarray(label.get("vasp_forces_eV_per_A"), dtype=float)
        if forces.shape != (len(structure.labels), 3) or not np.isfinite(forces).all():
            raise ValueError(f"invalid TS force label: {dataset_id}/{source_id}")
        energy = float(label.get("vasp_energy_eV"))
        if not np.isfinite(energy):
            raise ValueError(f"invalid TS energy label: {dataset_id}/{source_id}")
        samples.append(
            {
                "sample_id": f"{dataset_id}::{source_id}",
                "source_sample_id": source_id,
                "dataset_role": "current_trigger_ts_labels"
                if dataset_id == "current_round"
                else "prior_ts_replay",
                "reaction_id": label_set["reaction_id"],
                "energy_group_id": "fe110_c2ho_h_to_c2h2o_50atom_sigma0p20",
                "structure": {
                    "path": str(structure_path.resolve()),
                    "sha256": expected_hash,
                    "geometry_sha256": geometry_fingerprint(structure),
                    "atom_count": len(structure.labels),
                },
                "fixed_atom_indices_zero_based": _fixed_indices(structure_path),
                "label_source": _binding(label_set_path),
                "vasp_label": {
                    "energy_eV": energy,
                    "force_count": int(forces.shape[0]),
                    "forces_embedded_in_source_label_set": True,
                    "reportable_final_energy": False,
                },
            }
        )
    if not samples:
        raise ValueError(f"empty TS label set: {label_set_path}")
    return samples


def _adsorption_samples(
    labels_path: Path,
    structures_root: Path,
    policy_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    labels_path = labels_path.resolve()
    structures_root = structures_root.resolve()
    policy_path = policy_path.resolve()
    labels = load_json_object(labels_path)
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    replay = policy.get("fine_tuning", {}).get("replay", {})
    validation_ids = {str(value) for value in replay.get("validation_sample_ids", [])}
    training: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    for label in labels.get("samples", []):
        source_id = str(label.get("sample_id", ""))
        structure_path = structures_root / f"{source_id}.vasp"
        expected_hash = str(label.get("structure_sha256", ""))
        if not source_id or not structure_path.is_file() or sha256_file(structure_path) != expected_hash:
            raise ValueError(f"adsorption structure binding failed: {source_id!r}")
        if label.get("normal_completion") is not True or label.get("ionic_converged") is not True:
            raise ValueError(f"adsorption label is not converged: {source_id}")
        structure = read_poscar(structure_path)
        forces = np.asarray(label.get("forces_eV_per_A"), dtype=float)
        if forces.shape != (len(structure.labels), 3) or not np.isfinite(forces).all():
            raise ValueError(f"invalid adsorption force label: {source_id}")
        energy = float(label.get("final_toten_eV"))
        if not np.isfinite(energy):
            raise ValueError(f"invalid adsorption energy label: {source_id}")
        row = {
            "sample_id": f"adsorption::{source_id}",
            "source_sample_id": source_id,
            "dataset_role": "adsorption_retention_validation"
            if source_id in validation_ids
            else "adsorption_replay_training",
            "reaction_id": None,
            "energy_group_id": None,
            "structure": {
                "path": str(structure_path),
                "sha256": expected_hash,
                "geometry_sha256": geometry_fingerprint(structure),
                "atom_count": len(structure.labels),
            },
            "fixed_atom_indices_zero_based": [
                int(value) - 1 for value in label.get("fixed_atom_indices_1based", [])
            ],
            "label_source": _binding(labels_path),
            "vasp_label": {
                "energy_eV": energy,
                "force_count": int(forces.shape[0]),
                "forces_embedded_in_source_label_set": True,
                "reportable_final_energy": True,
            },
        }
        (validation if source_id in validation_ids else training).append(row)
    minimum_training = int(replay.get("minimum_training_samples", 0))
    minimum_validation = int(replay.get("minimum_validation_samples", 0))
    if len(training) < minimum_training or len(validation) < minimum_validation:
        raise ValueError("adsorption replay split is below its configured minimum")
    metadata = {
        "labels": _binding(labels_path),
        "structures_root": str(structures_root),
        "policy": _binding(policy_path),
        "configured_validation_sample_ids": sorted(validation_ids),
        "minimum_training_samples": minimum_training,
        "minimum_validation_samples": minimum_validation,
    }
    return training, validation, metadata


def _validate_ts_system_compatibility(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("no TS samples to validate")
    reference_path = Path(samples[0]["structure"]["path"])
    reference = read_poscar(reference_path)
    reference_fixed = _fixed_indices(reference_path)
    for sample in samples[1:]:
        path = Path(sample["structure"]["path"])
        structure = read_poscar(path)
        if structure.labels != reference.labels:
            raise ValueError(f"TS atom-order mismatch: {sample['sample_id']}")
        if not np.allclose(structure.cell, reference.cell, atol=1.0e-8, rtol=0.0):
            raise ValueError(f"TS cell mismatch: {sample['sample_id']}")
        if _fixed_indices(path) != reference_fixed:
            raise ValueError(f"TS fixed-layer mismatch: {sample['sample_id']}")
    return {
        "sample_count": len(samples),
        "atom_count": len(reference.labels),
        "atom_order_identical": True,
        "cell_identical": True,
        "fixed_layer_identical": True,
    }


def _rebind_heldout_plan(
    source_path: Path,
    *,
    reaction_id: str,
    round_index: int,
    output: Path,
) -> Path:
    source_path = source_path.resolve()
    source = load_json_object(source_path)
    if source.get("document_kind") != "dual_model_ts_heldout_validation_candidate_plan":
        raise ValueError("invalid source held-out plan")
    rebound = dict(source)
    rebound["reaction_id"] = reaction_id
    rebound["round_index"] = round_index
    rebound["source_frozen_heldout_plan"] = _binding(source_path)
    rebound["reuse_scope"] = (
        "same Fe45-C2-O-H2 chemistry and SIGMA=0.20 TS domain; immutable structures"
    )
    candidates: list[dict[str, Any]] = []
    for candidate in source.get("candidates", []):
        row = dict(candidate)
        structure_path = source_path.parent / str(candidate["structure_path"])
        if not structure_path.is_file() or sha256_file(structure_path) != candidate.get(
            "structure_sha256"
        ):
            raise ValueError(f"source held-out binding failed: {candidate.get('sample_id')}")
        row["structure_path"] = str(structure_path.resolve())
        candidates.append(row)
    rebound["candidates"] = candidates
    write_json_atomic(output, rebound, ensure_ascii=True)
    return output


def _assert_disjoint(
    samples: Iterable[dict[str, Any]], exclusion_manifest: dict[str, Any]
) -> dict[str, int]:
    excluded_exact = {
        str(row["structure_sha256"])
        for row in exclusion_manifest["excluded_structures"]
    }
    excluded_geometry = {
        str(row["geometry_sha256"])
        for row in exclusion_manifest["excluded_structures"]
    }
    seen_exact: set[str] = set()
    seen_geometry: set[str] = set()
    count = 0
    for sample in samples:
        exact = str(sample["structure"]["sha256"])
        geometry = str(sample["structure"]["geometry_sha256"])
        sample_id = str(sample["sample_id"])
        if exact in excluded_exact or geometry in excluded_geometry:
            raise ValueError(f"training/replay sample overlaps frozen held-out: {sample_id}")
        if exact in seen_exact or geometry in seen_geometry:
            raise ValueError(f"duplicate training/replay structure: {sample_id}")
        seen_exact.add(exact)
        seen_geometry.add(geometry)
        count += 1
    return {
        "training_and_replay_sample_count_checked": count,
        "frozen_heldout_structure_count": len(excluded_exact),
        "exact_overlap_count": 0,
        "rounded_geometry_overlap_count": 0,
    }


def _validate_frozen_heldout_labels(
    samples: list[dict[str, Any]], exclusion_manifest: dict[str, Any]
) -> dict[str, int]:
    excluded = {
        str(row["sample_id"]): (
            str(row["structure_sha256"]),
            str(row["geometry_sha256"]),
            bool(row["primary_metric_eligible"]),
        )
        for row in exclusion_manifest["excluded_structures"]
    }
    if len(samples) != len(excluded):
        raise ValueError("frozen held-out label count does not match exclusions")
    seen: set[str] = set()
    for sample in samples:
        source_id = str(sample["source_sample_id"])
        expected = excluded.get(source_id)
        actual = (
            str(sample["structure"]["sha256"]),
            str(sample["structure"]["geometry_sha256"]),
        )
        if expected is None or actual != expected[:2]:
            raise ValueError(f"frozen held-out label binding mismatch: {source_id}")
        sample["dataset_role"] = "frozen_ts_heldout_validation_only"
        sample["energy_group_id"] = "fe110_c2ho_h_to_c2h2o_50atom_sigma0p20"
        sample["primary_metric_eligible"] = expected[2]
        seen.add(source_id)
    if seen != set(excluded):
        raise ValueError("frozen held-out labels are incomplete")
    return {
        "heldout_label_count": len(samples),
        "primary_metric_label_count": sum(
            bool(sample["primary_metric_eligible"]) for sample in samples
        ),
        "diagnostic_only_label_count": sum(
            not bool(sample["primary_metric_eligible"]) for sample in samples
        ),
        "heldout_exclusion_count": len(excluded),
        "exact_and_geometry_bindings_match": True,
    }


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.state.resolve()
    state = load_json_object(state_path)
    if state.get("document_kind") != "dual_model_ts_active_learning_state":
        raise ValueError("invalid active-learning state")

    rebound_plan_path = output_dir / "frozen_heldout_reuse_plan.json"
    _rebind_heldout_plan(
        args.source_heldout_plan,
        reaction_id=str(state["reaction_id"]),
        round_index=int(state["round_index"]),
        output=rebound_plan_path,
    )
    exclusions_path = output_dir / "heldout_training_exclusions.json"
    write_heldout_exclusion_manifest(rebound_plan_path, exclusions_path)
    exclusions = load_json_object(exclusions_path)

    current_binding = state.get("vasp_label_batch", {})
    current_label_path = Path(str(current_binding.get("completed_label_set_path", ""))).resolve()
    if (
        current_label_path != args.current_ts_labels.resolve()
        or sha256_file(current_label_path)
        != current_binding.get("completed_label_set_sha256")
    ):
        raise ValueError("current TS label set does not match active state")

    ts_samples = _ts_samples(current_label_path, "current_round")
    prior_bindings: list[dict[str, str]] = []
    for index, path in enumerate(args.prior_ts_labels, start=1):
        resolved = path.resolve()
        ts_samples.extend(_ts_samples(resolved, f"prior_ts_{index}"))
        prior_bindings.append(_binding(resolved))
    ts_system_check = _validate_ts_system_compatibility(ts_samples)
    adsorption_training, adsorption_validation, adsorption_metadata = (
        _adsorption_samples(
            args.adsorption_labels,
            args.adsorption_structures,
            args.adsorption_policy,
        )
    )
    heldout_ts_samples = _ts_samples(args.heldout_ts_labels.resolve(), "heldout_ts")
    heldout_label_check = _validate_frozen_heldout_labels(
        heldout_ts_samples, exclusions
    )
    training_samples = ts_samples + adsorption_training
    disjointness = _assert_disjoint(training_samples, exclusions)

    replay_manifest_path = output_dir / "matris_replay_training_manifest.json"
    replay_manifest = {
        "schema_version": 1,
        "document_kind": "matris_energy_force_replay_manifest",
        "status": "prepared_review_only_not_submitted",
        "reaction_id": state["reaction_id"],
        "round_index": state["round_index"],
        "base_checkpoint_sha256": exclusions[
            "frozen_model_checkpoint_sha256"
        ]["primary"],
        "compatibility": {
            "final_energy_convention": EXPECTED_CONVENTION,
            "ISMEAR": 1,
            "SIGMA_eV": 0.2,
        },
        "sources": {
            "current_ts_labels": _binding(current_label_path),
            "prior_ts_labels": prior_bindings,
            "adsorption_replay": adsorption_metadata,
            "frozen_ts_heldout_labels": _binding(args.heldout_ts_labels.resolve()),
            "heldout_exclusion_manifest": _binding(exclusions_path),
        },
        "training_contract": {
            "current_and_prior_ts": [
                "movable_atom_vasp_forces",
                "within_system_relative_vasp_energies",
            ],
            "adsorption_replay": [
                "movable_atom_vasp_forces",
                "adsorption_domain_retention",
            ],
            "adsorption_energy_normalization": (
                "must use the reviewed MatRIS native reference-energy convention; "
                "do not mix raw total energies across stoichiometries as one relative-energy group"
            ),
            "force_tail_retention_required": True,
        },
        "training_samples": training_samples,
        "validation_only_samples": adsorption_validation,
        "frozen_ts_heldout_validation_samples": heldout_ts_samples,
        "counts": {
            "current_ts_training": sum(
                row["dataset_role"] == "current_trigger_ts_labels"
                for row in ts_samples
            ),
            "prior_ts_replay": sum(
                row["dataset_role"] == "prior_ts_replay" for row in ts_samples
            ),
            "adsorption_replay_training": len(adsorption_training),
            "adsorption_retention_validation": len(adsorption_validation),
            "frozen_ts_heldout_validation": len(heldout_ts_samples),
            "frozen_ts_primary_metric_validation": sum(
                bool(row["primary_metric_eligible"]) for row in heldout_ts_samples
            ),
            "total_optimizer_samples": len(training_samples),
        },
        "heldout_leakage_check": disjointness,
        "ts_system_compatibility_check": ts_system_check,
        "frozen_ts_heldout_label_check": heldout_label_check,
        "execution_authorized": False,
        "automatic_submission": False,
    }
    write_json_atomic(replay_manifest_path, replay_manifest, ensure_ascii=True)

    canonical_request_path = output_dir / "canonical_matris_finetune_request.json"
    canonical_preflight_path = output_dir / "canonical_matris_finetune_preflight.json"
    exclusion_sha = sha256_file(exclusions_path)
    preflight = preflight_and_prepare(
        state_path,
        exclusions_path,
        expected_exclusion_sha256=exclusion_sha,
        request_output=canonical_request_path,
        preflight_output=canonical_preflight_path,
    )
    if not preflight.get("passed"):
        raise ValueError(f"canonical MatRIS fine-tune preflight failed: {preflight['blockers']}")

    review_request_path = output_dir / "matris_replay_finetune_review_request.json"
    review_request = {
        "schema_version": 1,
        "document_kind": "matris_energy_force_replay_finetune_review_request",
        "status": "prepared_awaiting_separate_gpu_finetune_authorization",
        "reaction_id": state["reaction_id"],
        "round_index": state["round_index"],
        "base_checkpoint_sha256": exclusions[
            "frozen_model_checkpoint_sha256"
        ]["primary"],
        "canonical_finetune_request": _binding(canonical_request_path),
        "canonical_preflight": _binding(canonical_preflight_path),
        "replay_training_manifest": _binding(replay_manifest_path),
        "heldout_exclusion_manifest": _binding(exclusions_path),
        "heldout_source_plan": _binding(args.source_heldout_plan.resolve()),
        "review_summary": {
            "current_ts_label_count": replay_manifest["counts"][
                "current_ts_training"
            ],
            "prior_ts_replay_count": replay_manifest["counts"]["prior_ts_replay"],
            "adsorption_replay_training_count": replay_manifest["counts"][
                "adsorption_replay_training"
            ],
            "adsorption_retention_validation_count": replay_manifest["counts"][
                "adsorption_retention_validation"
            ],
            "frozen_heldout_count": disjointness["frozen_heldout_structure_count"],
            "frozen_heldout_vasp_label_count": replay_manifest["counts"][
                "frozen_ts_heldout_validation"
            ],
            "frozen_heldout_primary_metric_count": replay_manifest["counts"][
                "frozen_ts_primary_metric_validation"
            ],
            "heldout_overlap_count": 0,
        },
        "submission_boundary": {
            "gpu_finetune_authorized": False,
            "new_checkpoint_path_rerun_authorized": False,
            "automatic_submission": False,
            "separate_user_authorization_required": True,
        },
        "required_before_gpu_submission": [
            "review this hash-bound request and replay split",
            "validate the energy-and-force-aware executor against the exact MatRIS runtime and frozen base checkpoint in a bounded no-promotion MZ73 smoke",
            "bind the MZ73 submission to this review-request SHA-256 and the frozen base checkpoint",
        ],
        "post_training_acceptance": [
            "new checkpoint SHA-256 differs from the base checkpoint",
            "frozen TS held-out force and relative-energy metrics pass",
            "force-tail and adsorption-retention metrics do not regress",
            "complete MatRIS path is rerun with the accepted new checkpoint",
            "AQCat25 performs exact-structure audit of the returned complete path",
        ],
        "scientific_limits": {
            "this_request_is_not_a_gpu_result": True,
            "labels_are_not_final_barrier_energies": True,
            "heldout_structures_are_never_optimizer_or_replay_samples": True,
        },
    }
    write_json_atomic(review_request_path, review_request, ensure_ascii=True)
    return {
        "status": "prepared_review_only_not_submitted",
        "review_request": _binding(review_request_path),
        "replay_manifest": _binding(replay_manifest_path),
        "heldout_exclusions": _binding(exclusions_path),
        "counts": replay_manifest["counts"],
        "heldout_leakage_check": disjointness,
        "gpu_submission_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--source-heldout-plan", type=Path, required=True)
    parser.add_argument("--current-ts-labels", type=Path, required=True)
    parser.add_argument(
        "--prior-ts-labels", type=Path, action="append", default=[], required=True
    )
    parser.add_argument("--adsorption-labels", type=Path, required=True)
    parser.add_argument("--adsorption-structures", type=Path, required=True)
    parser.add_argument("--adsorption-policy", type=Path, required=True)
    parser.add_argument("--heldout-ts-labels", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


if __name__ == "__main__":
    print(json.dumps(prepare(build_parser().parse_args()), ensure_ascii=False))
