#!/usr/bin/env python3
"""Validate or run hash-bound MatRIS energy-and-force replay fine-tuning.

The ``preflight`` and ``self-test`` commands are local and never load MatRIS.
The ``train`` command additionally requires an explicit hash-bound execution
authorization and produces a review-only checkpoint candidate.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.matris_finetune_speed_benchmark import (
    configure_trainable_parameters,
    load_model,
    predict_one,
    save_checkpoint,
)
from scripts.matris_training_exclusions import (
    geometry_fingerprint,
    load_heldout_exclusions,
)
from scripts.neb_agent.utils_structure import read_poscar


REVIEW_KIND = "matris_energy_force_replay_finetune_review_request"
MANIFEST_KIND = "matris_energy_force_replay_manifest"
AUTHORIZATION_KIND = "matris_energy_force_finetune_execution_authorization"
RETENTION_METRIC_KEYS = (
    "component_rmse_eV_per_A",
    "vector_rmse_eV_per_A",
    "vector_p95_eV_per_A",
    "vector_max_eV_per_A",
)
CORE_RETENTION_METRIC_KEYS = RETENTION_METRIC_KEYS[:-1]


def _load_bound(reference: dict[str, Any], *, name: str) -> tuple[Path, dict[str, Any]]:
    path = Path(str(reference.get("path", ""))).resolve()
    expected = str(reference.get("sha256", ""))
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{name} binding failed")
    return path, load_json_object(path)


def _source_labels(reference: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _, payload = _load_bound(reference, name="VASP label source")
    if payload.get("document_kind") == "dual_model_ts_vasp_force_label_set":
        return {
            str(row["sample_id"]): {
                "energy_eV": float(row["vasp_energy_eV"]),
                "forces_eV_per_A": row["vasp_forces_eV_per_A"],
            }
            for row in payload.get("labels", [])
        }
    if payload.get("calibration_id") and isinstance(payload.get("samples"), list):
        return {
            str(row["sample_id"]): {
                "energy_eV": float(row["final_toten_eV"]),
                "forces_eV_per_A": row["forces_eV_per_A"],
            }
            for row in payload["samples"]
        }
    raise ValueError("unsupported VASP label source")


def _hydrate_samples(
    samples: Iterable[dict[str, Any]],
    *,
    label_cache: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    hydrated: list[dict[str, Any]] = []
    for source in samples:
        sample = dict(source)
        structure_ref = dict(sample.get("structure", {}))
        structure_path = Path(str(structure_ref.get("path", ""))).resolve()
        if (
            not structure_path.is_file()
            or sha256_file(structure_path) != structure_ref.get("sha256")
        ):
            raise ValueError(f"training structure binding failed: {sample.get('sample_id')}")
        structure = read_poscar(structure_path)
        if geometry_fingerprint(structure) != structure_ref.get("geometry_sha256"):
            raise ValueError(f"training geometry binding failed: {sample.get('sample_id')}")
        if len(structure.labels) != int(structure_ref.get("atom_count", -1)):
            raise ValueError(f"training atom count failed: {sample.get('sample_id')}")

        label_ref = sample.get("label_source")
        if not isinstance(label_ref, dict):
            raise ValueError("sample lacks a label-source binding")
        source_key = f"{label_ref.get('path')}::{label_ref.get('sha256')}"
        if source_key not in label_cache:
            label_cache[source_key] = _source_labels(label_ref)
        label = label_cache[source_key].get(str(sample.get("source_sample_id", "")))
        if not isinstance(label, dict):
            raise ValueError(f"VASP label row missing: {sample.get('sample_id')}")
        forces = np.asarray(label["forces_eV_per_A"], dtype=float)
        if forces.shape != (len(structure.labels), 3) or not np.isfinite(forces).all():
            raise ValueError(f"invalid VASP forces: {sample.get('sample_id')}")
        energy = float(label["energy_eV"])
        if not np.isfinite(energy) or not math.isclose(
            energy,
            float(sample["vasp_label"]["energy_eV"]),
            abs_tol=1.0e-8,
            rel_tol=0.0,
        ):
            raise ValueError(f"VASP energy binding failed: {sample.get('sample_id')}")
        sample["structure_path"] = str(structure_path)
        sample["reference_energy_eV"] = energy
        sample["reference_forces_eV_per_A"] = forces.tolist()
        hydrated.append(sample)
    return hydrated


def validate_review_package(review_path: Path) -> dict[str, Any]:
    review_path = review_path.resolve()
    review = load_json_object(review_path)
    if review.get("document_kind") != REVIEW_KIND:
        raise ValueError("invalid MatRIS replay fine-tune review request")
    if review.get("status") != "prepared_awaiting_separate_gpu_finetune_authorization":
        raise ValueError("fine-tune review request is not ready")
    selection_policy = _checkpoint_selection_policy(review)
    manifest_path, manifest = _load_bound(
        review.get("replay_training_manifest", {}), name="replay training manifest"
    )
    if manifest.get("document_kind") != MANIFEST_KIND:
        raise ValueError("invalid MatRIS replay manifest")
    if manifest.get("execution_authorized") is not False:
        raise ValueError("review manifest unexpectedly authorizes execution")
    exclusion_path, _ = _load_bound(
        review.get("heldout_exclusion_manifest", {}), name="held-out exclusions"
    )
    exclusions = load_heldout_exclusions(
        exclusion_path,
        expected_sha256=review["heldout_exclusion_manifest"]["sha256"],
    )
    if manifest.get("base_checkpoint_sha256") != review.get("base_checkpoint_sha256"):
        raise ValueError("base checkpoint mismatch")

    label_cache: dict[str, dict[str, dict[str, Any]]] = {}
    training = _hydrate_samples(
        manifest.get("training_samples", []), label_cache=label_cache
    )
    adsorption_validation = _hydrate_samples(
        manifest.get("validation_only_samples", []), label_cache=label_cache
    )
    heldout_validation = _hydrate_samples(
        manifest.get("frozen_ts_heldout_validation_samples", []),
        label_cache=label_cache,
    )

    excluded_exact = {
        str(row["structure_sha256"]): str(row["geometry_sha256"])
        for row in exclusions["excluded_structures"]
    }
    training_exact: set[str] = set()
    training_geometry: set[str] = set()
    for sample in training:
        exact = str(sample["structure"]["sha256"])
        geometry = str(sample["structure"]["geometry_sha256"])
        if exact in excluded_exact or geometry in excluded_exact.values():
            raise ValueError(f"training sample leaks held-out data: {sample['sample_id']}")
        if exact in training_exact or geometry in training_geometry:
            raise ValueError(f"duplicate optimizer structure: {sample['sample_id']}")
        training_exact.add(exact)
        training_geometry.add(geometry)
    heldout_pairs = {
        (str(sample["structure"]["sha256"]), str(sample["structure"]["geometry_sha256"]))
        for sample in heldout_validation
    }
    if heldout_pairs != set(excluded_exact.items()):
        raise ValueError("held-out validation labels do not exactly match exclusions")

    expected_counts = manifest.get("counts", {})
    if len(training) != int(expected_counts.get("total_optimizer_samples", -1)):
        raise ValueError("optimizer sample count mismatch")
    if len(heldout_validation) != int(
        expected_counts.get("frozen_ts_heldout_validation", -1)
    ):
        raise ValueError("held-out validation count mismatch")
    return {
        "review_path": review_path,
        "review": review,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "exclusion_path": exclusion_path,
        "training_samples": training,
        "adsorption_validation_samples": adsorption_validation,
        "heldout_validation_samples": heldout_validation,
        "validation_summary": {
            "optimizer_sample_count": len(training),
            "ts_energy_force_sample_count": sum(
                sample.get("energy_group_id") is not None for sample in training
            ),
            "adsorption_force_replay_count": sum(
                sample.get("dataset_role") == "adsorption_replay_training"
                for sample in training
            ),
            "adsorption_retention_validation_count": len(adsorption_validation),
            "frozen_ts_heldout_validation_count": len(heldout_validation),
            "frozen_ts_primary_metric_count": sum(
                bool(sample.get("primary_metric_eligible"))
                for sample in heldout_validation
            ),
            "heldout_exact_overlap_count": 0,
            "heldout_geometry_overlap_count": 0,
            "checkpoint_selection_policy": selection_policy["kind"],
        },
    }


def energy_anchor_ids(samples: Iterable[dict[str, Any]]) -> dict[str, str]:
    groups: dict[str, list[str]] = {}
    for sample in samples:
        group = sample.get("energy_group_id")
        if group is not None:
            groups.setdefault(str(group), []).append(str(sample["sample_id"]))
    return {group: sorted(sample_ids)[0] for group, sample_ids in groups.items()}


def combined_loss(
    *,
    predicted_energy,
    predicted_forces,
    reference_energy,
    reference_forces,
    movable_indices: list[int],
    force_weight: float,
    predicted_anchor_energy=None,
    reference_anchor_energy: float | None = None,
    energy_weight: float = 0.0,
):
    """Return total, force, and relative-energy MSE losses."""

    import torch

    force_error = predicted_forces[movable_indices] - reference_forces[movable_indices]
    force_loss = torch.mean(torch.square(force_error))
    energy_loss = torch.zeros((), dtype=force_loss.dtype, device=force_loss.device)
    if predicted_anchor_energy is not None:
        if reference_anchor_energy is None:
            raise ValueError("relative-energy loss lacks a reference anchor")
        delta_error = (predicted_energy - predicted_anchor_energy) - (
            reference_energy - reference_anchor_energy
        )
        energy_loss = torch.square(delta_error)
    total = float(force_weight) * force_loss + float(energy_weight) * energy_loss
    return total, force_loss, energy_loss


def _force_metrics(records: Iterable[dict[str, Any]]) -> dict[str, float | int]:
    components: list[float] = []
    vectors: list[float] = []
    count = 0
    for record in records:
        predicted = np.asarray(record["predicted_forces_eV_per_A"], dtype=float)
        reference = np.asarray(record["reference_forces_eV_per_A"], dtype=float)
        fixed = set(int(value) for value in record["fixed_atom_indices_zero_based"])
        movable = [index for index in range(len(predicted)) if index not in fixed]
        error = predicted[movable] - reference[movable]
        components.extend(error.reshape(-1).tolist())
        vectors.extend(np.linalg.norm(error, axis=1).tolist())
        count += len(movable)
    component_array = np.asarray(components, dtype=float)
    vector_array = np.asarray(vectors, dtype=float)
    return {
        "movable_atom_count": count,
        "component_rmse_eV_per_A": float(np.sqrt(np.mean(component_array**2))),
        "vector_rmse_eV_per_A": float(np.sqrt(np.mean(vector_array**2))),
        "vector_p95_eV_per_A": float(np.percentile(vector_array, 95)),
        "vector_max_eV_per_A": float(np.max(vector_array)),
    }


def _relative_energy_metrics(records: Iterable[dict[str, Any]]) -> dict[str, float | int]:
    rows = list(records)
    predicted = np.asarray([row["predicted_energy_eV"] for row in rows], dtype=float)
    reference = np.asarray([row["reference_energy_eV"] for row in rows], dtype=float)
    predicted -= np.min(predicted)
    reference -= np.min(reference)
    error = predicted - reference
    return {
        "sample_count": len(rows),
        "relative_energy_mae_eV": float(np.mean(np.abs(error))),
        "relative_energy_rmse_eV": float(np.sqrt(np.mean(error**2))),
        "lowest_energy_match": int(np.argmin(predicted) == np.argmin(reference)),
    }


def retention_non_regression(
    baseline: dict[str, float | int],
    candidate: dict[str, float | int],
    *,
    absolute_tolerance_eV_per_A: float = 0.0,
) -> tuple[bool, dict[str, bool]]:
    """Check each declared adsorption-retention force metric independently."""

    if absolute_tolerance_eV_per_A < 0.0:
        raise ValueError("adsorption-retention tolerance cannot be negative")
    checks = {
        key: float(candidate[key])
        <= float(baseline[key]) + float(absolute_tolerance_eV_per_A)
        for key in RETENTION_METRIC_KEYS
    }
    return all(checks.values()), checks


def retention_gate_verdict(
    baseline: dict[str, float | int],
    candidate: dict[str, float | int],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Classify adsorption retention as pass, soft warning, or failure."""

    if policy["kind"] != "adsorption_retention_tiered_early_stopping":
        passed, checks = retention_non_regression(
            baseline,
            candidate,
            absolute_tolerance_eV_per_A=float(
                policy.get("absolute_tolerance_eV_per_A", 0.0)
            ),
        )
        return {
            "status": "pass" if passed else "fail",
            "candidate_eligible": passed,
            "metric_checks": checks,
            "vector_max_absolute_regression_eV_per_A": float(
                candidate["vector_max_eV_per_A"]
            )
            - float(baseline["vector_max_eV_per_A"]),
        }

    core_tolerance = float(policy["hard_metric_absolute_tolerance_eV_per_A"])
    core_checks = {
        key: float(candidate[key]) <= float(baseline[key]) + core_tolerance
        for key in CORE_RETENTION_METRIC_KEYS
    }
    baseline_max = float(baseline["vector_max_eV_per_A"])
    candidate_max = float(candidate["vector_max_eV_per_A"])
    absolute_regression = candidate_max - baseline_max
    relative_regression = absolute_regression / baseline_max
    pass_limit = float(policy["vector_max_pass_absolute_tolerance_eV_per_A"])
    warning_absolute = float(
        policy["vector_max_soft_warning_maximum_absolute_regression_eV_per_A"]
    )
    warning_relative = float(
        policy["vector_max_soft_warning_maximum_relative_regression_fraction"]
    )
    if not all(core_checks.values()):
        status = "fail"
    elif absolute_regression <= pass_limit:
        status = "pass"
    elif (
        absolute_regression <= warning_absolute
        and relative_regression <= warning_relative
    ):
        status = "soft_warning"
    else:
        status = "fail"
    return {
        "status": status,
        "candidate_eligible": status in {"pass", "soft_warning"},
        "metric_checks": {
            **core_checks,
            "vector_max_eV_per_A": status in {"pass", "soft_warning"},
        },
        "vector_max_absolute_regression_eV_per_A": absolute_regression,
        "vector_max_relative_regression_fraction": relative_regression,
    }


