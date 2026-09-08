#!/usr/bin/env python3
"""Run reaction-group-held-out MatRIS fine-tuning and an end-to-end GPU timing test."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from scripts.matris_training_exclusions import (
    assert_training_samples_disjoint,
    load_heldout_exclusions,
)
from scripts.artifact_io import sha256_file as sha256_file




def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def load_experiment(path: Path) -> dict[str, Any]:
    experiment = load_json(path)
    if experiment.get("document_kind") != "matris_finetune_speed_benchmark_experiment":
        raise ValueError("invalid experiment document kind")
    return experiment


def verify_inputs(experiment_path: Path, experiment: dict[str, Any]) -> tuple[Path, Path, dict[str, Any]]:
    manifest_path = Path(experiment["benchmark_manifest"]["path"])
    checkpoint_path = Path(experiment["base_checkpoint"]["path"])
    expected_manifest_hash = experiment["benchmark_manifest"]["sha256"]
    expected_checkpoint_hash = experiment["base_checkpoint"]["sha256"]
    if sha256_file(manifest_path) != expected_manifest_hash:
        raise ValueError("benchmark manifest hash mismatch")
    if sha256_file(checkpoint_path) != expected_checkpoint_hash:
        raise ValueError("base checkpoint hash mismatch")
    manifest = load_json(manifest_path)
    if manifest.get("document_kind") != "mlip_same_structure_benchmark_manifest":
        raise ValueError("invalid benchmark manifest")
    if manifest.get("matris_checkpoint_sha256") != expected_checkpoint_hash:
        raise ValueError("manifest is not bound to the requested MatRIS checkpoint")
    structures_root = manifest_path.parent
    seen: set[str] = set()
    for sample in manifest.get("samples", []):
        sample_id = str(sample["sample_id"])
        if sample_id in seen:
            raise ValueError(f"duplicate sample id: {sample_id}")
        seen.add(sample_id)
        structure_path = structures_root / sample["structure"]["path"]
        if sha256_file(structure_path) != sample["structure"]["sha256"]:
            raise ValueError(f"structure hash mismatch: {sample_id}")
        forces = np.asarray(sample["vasp_label"]["forces_eV_per_A"], dtype=float)
        if forces.shape != (int(sample["structure"]["atom_count"]), 3):
            raise ValueError(f"invalid force label shape: {sample_id}")
        if not np.isfinite(forces).all():
            raise ValueError(f"non-finite force label: {sample_id}")
    requested = {
        sample_id
        for fold in experiment["fine_tuning"]["folds"]
        for sample_id in fold["training_sample_ids"] + fold["held_out_sample_ids"]
    }
    missing = requested - seen
    if missing:
        raise ValueError(f"experiment references missing samples: {sorted(missing)}")
    exclusion_ref = experiment.get("heldout_exclusion_manifest")
    if not isinstance(exclusion_ref, dict):
        raise ValueError("MatRIS training requires a hash-bound held-out exclusion manifest")
    exclusion_path = Path(str(exclusion_ref.get("path", "")))
    exclusions = load_heldout_exclusions(
        exclusion_path,
        expected_sha256=str(exclusion_ref.get("sha256", "")),
    )
    training_ids = {
        sample_id
        for fold in experiment["fine_tuning"]["folds"]
        for sample_id in fold["training_sample_ids"]
    }
    assert_training_samples_disjoint(
        (sample for sample in manifest["samples"] if sample["sample_id"] in training_ids),
        structures_root=structures_root,
        exclusion_manifest=exclusions,
    )
    return manifest_path, checkpoint_path, manifest


def load_atoms(manifest_path: Path, sample: dict[str, Any]):
    from ase.io import read

    return read(manifest_path.parent / sample["structure"]["path"])


def load_model(checkpoint_path: Path, device: str):
    import torch
    from matris.model.model import MatRIS

    started = time.perf_counter()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    original_config = dict(checkpoint["config"])
    construction_config = dict(original_config)
    if construction_config.get("reference_energy") == "fecoh":
        construction_config["reference_energy"] = "demo"
    model = MatRIS(**construction_config)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.config["reference_energy"] = original_config.get("reference_energy")
    model = model.to(device)
    model.eval()
    if device.startswith("cuda"):
        torch.cuda.synchronize()
    return model, original_config, time.perf_counter() - started


def graph_for(model, atoms, device: str):
    from matris.graph import RadiusGraph
    from pymatgen.io.ase import AseAtomsAdaptor

    structure = AseAtomsAdaptor.get_structure(atoms)
    graph = model.graph_converter(structure).to(device)
    return [graph] if isinstance(graph, RadiusGraph) else graph


def predict_one(model, atoms, device: str, *, training: bool):
    graphs = graph_for(model, atoms, device)
    output = model(graphs, task="ef", is_training=training)
    forces = output["f"][0]
    energy = output["e"][0]
    if model.is_intensive:
        energy = energy * len(atoms)
    return energy, forces


def prediction_record(model, manifest_path: Path, sample: dict[str, Any], device: str) -> dict[str, Any]:
    import torch

    atoms = load_atoms(manifest_path, sample)
    model.eval()
    with torch.enable_grad():
        energy, forces = predict_one(model, atoms, device, training=False)
    predicted_forces = forces.detach().cpu().numpy()
    if predicted_forces.shape != (len(atoms), 3) or not np.isfinite(predicted_forces).all():
        raise RuntimeError(f"non-finite prediction: {sample['sample_id']}")
    return {
        "sample_id": sample["sample_id"],
        "reaction_id": sample["reaction_id"],
        "subset": sample["subset"],
        "energy_group_id": sample["energy_group_id"],
        "predicted_energy_eV": float(energy.detach().cpu()),
        "predicted_forces_eV_per_A": predicted_forces.tolist(),
        "vasp_energy_eV": float(sample["vasp_label"]["energy_eV"]),
        "vasp_forces_eV_per_A": sample["vasp_label"]["forces_eV_per_A"],
        "fixed_atom_indices_zero_based": sample["fixed_atom_indices_zero_based"],
    }


def force_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    component_errors: list[float] = []
    vector_errors: list[float] = []
    movable_atoms = 0
    for record in records:
        predicted = np.asarray(record["predicted_forces_eV_per_A"], dtype=float)
        reference = np.asarray(record["vasp_forces_eV_per_A"], dtype=float)
        fixed = set(int(value) for value in record["fixed_atom_indices_zero_based"])
        movable = [index for index in range(len(predicted)) if index not in fixed]
        errors = predicted[movable] - reference[movable]
        component_errors.extend(errors.reshape(-1).tolist())
        vector_errors.extend(np.linalg.norm(errors, axis=1).tolist())
        movable_atoms += len(movable)
    components = np.asarray(component_errors, dtype=float)
    vectors = np.asarray(vector_errors, dtype=float)
    return {
        "sample_count": len(records),
        "movable_atom_count": movable_atoms,
        "force_component_count": int(components.size),
        "component_mae_eV_per_A": float(np.mean(np.abs(components))),
        "component_rmse_eV_per_A": float(np.sqrt(np.mean(np.square(components)))),
        "vector_rmse_eV_per_A": float(np.sqrt(np.mean(np.square(vectors)))),
        "vector_p95_eV_per_A": float(np.percentile(vectors, 95)),
        "vector_max_eV_per_A": float(np.max(vectors)),
    }


def relative_energy_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    reference = np.asarray([record["vasp_energy_eV"] for record in records], dtype=float)
    predicted = np.asarray([record["predicted_energy_eV"] for record in records], dtype=float)
    reference -= np.min(reference)
    predicted -= np.min(predicted)
    errors = predicted - reference
    return {
        "sample_count": len(records),
        "relative_energy_mae_eV": float(np.mean(np.abs(errors))),
        "relative_energy_rmse_eV": float(np.sqrt(np.mean(np.square(errors)))),
        "lowest_energy_match": int(np.argmin(reference) == np.argmin(predicted)),
    }


def configure_trainable_parameters(model, scope: str):
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    if scope == "energy_head":
        modules = [model.energy_head]
    elif scope == "last_interaction_and_energy_head":
        modules = [model.interaction_block[-1], model.readout_norm, model.energy_head]
    else:
        raise ValueError(f"unsupported fine-tuning scope: {scope}")
    parameters = []
    for module in modules:
        for parameter in module.parameters():
            parameter.requires_grad_(True)
            parameters.append(parameter)
    return parameters


def train_fold(
    model,
    manifest_path: Path,
    samples_by_id: dict[str, dict[str, Any]],
    training_ids: list[str],
    device: str,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], float]:
    import torch

    parameters = configure_trainable_parameters(model, config["trainable_scope"])
    optimizer = torch.optim.AdamW(
        parameters,
        lr=float(config["learning_rate"]),
        weight_decay=float(config["weight_decay"]),
    )
    seed = int(config["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    history: list[dict[str, Any]] = []
    started = time.perf_counter()
    for epoch in range(1, int(config["epochs"]) + 1):
        order = list(training_ids)
        random.Random(seed + epoch).shuffle(order)
        squared_error_sum = 0.0
        component_count = 0
        model.train()
        for sample_id in order:
            sample = samples_by_id[sample_id]
            atoms = load_atoms(manifest_path, sample)
            optimizer.zero_grad(set_to_none=True)
            _, predicted_forces = predict_one(model, atoms, device, training=True)
            reference = torch.as_tensor(
                sample["vasp_label"]["forces_eV_per_A"],
                dtype=predicted_forces.dtype,
                device=predicted_forces.device,
            )
            fixed = set(int(value) for value in sample["fixed_atom_indices_zero_based"])
            movable = [index for index in range(len(atoms)) if index not in fixed]
            error = predicted_forces[movable] - reference[movable]
            loss = torch.mean(torch.square(error))
            if not torch.isfinite(loss):
                raise RuntimeError(f"non-finite training loss: {sample_id}")
            loss.backward()
            gradient_norm = torch.nn.utils.clip_grad_norm_(parameters, float(config["gradient_clip_norm"]))
            if not torch.isfinite(gradient_norm):
                raise RuntimeError(f"non-finite gradient: {sample_id}")
            optimizer.step()
            squared_error_sum += float(torch.sum(torch.square(error)).detach().cpu())
            component_count += int(error.numel())
        history.append(
            {
                "epoch": epoch,
                "training_component_rmse_eV_per_A": math.sqrt(squared_error_sum / component_count),
            }
        )
    if device.startswith("cuda"):
        torch.cuda.synchronize()
    return history, time.perf_counter() - started


def save_checkpoint(model, original_config: dict[str, Any], path: Path) -> str:
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    state_dict = {key: value.detach().cpu() for key, value in model.state_dict().items()}
    torch.save({"config": original_config, "state_dict": state_dict}, path)
    return sha256_file(path)


def timed_batch(model, manifest_path: Path, samples: list[dict[str, Any]], device: str) -> float:
    import torch

    if device.startswith("cuda"):
        torch.cuda.synchronize()
    started = time.perf_counter()
    for sample in samples:
        atoms = load_atoms(manifest_path, sample)
        with torch.enable_grad():
            energy, forces = predict_one(model, atoms, device, training=False)
        if not torch.isfinite(energy) or not torch.isfinite(forces).all():
            raise RuntimeError(f"non-finite timing prediction: {sample['sample_id']}")
    if device.startswith("cuda"):
        torch.cuda.synchronize()
    return time.perf_counter() - started


def run(args: argparse.Namespace) -> None:
    import torch

    experiment_path = args.experiment.resolve()
    experiment = load_experiment(experiment_path)
    manifest_path, checkpoint_path, manifest = verify_inputs(experiment_path, experiment)
    samples_by_id = {sample["sample_id"]: sample for sample in manifest["samples"]}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started_utc = utc_now()

    base_model, original_config, base_load_seconds = load_model(checkpoint_path, args.device)
    all_base_predictions = {
        sample_id: prediction_record(base_model, manifest_path, sample, args.device)
        for sample_id, sample in samples_by_id.items()
    }

    timing_config = experiment["timing"]
    timing_samples = [samples_by_id[sample_id] for sample_id in timing_config["sample_ids"]]
    cold_batch_seconds = timed_batch(base_model, manifest_path, timing_samples, args.device)
    for _ in range(int(timing_config["warmup_repeats"])):
        timed_batch(base_model, manifest_path, timing_samples, args.device)
    timing_repeats = [
        timed_batch(base_model, manifest_path, timing_samples, args.device)
        for _ in range(int(timing_config["measured_repeats"]))
    ]
    warm_median_seconds = statistics.median(timing_repeats)
    vasp_wall_seconds = float(timing_config["vasp_reference"]["wall_seconds"])
    timing_result = {
        "sample_count": len(timing_samples),
        "sample_ids": timing_config["sample_ids"],
        "model_load_seconds": base_load_seconds,
        "cold_batch_seconds": cold_batch_seconds,
        "warm_batch_seconds": timing_repeats,
        "warm_batch_median_seconds": warm_median_seconds,
        "warm_per_structure_median_seconds": warm_median_seconds / len(timing_samples),
        "vasp_reference": timing_config["vasp_reference"],
        "wall_clock_speedup_warm": vasp_wall_seconds / warm_median_seconds,
        "wall_clock_speedup_cold_including_model_load": vasp_wall_seconds
        / (base_load_seconds + cold_batch_seconds),
        "comparison_scope": "same eight fixed structures; queue time excluded; MatRIS includes structure read, graph construction, energy, and force inference",
    }

    fine_config = experiment["fine_tuning"]
    fold_results: list[dict[str, Any]] = []
    aggregated_base: list[dict[str, Any]] = []
    aggregated_tuned: list[dict[str, Any]] = []
    for fold in fine_config["folds"]:
        fold_name = fold["name"]
        model, fold_original_config, _ = load_model(checkpoint_path, args.device)
        history, training_seconds = train_fold(
            model,
            manifest_path,
            samples_by_id,
            fold["training_sample_ids"],
            args.device,
            fine_config,
        )
        held_out_base = [all_base_predictions[sample_id] for sample_id in fold["held_out_sample_ids"]]
        held_out_tuned = [
            prediction_record(model, manifest_path, samples_by_id[sample_id], args.device)
            for sample_id in fold["held_out_sample_ids"]
        ]
        retention_base = [
            all_base_predictions[sample_id] for sample_id in fine_config["retention_sample_ids"]
        ]
        retention_tuned = [
            prediction_record(model, manifest_path, samples_by_id[sample_id], args.device)
            for sample_id in fine_config["retention_sample_ids"]
        ]
        checkpoint_output = output / "checkpoints" / f"{fold_name}.pth.tar"
        checkpoint_hash = save_checkpoint(model, fold_original_config, checkpoint_output)
        base_force = force_metrics(held_out_base)
        tuned_force = force_metrics(held_out_tuned)
        fold_results.append(
            {
                "name": fold_name,
                "held_out_reaction_id": fold["held_out_reaction_id"],
                "training_sample_count": len(fold["training_sample_ids"]),
                "held_out_sample_count": len(fold["held_out_sample_ids"]),
                "training_seconds": training_seconds,
                "training_history": history,
                "base_force_metrics": base_force,
                "tuned_force_metrics": tuned_force,
                "vector_rmse_change_fraction": (
                    tuned_force["vector_rmse_eV_per_A"] / base_force["vector_rmse_eV_per_A"] - 1.0
                ),
                "base_relative_energy_metrics": relative_energy_metrics(held_out_base),
                "tuned_relative_energy_metrics": relative_energy_metrics(held_out_tuned),
                "base_retention_force_metrics": force_metrics(retention_base),
                "tuned_retention_force_metrics": force_metrics(retention_tuned),
                "checkpoint": {
                    "path": checkpoint_output.relative_to(output).as_posix(),
                    "sha256": checkpoint_hash,
                },
            }
        )
        aggregated_base.extend(held_out_base)
        aggregated_tuned.extend(held_out_tuned)
        del model
        torch.cuda.empty_cache() if args.device.startswith("cuda") else None

    aggregate_base_metrics = force_metrics(aggregated_base)
    aggregate_tuned_metrics = force_metrics(aggregated_tuned)
    improved_fold_count = sum(
        fold["tuned_force_metrics"]["vector_rmse_eV_per_A"]
        < fold["base_force_metrics"]["vector_rmse_eV_per_A"]
        for fold in fold_results
    )
    fine_tuning_result = {
        "protocol": {
            "split": "three-fold leave-one-complete-reaction-out",
            "training_target": "movable-atom VASP forces only",
            "trainable_scope": fine_config["trainable_scope"],
            "epochs": fine_config["epochs"],
            "learning_rate": fine_config["learning_rate"],
            "weight_decay": fine_config["weight_decay"],
            "seed": fine_config["seed"],
        },
        "folds": fold_results,
        "aggregate_base_force_metrics": aggregate_base_metrics,
        "aggregate_tuned_force_metrics": aggregate_tuned_metrics,
        "aggregate_vector_rmse_change_fraction": (
            aggregate_tuned_metrics["vector_rmse_eV_per_A"]
            / aggregate_base_metrics["vector_rmse_eV_per_A"]
            - 1.0
        ),
        "improved_fold_count": improved_fold_count,
        "fold_count": len(fold_results),
        "evidence_supports_cross_reaction_improvement": bool(
            aggregate_tuned_metrics["vector_rmse_eV_per_A"]
            < aggregate_base_metrics["vector_rmse_eV_per_A"]
            and aggregate_tuned_metrics["vector_p95_eV_per_A"]
            <= aggregate_base_metrics["vector_p95_eV_per_A"]
            and improved_fold_count >= 2
        ),
    }

    result = {
        "schema_version": 1,
        "document_kind": "matris_finetune_speed_benchmark_result",
        "status": "success",
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "experiment_path": str(experiment_path),
        "experiment_sha256": sha256_file(experiment_path),
        "benchmark_manifest_sha256": sha256_file(manifest_path),
        "base_checkpoint_sha256": sha256_file(checkpoint_path),
        "heldout_exclusion_manifest_sha256": experiment[
            "heldout_exclusion_manifest"
        ]["sha256"],
        "device": {
            "requested": args.device,
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        "fine_tuning": fine_tuning_result,
        "timing": timing_result,
        "scientific_limits": {
            "predictions_are_not_vasp": True,
            "fine_tuning_is_small_data_and_reaction_group_held_out": True,
            "timing_speedup_does_not_establish_accuracy_outside_the_test_domain": True,
            "vasp_wall_time_and_gpu_wall_time_exclude_queue_wait": True,
            "fine_tuned_checkpoints_require_separate_review_before_scientific_use": True,
        },
    }
    write_json_atomic(output / "result.json", result)
    print(
        json.dumps(
            {
                "status": "success",
                "aggregate_base_vector_rmse_eV_per_A": aggregate_base_metrics[
                    "vector_rmse_eV_per_A"
                ],
                "aggregate_tuned_vector_rmse_eV_per_A": aggregate_tuned_metrics[
                    "vector_rmse_eV_per_A"
                ],
                "improved_fold_count": improved_fold_count,
                "wall_clock_speedup_warm": timing_result["wall_clock_speedup_warm"],
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