def _checkpoint_selection_policy(review: dict[str, Any]) -> dict[str, Any]:
    policy = review.get("checkpoint_selection_policy")
    if policy is None:
        return {"kind": "final_epoch"}
    if not isinstance(policy, dict):
        raise ValueError("checkpoint selection policy must be an object")
    kind = policy.get("kind")
    supported = {
        "adsorption_retention_strict_early_stopping",
        "adsorption_retention_tiered_early_stopping",
    }
    if kind not in supported:
        raise ValueError("unsupported checkpoint selection policy")
    if policy.get("selection_dataset_role") != "adsorption_retention_validation":
        raise ValueError("retention early stopping must use adsorption validation")
    if policy.get("frozen_ts_heldout_usage") != "final_evaluation_only":
        raise ValueError("frozen TS held-out must be final-evaluation only")
    if kind == "adsorption_retention_strict_early_stopping" and tuple(
        policy.get("required_non_regression_metrics", [])
    ) != RETENTION_METRIC_KEYS:
        raise ValueError("retention metric declaration mismatch")
    tolerance_default = (
        0.0 if kind == "adsorption_retention_tiered_early_stopping" else -1.0
    )
    tolerance = float(policy.get("absolute_tolerance_eV_per_A", tolerance_default))
    if tolerance < 0.0:
        raise ValueError("retention tolerance must be non-negative")
    patience = int(policy.get("patience_epochs", 0))
    if patience < 1:
        raise ValueError("early-stopping patience must be positive")
    min_delta = float(policy.get("training_objective_min_delta", -1.0))
    if min_delta < 0.0:
        raise ValueError("training objective min delta must be non-negative")
    normalized = {
        "kind": kind,
        "selection_dataset_role": "adsorption_retention_validation",
        "absolute_tolerance_eV_per_A": tolerance,
        "patience_epochs": patience,
        "training_objective_min_delta": min_delta,
        "frozen_ts_heldout_usage": "final_evaluation_only",
        "save_every_epoch": True,
        "epoch_zero_is_candidate": False,
    }
    if kind == "adsorption_retention_strict_early_stopping":
        normalized["required_non_regression_metrics"] = list(RETENTION_METRIC_KEYS)
        return normalized
    if tuple(policy.get("hard_non_regression_metrics", [])) != CORE_RETENTION_METRIC_KEYS:
        raise ValueError("tiered retention hard-metric declaration mismatch")
    tiered_values = {
        "hard_metric_absolute_tolerance_eV_per_A": float(
            policy.get("hard_metric_absolute_tolerance_eV_per_A", -1.0)
        ),
        "vector_max_pass_absolute_tolerance_eV_per_A": float(
            policy.get("vector_max_pass_absolute_tolerance_eV_per_A", -1.0)
        ),
        "vector_max_soft_warning_maximum_absolute_regression_eV_per_A": float(
            policy.get(
                "vector_max_soft_warning_maximum_absolute_regression_eV_per_A", -1.0
            )
        ),
        "vector_max_soft_warning_maximum_relative_regression_fraction": float(
            policy.get(
                "vector_max_soft_warning_maximum_relative_regression_fraction", -1.0
            )
        ),
    }
    if any(value < 0.0 for value in tiered_values.values()):
        raise ValueError("tiered retention tolerances must be non-negative")
    normalized["hard_non_regression_metrics"] = list(CORE_RETENTION_METRIC_KEYS)
    normalized.update(tiered_values)
    return normalized


def update_checkpoint_selection(
    *,
    policy: dict[str, Any],
    epoch: int,
    checkpoint_path: Path,
    training_objective: float,
    retention_pass: bool,
    selected_epoch: int | None,
    selected_checkpoint_path: Path | None,
    selected_training_objective: float,
    epochs_without_eligible_improvement: int,
) -> tuple[int | None, Path | None, float, int, bool]:
    """Update retention-aware checkpoint selection without TS held-out input."""

    if policy["kind"] == "final_epoch":
        return epoch, checkpoint_path, training_objective, 0, False
    improved = retention_pass and (
        training_objective
        < selected_training_objective
        - float(policy["training_objective_min_delta"])
    )
    if improved:
        return epoch, checkpoint_path, training_objective, 0, False
    if selected_epoch is not None:
        epochs_without_eligible_improvement += 1
    should_stop = (
        selected_epoch is not None
        and epochs_without_eligible_improvement >= int(policy["patience_epochs"])
    )
    return (
        selected_epoch,
        selected_checkpoint_path,
        selected_training_objective,
        epochs_without_eligible_improvement,
        should_stop,
    )


def _self_test(output: Path) -> dict[str, Any]:
    import torch

    torch.manual_seed(7)
    energy_scale = torch.nn.Parameter(torch.tensor(0.7))
    force_scale = torch.nn.Parameter(torch.tensor(0.4))
    optimizer = torch.optim.SGD([energy_scale, force_scale], lr=0.05)
    reference_forces = torch.tensor(
        [[0.0, 0.0, 0.0], [0.2, -0.1, 0.3], [-0.2, 0.4, 0.1]],
        dtype=torch.float64,
    )
    base_forces = torch.tensor(
        [[0.0, 0.0, 0.0], [0.1, -0.2, 0.2], [-0.3, 0.2, 0.2]],
        dtype=torch.float64,
    )
    history: list[float] = []
    energy_gradient_seen = False
    force_gradient_seen = False
    for _ in range(12):
        optimizer.zero_grad(set_to_none=True)
        predicted_forces = force_scale.double() * base_forces
        predicted_energy = energy_scale.double() * torch.tensor(2.0)
        predicted_anchor = energy_scale.double() * torch.tensor(0.5)
        total, _, _ = combined_loss(
            predicted_energy=predicted_energy,
            predicted_forces=predicted_forces,
            reference_energy=torch.tensor(1.8),
            reference_forces=reference_forces,
            movable_indices=[1, 2],
            force_weight=1.0,
            predicted_anchor_energy=predicted_anchor,
            reference_anchor_energy=0.2,
            energy_weight=1.0,
        )
        total.backward()
        energy_gradient_seen |= energy_scale.grad is not None and bool(
            torch.isfinite(energy_scale.grad)
        )
        force_gradient_seen |= force_scale.grad is not None and bool(
            torch.isfinite(force_scale.grad)
        )
        optimizer.step()
        history.append(float(total.detach()))
    if not history[-1] < history[0]:
        raise RuntimeError("combined energy-force smoke loss did not decrease")

    identical_records = [
        {
            "predicted_energy_eV": 0.0,
            "reference_energy_eV": 0.0,
            "predicted_forces_eV_per_A": reference_forces.numpy().tolist(),
            "reference_forces_eV_per_A": reference_forces.numpy().tolist(),
            "fixed_atom_indices_zero_based": [0],
        },
        {
            "predicted_energy_eV": 0.5,
            "reference_energy_eV": 0.5,
            "predicted_forces_eV_per_A": reference_forces.numpy().tolist(),
            "reference_forces_eV_per_A": reference_forces.numpy().tolist(),
            "fixed_atom_indices_zero_based": [0],
        },
    ]
    force_metrics = _force_metrics(identical_records)
    energy_metrics = _relative_energy_metrics(identical_records)
    checkpoint_path = output / "toy_checkpoint.pt"
    output.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"energy_scale": energy_scale.detach(), "force_scale": force_scale.detach()},
        checkpoint_path,
    )
    checkpoint_sha = sha256_file(checkpoint_path)
    if len(checkpoint_sha) != 64:
        raise RuntimeError("toy checkpoint hash was not produced")
    result = {
        "schema_version": 1,
        "document_kind": "matris_energy_force_executor_local_self_test",
        "status": "passed",
        "scope": "toy_torch_loss_and_metrics_only_no_MatRIS_model_loaded",
        "checks": {
            "combined_loss_finite": all(math.isfinite(value) for value in history),
            "combined_loss_decreased": history[-1] < history[0],
            "energy_gradient_seen": energy_gradient_seen,
            "force_gradient_seen": force_gradient_seen,
            "force_tail_metrics_computed": force_metrics["vector_max_eV_per_A"] == 0.0,
            "relative_energy_metrics_computed": energy_metrics["relative_energy_rmse_eV"] == 0.0,
            "checkpoint_hash_generated": True,
        },
        "loss": {"initial": history[0], "final": history[-1]},
        "force_metrics": force_metrics,
        "relative_energy_metrics": energy_metrics,
        "toy_checkpoint": {"path": str(checkpoint_path), "sha256": checkpoint_sha},
        "scientific_limits": {
            "not_a_MatRIS_checkpoint": True,
            "not_a_GPU_finetune": True,
            "does_not_validate_MatRIS_runtime_integration": True,
        },
    }
    write_json_atomic(output / "self_test_result.json", result, ensure_ascii=True)
    return result


def _prediction_record(model, sample: dict[str, Any], device: str) -> dict[str, Any]:
    import torch
    from ase.io import read

    atoms = read(sample["structure_path"])
    model.eval()
    with torch.enable_grad():
        energy, forces = predict_one(model, atoms, device, training=False)
    return {
        "sample_id": sample["sample_id"],
        "predicted_energy_eV": float(energy.detach().cpu()),
        "reference_energy_eV": float(sample["reference_energy_eV"]),
        "predicted_forces_eV_per_A": forces.detach().cpu().numpy().tolist(),
        "reference_forces_eV_per_A": sample["reference_forces_eV_per_A"],
        "fixed_atom_indices_zero_based": sample["fixed_atom_indices_zero_based"],
    }


def _validate_authorization(
    authorization_path: Path, review_path: Path, review_sha: str
) -> dict[str, Any]:
    authorization = load_json_object(authorization_path.resolve())
    if authorization.get("document_kind") != AUTHORIZATION_KIND:
        raise ValueError("invalid MatRIS execution authorization")
    if authorization.get("execution_authorized") is not True:
        raise ValueError("MatRIS execution is not authorized")
    request = authorization.get("review_request", {})
    if (
        Path(str(request.get("path", ""))).resolve() != review_path.resolve()
        or request.get("sha256") != review_sha
    ):
        raise ValueError("authorization is not bound to this review request")
    return authorization


def _train(args: argparse.Namespace, context: dict[str, Any]) -> dict[str, Any]:
    import torch
    from ase.io import read

    review_path = context["review_path"]
    review_sha = sha256_file(review_path)
    authorization = _validate_authorization(args.authorization, review_path, review_sha)
    checkpoint = args.checkpoint.resolve()
    if (
        not checkpoint.is_file()
        or sha256_file(checkpoint) != context["review"]["base_checkpoint_sha256"]
    ):
        raise ValueError("base MatRIS checkpoint binding failed")
    if authorization.get("base_checkpoint_sha256") != sha256_file(checkpoint):
        raise ValueError("authorization checkpoint binding failed")
    if args.epochs < 1 or args.epochs > 50:
        raise ValueError("epochs must be between 1 and 50")
    if args.force_weight <= 0.0 or args.energy_weight <= 0.0:
        raise ValueError("energy and force weights must both be positive")
    selection_policy = _checkpoint_selection_policy(context["review"])

    training = context["training_samples"]
    by_id = {sample["sample_id"]: sample for sample in training}
    anchors = energy_anchor_ids(training)
    model, original_config, _ = load_model(checkpoint, args.device)
    parameters = configure_trainable_parameters(model, args.trainable_scope)
    optimizer = torch.optim.AdamW(
        parameters, lr=args.learning_rate, weight_decay=args.weight_decay
    )
    seed = int(args.seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    primary_heldout = [
        sample
        for sample in context["heldout_validation_samples"]
        if sample.get("primary_metric_eligible") is True
    ]
    diagnostic_heldout = [
        sample
        for sample in context["heldout_validation_samples"]
        if sample.get("primary_metric_eligible") is not True
    ]
    before_adsorption = [
        _prediction_record(model, sample, args.device)
        for sample in context["adsorption_validation_samples"]
    ]
    baseline_adsorption_metrics = _force_metrics(before_adsorption)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    epoch_output = output / "epoch_checkpoints"
    history: list[dict[str, Any]] = []
    selected_epoch: int | None = None
    selected_training_objective = math.inf
    selected_checkpoint_path: Path | None = None
    epochs_without_eligible_improvement = 0
    stopped_early = False
    for epoch in range(1, args.epochs + 1):
        order = list(by_id)
        random.Random(seed + epoch).shuffle(order)
        total_sum = force_sum = energy_sum = 0.0
        energy_terms = 0
        model.train()
        for sample_id in order:
            sample = by_id[sample_id]
            atoms = read(sample["structure_path"])
            optimizer.zero_grad(set_to_none=True)
            predicted_energy, predicted_forces = predict_one(
                model, atoms, args.device, training=True
            )
            reference_forces = torch.as_tensor(
                sample["reference_forces_eV_per_A"],
                dtype=predicted_forces.dtype,
                device=predicted_forces.device,
            )
            fixed = set(int(value) for value in sample["fixed_atom_indices_zero_based"])
            movable = [index for index in range(len(atoms)) if index not in fixed]
            predicted_anchor = None
            reference_anchor = None
            group = sample.get("energy_group_id")
            if group is not None and anchors[str(group)] != sample_id:
                anchor = by_id[anchors[str(group)]]
                anchor_atoms = read(anchor["structure_path"])
                predicted_anchor, _ = predict_one(
                    model, anchor_atoms, args.device, training=True
                )
                reference_anchor = float(anchor["reference_energy_eV"])
                energy_terms += 1
            total, force_loss, energy_loss = combined_loss(
                predicted_energy=predicted_energy,
                predicted_forces=predicted_forces,
                reference_energy=float(sample["reference_energy_eV"]),
                reference_forces=reference_forces,
                movable_indices=movable,
                force_weight=args.force_weight,
                predicted_anchor_energy=predicted_anchor,
                reference_anchor_energy=reference_anchor,
                energy_weight=args.energy_weight,
            )
            if not torch.isfinite(total):
                raise RuntimeError(f"non-finite training loss: {sample_id}")
            total.backward()
            gradient_norm = torch.nn.utils.clip_grad_norm_(
                parameters, args.gradient_clip_norm
            )
            if not torch.isfinite(gradient_norm):
                raise RuntimeError(f"non-finite gradient: {sample_id}")
            optimizer.step()
            total_sum += float(total.detach().cpu())
            force_sum += float(force_loss.detach().cpu())
            energy_sum += float(energy_loss.detach().cpu())
        mean_total_loss = total_sum / len(order)
        epoch_checkpoint = epoch_output / f"epoch_{epoch:03d}.pth.tar"
        epoch_checkpoint_sha = save_checkpoint(model, original_config, epoch_checkpoint)
        epoch_adsorption = [
            _prediction_record(model, sample, args.device)
            for sample in context["adsorption_validation_samples"]
        ]
        epoch_adsorption_metrics = _force_metrics(epoch_adsorption)
        retention_gate = retention_gate_verdict(
            baseline_adsorption_metrics,
            epoch_adsorption_metrics,
            selection_policy,
        )
        retention_candidate_eligible = bool(retention_gate["candidate_eligible"])
        history.append(
            {
                "epoch": epoch,
                "mean_total_loss": mean_total_loss,
                "mean_force_mse": force_sum / len(order),
                "mean_relative_energy_mse": energy_sum / max(energy_terms, 1),
                "checkpoint": {
                    "path": str(epoch_checkpoint),
                    "sha256": epoch_checkpoint_sha,
                },
                "adsorption_retention_force": epoch_adsorption_metrics,
                "adsorption_retention_gate_status": retention_gate["status"],
                "adsorption_retention_candidate_eligible": (
                    retention_candidate_eligible
                ),
                "adsorption_retention_non_regression": (
                    retention_gate["status"] == "pass"
                ),
                "adsorption_retention_metric_checks": retention_gate[
                    "metric_checks"
                ],
                "adsorption_retention_gate_details": retention_gate,
            }
        )

        (
            selected_epoch,
            selected_checkpoint_path,
            selected_training_objective,
            epochs_without_eligible_improvement,
            should_stop,
        ) = update_checkpoint_selection(
            policy=selection_policy,
            epoch=epoch,
            checkpoint_path=epoch_checkpoint,
            training_objective=mean_total_loss,
            retention_pass=retention_candidate_eligible,
            selected_epoch=selected_epoch,
            selected_checkpoint_path=selected_checkpoint_path,
            selected_training_objective=selected_training_objective,
            epochs_without_eligible_improvement=epochs_without_eligible_improvement,
        )
        if should_stop:
            stopped_early = True
            break

    if selected_checkpoint_path is None:
        result = {
            "schema_version": 2,
            "document_kind": "matris_energy_force_finetune_result",
            "status": "completed_no_retention_eligible_checkpoint_candidate",
            "review_request": {"path": str(review_path), "sha256": review_sha},
            "authorization": {
                "path": str(args.authorization.resolve()),
                "sha256": sha256_file(args.authorization.resolve()),
            },
            "base_checkpoint_sha256": sha256_file(checkpoint),
            "checkpoint_selection_policy": selection_policy,
            "training": {
                "requested_epochs": args.epochs,
                "completed_epochs": len(history),
                "stopped_early": stopped_early,
                "history": history,
            },
            "adsorption_retention": {
                "baseline_force": baseline_adsorption_metrics,
                "eligible_epoch_count": 0,
            },
            "frozen_ts_heldout": {
                "evaluated": False,
                "reason": "no checkpoint passed adsorption-retention selection",
            },
            "promotion_authorized": False,
            "complete_path_rerun_authorized": False,
        }
        write_json_atomic(output / "result.json", result, ensure_ascii=True)
        return result

    del optimizer, parameters, model
    if args.device.startswith("cuda"):
        torch.cuda.empty_cache()
    before_model, _, _ = load_model(checkpoint, args.device)
    before_heldout = [
        _prediction_record(before_model, sample, args.device)
        for sample in primary_heldout
    ]
    before_diagnostic = [
        _prediction_record(before_model, sample, args.device)
        for sample in diagnostic_heldout
    ]
    del before_model
    if args.device.startswith("cuda"):
        torch.cuda.empty_cache()
    selected_model, _, _ = load_model(selected_checkpoint_path, args.device)
    after_heldout = [
        _prediction_record(selected_model, sample, args.device)
        for sample in primary_heldout
    ]
    after_diagnostic = [
        _prediction_record(selected_model, sample, args.device)
        for sample in diagnostic_heldout
    ]
    after_adsorption = [
        _prediction_record(selected_model, sample, args.device)
        for sample in context["adsorption_validation_samples"]
    ]
    checkpoint_output = output / "checkpoint_candidate.pth.tar"
    shutil.copy2(selected_checkpoint_path, checkpoint_output)
    candidate_sha = sha256_file(checkpoint_output)
    selected_adsorption_metrics = _force_metrics(after_adsorption)
    selected_retention_gate = retention_gate_verdict(
        baseline_adsorption_metrics,
        selected_adsorption_metrics,
        selection_policy,
    )
    result = {
        "schema_version": 2,
        "document_kind": "matris_energy_force_finetune_result",
        "status": "completed_needs_work_review_not_promoted",
        "review_request": {"path": str(review_path), "sha256": review_sha},
        "authorization": {
            "path": str(args.authorization.resolve()),
            "sha256": sha256_file(args.authorization.resolve()),
        },
        "base_checkpoint_sha256": sha256_file(checkpoint),
        "checkpoint_candidate": {
            "path": str(checkpoint_output),
            "sha256": candidate_sha,
            "selected_epoch": selected_epoch,
            "selected_epoch_checkpoint": {
                "path": str(selected_checkpoint_path),
                "sha256": sha256_file(selected_checkpoint_path),
            },
        },
        "checkpoint_selection_policy": selection_policy,
        "training": {
            "requested_epochs": args.epochs,
            "completed_epochs": len(history),
            "stopped_early": stopped_early,
            "force_weight": args.force_weight,
            "energy_weight": args.energy_weight,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "trainable_scope": args.trainable_scope,
            "history": history,
        },
        "frozen_ts_heldout": {
            "primary_metric_sample_count": len(primary_heldout),
            "diagnostic_only_sample_count": len(diagnostic_heldout),
            "before_force": _force_metrics(before_heldout),
            "after_force": _force_metrics(after_heldout),
            "before_relative_energy": _relative_energy_metrics(before_heldout),
            "after_relative_energy": _relative_energy_metrics(after_heldout),
            "diagnostic_before_force": _force_metrics(before_diagnostic),
            "diagnostic_after_force": _force_metrics(after_diagnostic),
        },
        "adsorption_retention": {
            "before_force": baseline_adsorption_metrics,
            "after_force": selected_adsorption_metrics,
            "selected_epoch_gate_status": selected_retention_gate["status"],
            "selected_epoch_candidate_eligible": selected_retention_gate[
                "candidate_eligible"
            ],
            "selected_epoch_non_regression": (
                selected_retention_gate["status"] == "pass"
            ),
            "selected_epoch_metric_checks": selected_retention_gate[
                "metric_checks"
            ],
            "eligible_epoch_count": sum(
                bool(row["adsorption_retention_candidate_eligible"])
                for row in history
            ),
        },
        "promotion_authorized": False,
        "complete_path_rerun_authorized": False,
    }
    write_json_atomic(output / "result.json", result, ensure_ascii=True)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "self-test"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--review-request", type=Path, required=True)
        sub.add_argument("--output", type=Path, required=True)
    train = subparsers.add_parser("train")
    train.add_argument("--review-request", type=Path, required=True)
    train.add_argument("--authorization", type=Path, required=True)
    train.add_argument("--checkpoint", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--device", default="cuda")
    train.add_argument("--epochs", type=int, required=True)
    train.add_argument("--force-weight", type=float, required=True)
    train.add_argument("--energy-weight", type=float, required=True)
    train.add_argument("--learning-rate", type=float, required=True)
    train.add_argument("--weight-decay", type=float, default=0.0)
    train.add_argument("--gradient-clip-norm", type=float, default=10.0)
    train.add_argument(
        "--trainable-scope",
        choices=("energy_head", "last_interaction_and_energy_head"),
        required=True,
    )
    train.add_argument("--seed", type=int, default=20260902)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    context = validate_review_package(args.review_request)
    if args.command == "preflight":
        result = {
            "schema_version": 1,
            "document_kind": "matris_energy_force_executor_preflight",
            "status": "passed",
            "review_request": {
                "path": str(context["review_path"]),
                "sha256": sha256_file(context["review_path"]),
            },
            "validation_summary": context["validation_summary"],
            "execution_performed": False,
        }
        write_json_atomic(args.output, result, ensure_ascii=True)
    elif args.command == "self-test":
        result = _self_test(args.output)
        result["review_request_sha256"] = sha256_file(context["review_path"])
        result["production_manifest_preflight"] = context["validation_summary"]
        write_json_atomic(args.output / "self_test_result.json", result, ensure_ascii=True)
    else:
        result = _train(args, context)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
