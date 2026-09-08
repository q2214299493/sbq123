#!/usr/bin/env python3
"""Offline leave-one-reaction-out feasibility test for MatRIS/AQCat25 fusion.

The script consumes only existing, hash-bound VASP labels and existing MLIP
predictions.  It never runs either MLIP, submits a calculation, modifies a
checkpoint, or promotes a model.  The conservative meta-model is deliberately
low capacity: MatRIS is the anchor, AQCat25 contributes through one bounded
global mixing coefficient, and a pair-RBF energy correction supplies a
structure-dependent residual.  Forces are analytic derivatives of that same
energy expression.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import os
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from ase import Atoms
from ase.geometry import find_mic
from ase.io import read
from scipy.optimize import lsq_linear

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic


MODEL_ORDER = ("matris", "aqcat25", "linear_fusion", "conservative_meta")
MODEL_LABELS = {
    "matris": "MatRIS",
    "aqcat25": "AQCat25",
    "linear_fusion": "Linear fusion",
    "conservative_meta": "Conservative meta",
}


@dataclass(frozen=True)
class FusionSample:
    sample_id: str
    reaction_id: str
    energy_group_id: str
    composition_key: str
    energy_class: str
    structure_sha256: str
    atoms: Atoms
    fixed_indices: tuple[int, ...]
    movable_indices: tuple[int, ...]
    vasp_energy: float
    vasp_forces: np.ndarray
    matris_energy: float
    matris_forces: np.ndarray
    aqcat25_energy: float
    aqcat25_forces: np.ndarray


@dataclass(frozen=True)
class Prediction:
    energy: float
    forces: np.ndarray


@dataclass(frozen=True)
class MetaParameters:
    cutoff_A: float
    radial_basis_count: int
    ridge_alpha: float


class PairFeatureCache:
    def __init__(self, pair_types: tuple[tuple[str, str], ...], center_min_A: float) -> None:
        self.pair_types = pair_types
        self.center_min_A = float(center_min_A)
        self._cache: dict[tuple[str, float, int], tuple[np.ndarray, np.ndarray]] = {}

    def get(
        self, sample: FusionSample, cutoff_A: float, radial_basis_count: int
    ) -> tuple[np.ndarray, np.ndarray]:
        key = (sample.structure_sha256, float(cutoff_A), int(radial_basis_count))
        if key not in self._cache:
            self._cache[key] = pair_rbf_energy_force_features(
                sample.atoms,
                sample.fixed_indices,
                self.pair_types,
                cutoff_A=float(cutoff_A),
                radial_basis_count=int(radial_basis_count),
                center_min_A=self.center_min_A,
            )
        energy, forces = self._cache[key]
        return energy.copy(), forces.copy()


def _finite_array(value: Any, shape: tuple[int, ...], label: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{label} must have finite shape {shape}, got {array.shape}")
    return array


def _load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fusion feasibility config must be a mapping")
    if payload.get("workflow_kind") != "offline_matris_aqcat25_fusion_feasibility":
        raise ValueError("unexpected fusion feasibility workflow kind")
    if payload.get("scientific_boundaries", {}).get("offline_only") is not True:
        raise ValueError("offline_only boundary must remain true")
    return payload


def _resolve_source(root: Path, configured: str) -> Path:
    path = Path(configured)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _result_map(payload: dict[str, Any], backend: str) -> dict[str, dict[str, Any]]:
    rows = payload.get("samples")
    if not isinstance(rows, list):
        raise ValueError(f"{backend} result samples must be a list")
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        if not sample_id or sample_id in mapped:
            raise ValueError(f"invalid or duplicate {backend} sample id: {sample_id}")
        mapped[sample_id] = row
    return mapped


def load_samples(  # noqa: C901 - explicit audit gates
    manifest_path: Path,
    matris_path: Path,
    aqcat25_path: Path,
    config: dict[str, Any],
) -> tuple[list[FusionSample], dict[str, Any]]:
    manifest = load_json_object(manifest_path)
    matris_payload = load_json_object(matris_path)
    aqcat_payload = load_json_object(aqcat25_path)
    manifest_hash = sha256_file(manifest_path)
    for backend, payload in (("matris", matris_payload), ("aqcat25", aqcat_payload)):
        if payload.get("manifest_sha256") != manifest_hash:
            raise ValueError(f"{backend} result is not bound to the benchmark manifest")
        if payload.get("complete") is not True:
            raise ValueError(f"{backend} result is incomplete")

    matris = _result_map(matris_payload, "matris")
    aqcat25 = _result_map(aqcat_payload, "aqcat25")
    rows = manifest.get("samples")
    if not isinstance(rows, list) or not rows:
        raise ValueError("benchmark manifest has no samples")
    manifest_ids = {str(row.get("sample_id", "")) for row in rows}
    if manifest_ids != set(matris) or manifest_ids != set(aqcat25):
        raise ValueError("manifest and prediction sample sets differ")

    contract = config["data_contract"]
    samples: list[FusionSample] = []
    structure_reactions: dict[str, set[str]] = {}
    energy_group_classes: dict[str, set[str]] = {}
    manifest_root = manifest_path.parent
    for row in rows:
        sample_id = str(row["sample_id"])
        reaction_id = str(row["reaction_id"])
        structure_info = row["structure"]
        structure_path = (manifest_root / str(structure_info["path"])).resolve()
        structure_sha = str(structure_info["sha256"])
        if sha256_file(structure_path) != structure_sha:
            raise ValueError(f"structure hash mismatch: {sample_id}")
        atoms = read(structure_path, format="vasp")
        atom_count = len(atoms)
        symbols = atoms.get_chemical_symbols()
        if atom_count != int(structure_info["atom_count"]) or symbols != list(
            structure_info["symbols"]
        ):
            raise ValueError(f"structure atom identity mismatch: {sample_id}")

        fixed = tuple(sorted(int(value) for value in row["fixed_atom_indices_zero_based"]))
        if len(set(fixed)) != len(fixed) or any(index < 0 or index >= atom_count for index in fixed):
            raise ValueError(f"invalid fixed atom list: {sample_id}")
        movable = tuple(index for index in range(atom_count) if index not in set(fixed))
        if not movable:
            raise ValueError(f"sample has no movable atoms: {sample_id}")

        label = row["vasp_label"]
        if contract["require_normal_vasp_completion"] and label.get("normal_completion") is not True:
            raise ValueError(f"VASP label lacks normal completion: {sample_id}")
        if contract["require_electronic_convergence"] and label.get("electronic_converged") is not True:
            raise ValueError(f"VASP label lacks electronic convergence: {sample_id}")
        vasp_forces = _finite_array(
            label["forces_eV_per_A"], (atom_count, 3), f"{sample_id} VASP forces"
        )
        vasp_energy = float(label["energy_eV"])
        if not math.isfinite(vasp_energy):
            raise ValueError(f"non-finite VASP energy: {sample_id}")

        model_values: dict[str, tuple[float, np.ndarray]] = {}
        for backend, mapped in (("matris", matris), ("aqcat25", aqcat25)):
            result = mapped[sample_id]
            if contract["require_exact_structure_hash_match"] and result.get(
                "structure_sha256"
            ) != structure_sha:
                raise ValueError(f"{backend} structure hash mismatch: {sample_id}")
            single = result.get("single_point", {})
            if single.get("status") != "success":
                raise ValueError(f"{backend} prediction failed: {sample_id}")
            energy = float(single["energy_eV"])
            forces = _finite_array(
                single["forces_eV_per_A"],
                (atom_count, 3),
                f"{sample_id} {backend} forces",
            )
            if not math.isfinite(energy):
                raise ValueError(f"non-finite {backend} energy: {sample_id}")
            model_values[backend] = (energy, forces)

        energy_group_id = str(row["energy_group_id"])
        energy_class = str(label.get("energy_class", ""))
        energy_group_classes.setdefault(energy_group_id, set()).add(energy_class)
        structure_reactions.setdefault(structure_sha, set()).add(reaction_id)
        samples.append(
            FusionSample(
                sample_id=sample_id,
                reaction_id=reaction_id,
                energy_group_id=energy_group_id,
                composition_key=str(row["composition_key"]),
                energy_class=energy_class,
                structure_sha256=structure_sha,
                atoms=atoms,
                fixed_indices=fixed,
                movable_indices=movable,
                vasp_energy=vasp_energy,
                vasp_forces=vasp_forces,
                matris_energy=model_values["matris"][0],
                matris_forces=model_values["matris"][1],
                aqcat25_energy=model_values["aqcat25"][0],
                aqcat25_forces=model_values["aqcat25"][1],
            )
        )

    leakage = {
        structure_hash: sorted(reactions)
        for structure_hash, reactions in structure_reactions.items()
        if len(reactions) > 1
    }
    if leakage:
        raise ValueError(f"exact structures cross reaction folds: {leakage}")
    mixed_energy_classes = {
        group: sorted(classes) for group, classes in energy_group_classes.items() if len(classes) > 1
    }
    if mixed_energy_classes:
        raise ValueError(f"energy group mixes energy classes: {mixed_energy_classes}")

    reactions = sorted({sample.reaction_id for sample in samples})
    if len(reactions) < 3:
        raise ValueError("leave-one-reaction-out requires at least three reactions")
    audit = {
        "sample_count": len(samples),
        "reaction_count": len(reactions),
        "reactions": {
            reaction: {
                "sample_count": sum(sample.reaction_id == reaction for sample in samples),
                "energy_groups": sorted(
                    {sample.energy_group_id for sample in samples if sample.reaction_id == reaction}
                ),
                "energy_classes": sorted(
                    {sample.energy_class for sample in samples if sample.reaction_id == reaction}
                ),
            }
            for reaction in reactions
        },
        "unique_structure_count": len(structure_reactions),
        "cross_reaction_exact_structure_leakage": False,
        "all_vasp_labels_normal_and_electronically_converged": True,
        "all_predictions_complete_and_hash_matched": True,
        "compatibility_branch": manifest.get("compatibility_branch"),
        "raw_inputs_preserved": True,
    }
    return samples, audit


def species_pair_types(samples: Iterable[FusionSample]) -> tuple[tuple[str, str], ...]:
    symbols = sorted({symbol for sample in samples for symbol in sample.atoms.get_chemical_symbols()})
    return tuple((first, second) for index, first in enumerate(symbols) for second in symbols[index:])


def pair_rbf_energy_force_features(
    atoms: Atoms,
    fixed_indices: Iterable[int],
    pair_types: tuple[tuple[str, str], ...],
    *,
    cutoff_A: float,
    radial_basis_count: int,
    center_min_A: float,
) -> tuple[np.ndarray, np.ndarray]:
    if cutoff_A <= center_min_A or radial_basis_count < 2:
        raise ValueError("invalid pair-RBF feature settings")
    pair_index = {pair: index for index, pair in enumerate(pair_types)}
    centers = np.linspace(center_min_A, cutoff_A, radial_basis_count)
    spacing = float(centers[1] - centers[0])
    gamma = 1.0 / (spacing * spacing)
    feature_count = len(pair_types) * radial_basis_count
    energy_features = np.zeros(feature_count, dtype=float)
    force_features = np.zeros((len(atoms), 3, feature_count), dtype=float)
    symbols = atoms.get_chemical_symbols()
    fixed = set(int(value) for value in fixed_indices)
    positions = np.asarray(atoms.positions, dtype=float)
    for first in range(len(atoms) - 1):
        for second in range(first + 1, len(atoms)):
            if first in fixed and second in fixed:
                continue
            displacement, distance = find_mic(
                positions[second] - positions[first], atoms.cell, atoms.pbc
            )
            radius = float(distance)
            if radius <= 1.0e-12 or radius >= cutoff_A:
                continue
            unit = np.asarray(displacement, dtype=float) / radius
            pair = tuple(sorted((symbols[first], symbols[second])))
            offset = pair_index[pair] * radial_basis_count
            cosine = math.cos(math.pi * radius / cutoff_A)
            cutoff = 0.5 * (cosine + 1.0)
            cutoff_derivative = -0.5 * math.pi / cutoff_A * math.sin(
                math.pi * radius / cutoff_A
            )
            gaussian = np.exp(-gamma * (radius - centers) ** 2)
            gaussian_derivative = gaussian * (-2.0 * gamma * (radius - centers))
            values = gaussian * cutoff
            derivatives = gaussian_derivative * cutoff + gaussian * cutoff_derivative
            indices = slice(offset, offset + radial_basis_count)
            energy_features[indices] += values
            pair_forces = unit[:, None] * derivatives[None, :]
            force_features[first, :, indices] += pair_forces
            force_features[second, :, indices] -= pair_forces
    return energy_features, force_features


def _eligible_energy_groups(
    samples: Iterable[FusionSample], minimum_size: int
) -> list[list[FusionSample]]:
    grouped: dict[str, list[FusionSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.energy_group_id, []).append(sample)
    return [
        sorted(group, key=lambda sample: sample.sample_id)
        for _, group in sorted(grouped.items())
        if len(group) >= minimum_size
    ]


def training_rows(
    samples: list[FusionSample],
    feature_cache: PairFeatureCache,
    parameters: MetaParameters,
    minimum_energy_group_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    force_rows: list[np.ndarray] = []
    force_targets: list[float] = []
    feature_map: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for sample in samples:
        pair_energy, pair_forces = feature_cache.get(
            sample, parameters.cutoff_A, parameters.radial_basis_count
        )
        feature_map[sample.sample_id] = (pair_energy, pair_forces)
        for atom_index in sample.movable_indices:
            for component in range(3):
                force_rows.append(
                    np.concatenate(
                        (
                            np.array(
                                [
                                    sample.aqcat25_forces[atom_index, component]
                                    - sample.matris_forces[atom_index, component]
                                ]
                            ),
                            pair_forces[atom_index, component, :],
                        )
                    )
                )
                force_targets.append(
                    float(
                        sample.vasp_forces[atom_index, component]
                        - sample.matris_forces[atom_index, component]
                    )
                )

    energy_rows: list[np.ndarray] = []
    energy_targets: list[float] = []
    for group in _eligible_energy_groups(samples, minimum_energy_group_size):
        rows = []
        targets = []
        for sample in group:
            pair_energy = feature_map[sample.sample_id][0]
            rows.append(
                np.concatenate(
                    (
                        np.array([sample.aqcat25_energy - sample.matris_energy]),
                        pair_energy,
                    )
                )
            )
            targets.append(sample.vasp_energy - sample.matris_energy)
        row_array = np.asarray(rows, dtype=float)
        target_array = np.asarray(targets, dtype=float)
        row_array -= np.mean(row_array, axis=0, keepdims=True)
        target_array -= np.mean(target_array)
        energy_rows.extend(row_array)
        energy_targets.extend(target_array)

    force_x = np.asarray(force_rows, dtype=float)
    force_y = np.asarray(force_targets, dtype=float)
    feature_count = 1 + len(feature_cache.pair_types) * parameters.radial_basis_count
    energy_x = (
        np.asarray(energy_rows, dtype=float)
        if energy_rows
        else np.empty((0, feature_count), dtype=float)
    )
    energy_y = np.asarray(energy_targets, dtype=float)
    return force_x, force_y, energy_x, energy_y


def weighted_objective_rows(
    force_x: np.ndarray,
    force_y: np.ndarray,
    energy_x: np.ndarray,
    energy_y: np.ndarray,
    objective: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    blocks_x: list[np.ndarray] = []
    blocks_y: list[np.ndarray] = []
    if len(force_y):
        factor = math.sqrt(float(objective["force_block_weight"]) / len(force_y)) / float(
            objective["force_scale_eV_per_A"]
        )
        blocks_x.append(force_x * factor)
        blocks_y.append(force_y * factor)
    if len(energy_y):
        factor = math.sqrt(
            float(objective["relative_energy_block_weight"]) / len(energy_y)
        ) / float(objective["relative_energy_scale_eV"])
        blocks_x.append(energy_x * factor)
        blocks_y.append(energy_y * factor)
    if not blocks_x:
        raise ValueError("training objective has no rows")
    return np.vstack(blocks_x), np.concatenate(blocks_y)


def fit_linear_weight(
    samples: list[FusionSample],
    minimum_energy_group_size: int,
    objective: dict[str, Any],
) -> float:
    force_x = []
    force_y = []
    for sample in samples:
        difference = sample.aqcat25_forces - sample.matris_forces
        residual = sample.vasp_forces - sample.matris_forces
        force_x.extend(difference[list(sample.movable_indices), :].reshape(-1))
        force_y.extend(residual[list(sample.movable_indices), :].reshape(-1))
    energy_x = []
    energy_y = []
    for group in _eligible_energy_groups(samples, minimum_energy_group_size):
        difference = np.asarray(
            [sample.aqcat25_energy - sample.matris_energy for sample in group]
        )
        residual = np.asarray([sample.vasp_energy - sample.matris_energy for sample in group])
        energy_x.extend(difference - np.mean(difference))
        energy_y.extend(residual - np.mean(residual))
    x, y = weighted_objective_rows(
        np.asarray(force_x)[:, None],
        np.asarray(force_y),
        np.asarray(energy_x)[:, None],
        np.asarray(energy_y),
        objective,
    )
    denominator = float(np.dot(x[:, 0], x[:, 0]))
    if denominator <= 1.0e-30:
        return 0.0
    return float(np.clip(np.dot(x[:, 0], y) / denominator, 0.0, 1.0))


def fit_meta_coefficients(
    samples: list[FusionSample],
    feature_cache: PairFeatureCache,
    parameters: MetaParameters,
    minimum_energy_group_size: int,
    objective: dict[str, Any],
) -> np.ndarray:
    force_x, force_y, energy_x, energy_y = training_rows(
        samples, feature_cache, parameters, minimum_energy_group_size
    )
    matrix, target = weighted_objective_rows(
        force_x, force_y, energy_x, energy_y, objective
    )
    column_norm = np.linalg.norm(matrix, axis=0)
    column_norm[column_norm < 1.0e-14] = 1.0
    standardized = matrix / column_norm[None, :]
    feature_count = standardized.shape[1]
    augmented_matrix = np.vstack(
        (standardized, math.sqrt(parameters.ridge_alpha) * np.eye(feature_count))
    )
    augmented_target = np.concatenate((target, np.zeros(feature_count)))
    lower = np.full(feature_count, -np.inf)
    upper = np.full(feature_count, np.inf)
    lower[0] = 0.0
    upper[0] = column_norm[0]
    result = lsq_linear(
        augmented_matrix,
        augmented_target,
        bounds=(lower, upper),
        method="bvls",
        tol=1.0e-10,
        max_iter=500,
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        raise RuntimeError(f"conservative meta fit failed: {result.message}")
    return result.x / column_norm


def predict_baselines(sample: FusionSample, linear_weight: float) -> dict[str, Prediction]:
    return {
        "matris": Prediction(sample.matris_energy, sample.matris_forces.copy()),
        "aqcat25": Prediction(sample.aqcat25_energy, sample.aqcat25_forces.copy()),
        "linear_fusion": Prediction(
            sample.matris_energy
            + linear_weight * (sample.aqcat25_energy - sample.matris_energy),
            sample.matris_forces
            + linear_weight * (sample.aqcat25_forces - sample.matris_forces),
        ),
    }


def predict_meta(
    sample: FusionSample,
    feature_cache: PairFeatureCache,
    parameters: MetaParameters,
    coefficients: np.ndarray,
) -> Prediction:
    pair_energy, pair_forces = feature_cache.get(
        sample, parameters.cutoff_A, parameters.radial_basis_count
    )
    weight = float(coefficients[0])
    correction = coefficients[1:]
    energy = (
        sample.matris_energy
        + weight * (sample.aqcat25_energy - sample.matris_energy)
        + float(np.dot(pair_energy, correction))
    )
    forces = (
        sample.matris_forces
        + weight * (sample.aqcat25_forces - sample.matris_forces)
        + np.tensordot(pair_forces, correction, axes=(2, 0))
    )
    return Prediction(float(energy), np.asarray(forces, dtype=float))


def reaction_metrics(
    samples: list[FusionSample],
    predictions: dict[str, Prediction],
    minimum_energy_group_size: int,
) -> dict[str, Any]:
    component_errors = []
    vector_errors = []
    for sample in samples:
        error = predictions[sample.sample_id].forces - sample.vasp_forces
        movable_error = error[list(sample.movable_indices), :]
        component_errors.extend(movable_error.reshape(-1))
        vector_errors.extend(np.linalg.norm(movable_error, axis=1))
    components = np.asarray(component_errors, dtype=float)
    vectors = np.asarray(vector_errors, dtype=float)
    energy_errors = []
    energy_group_count = 0
    lowest_matches = 0
    for group in _eligible_energy_groups(samples, minimum_energy_group_size):
        reference = np.asarray([sample.vasp_energy for sample in group])
        predicted = np.asarray([predictions[sample.sample_id].energy for sample in group])
        reference_relative = reference - np.min(reference)
        predicted_relative = predicted - np.min(predicted)
        energy_errors.extend(predicted_relative - reference_relative)
        energy_group_count += 1
        lowest_matches += int(int(np.argmin(reference)) == int(np.argmin(predicted)))
    energy_array = np.asarray(energy_errors, dtype=float)
    return {
        "sample_count": len(samples),
        "movable_atom_force_vector_count": int(len(vectors)),
        "force_component_mae_eV_per_A": float(np.mean(np.abs(components))),
        "force_component_rmse_eV_per_A": float(np.sqrt(np.mean(components**2))),
        "force_vector_rmse_eV_per_A": float(np.sqrt(np.mean(vectors**2))),
        "force_vector_p95_eV_per_A": float(np.quantile(vectors, 0.95)),
        "force_vector_max_eV_per_A": float(np.max(vectors)),
        "relative_energy_sample_count": int(len(energy_array)),
        "relative_energy_group_count": energy_group_count,
        "relative_energy_mae_eV": (
            float(np.mean(np.abs(energy_array))) if len(energy_array) else None
        ),
        "relative_energy_rmse_eV": (
            float(np.sqrt(np.mean(energy_array**2))) if len(energy_array) else None
        ),
        "lowest_energy_match_count": lowest_matches,
    }


def sample_metric_rows(
    samples: list[FusionSample],
    predictions_by_model: dict[str, dict[str, Prediction]],
    minimum_energy_group_size: int,
) -> list[dict[str, Any]]:
    relative_errors: dict[tuple[str, str], float] = {}
    for model, predictions in predictions_by_model.items():
        for group in _eligible_energy_groups(samples, minimum_energy_group_size):
            reference = np.asarray([sample.vasp_energy for sample in group])
            predicted = np.asarray([predictions[sample.sample_id].energy for sample in group])
            errors = (predicted - np.min(predicted)) - (reference - np.min(reference))
            for sample, error in zip(group, errors):
                relative_errors[(model, sample.sample_id)] = float(error)
    rows = []
    for model in MODEL_ORDER:
        predictions = predictions_by_model[model]
        for sample in sorted(samples, key=lambda value: value.sample_id):
            error = predictions[sample.sample_id].forces - sample.vasp_forces
            movable = error[list(sample.movable_indices), :]
            vector = np.linalg.norm(movable, axis=1)
            rows.append(
                {
                    "reaction_id": sample.reaction_id,
                    "sample_id": sample.sample_id,
                    "model": model,
                    "force_component_mae_eV_per_A": float(np.mean(np.abs(movable))),
                    "force_vector_rmse_eV_per_A": float(np.sqrt(np.mean(vector**2))),
                    "force_vector_max_eV_per_A": float(np.max(vector)),
                    "relative_energy_error_eV": relative_errors.get((model, sample.sample_id)),
                }
            )
    return rows


def normalized_validation_score(metrics: dict[str, Any], objective: dict[str, Any]) -> float:
    force_score = metrics["force_vector_rmse_eV_per_A"] / float(
        objective["force_scale_eV_per_A"]
    )
    energy = metrics["relative_energy_rmse_eV"]
    if energy is None:
        return float(force_score)
    energy_score = energy / float(objective["relative_energy_scale_eV"])
    force_weight = float(objective["force_block_weight"])
    energy_weight = float(objective["relative_energy_block_weight"])
    return float((force_weight * force_score + energy_weight * energy_score) / (force_weight + energy_weight))


def select_meta_parameters(
    training_samples: list[FusionSample],
    feature_cache: PairFeatureCache,
    config: dict[str, Any],
) -> tuple[MetaParameters, list[dict[str, Any]]]:
    meta = config["models"]["conservative_meta"]
    minimum_size = int(config["data_contract"]["minimum_energy_group_size"])
    objective = config["fit_objective"]
    reactions = sorted({sample.reaction_id for sample in training_samples})
    candidates = [
        MetaParameters(float(cutoff), int(count), float(alpha))
        for cutoff, count, alpha in itertools.product(
            meta["cutoff_A_grid"],
            meta["radial_basis_count_grid"],
            meta["ridge_alpha_grid"],
        )
    ]
    assessments = []
    for candidate in candidates:
        scores = []
        for heldout in reactions:
            inner_train = [sample for sample in training_samples if sample.reaction_id != heldout]
            inner_test = [sample for sample in training_samples if sample.reaction_id == heldout]
            coefficients = fit_meta_coefficients(
                inner_train, feature_cache, candidate, minimum_size, objective
            )
            predictions = {
                sample.sample_id: predict_meta(sample, feature_cache, candidate, coefficients)
                for sample in inner_test
            }
            metrics = reaction_metrics(inner_test, predictions, minimum_size)
            scores.append(normalized_validation_score(metrics, objective))
        assessments.append(
            {
                "cutoff_A": candidate.cutoff_A,
                "radial_basis_count": candidate.radial_basis_count,
                "ridge_alpha": candidate.ridge_alpha,
                "nested_macro_score": float(np.mean(scores)),
                "inner_fold_scores": scores,
            }
        )
    best = min(
        assessments,
        key=lambda row: (
            row["nested_macro_score"],
            row["radial_basis_count"],
            row["cutoff_A"],
            -row["ridge_alpha"],
        ),
    )
    return (
        MetaParameters(
            cutoff_A=float(best["cutoff_A"]),
            radial_basis_count=int(best["radial_basis_count"]),
            ridge_alpha=float(best["ridge_alpha"]),
        ),
        assessments,
    )


def exact_sign_flip_pvalue(differences: Iterable[float]) -> float:
    values = np.asarray(list(differences), dtype=float)
    if len(values) == 0 or not np.all(np.isfinite(values)):
        raise ValueError("sign-flip test requires finite paired differences")
    observed = float(np.mean(values))
    if observed <= 0.0:
        return 1.0
    count = 0
    total = 2 ** len(values)
    for signs in itertools.product((-1.0, 1.0), repeat=len(values)):
        permuted = float(np.mean(values * np.asarray(signs)))
        if permuted >= observed - 1.0e-15:
            count += 1
    return float(count / total)


def bootstrap_relative_improvement(
    baseline: Iterable[float],
    candidate: Iterable[float],
    *,
    resamples: int,
    seed: int,
) -> dict[str, float]:
    baseline_values = np.asarray(list(baseline), dtype=float)
    candidate_values = np.asarray(list(candidate), dtype=float)
    if baseline_values.shape != candidate_values.shape or len(baseline_values) == 0:
        raise ValueError("bootstrap inputs must be nonempty paired vectors")
    estimate = 1.0 - float(np.mean(candidate_values) / np.mean(baseline_values))
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(baseline_values), size=(resamples, len(baseline_values)))
    sampled_baseline = np.mean(baseline_values[indices], axis=1)
    sampled_candidate = np.mean(candidate_values[indices], axis=1)
    improvements = 1.0 - sampled_candidate / sampled_baseline
    return {
        "estimate": estimate,
        "ci95_low": float(np.quantile(improvements, 0.025)),
        "ci95_high": float(np.quantile(improvements, 0.975)),
    }


def promotion_assessment(
    fold_rows: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, Any]:
    gate = config["promotion_gate"]
    by_model = {
        model: {row["reaction_id"]: row for row in fold_rows if row["model"] == model}
        for model in MODEL_ORDER
    }
    reactions = sorted(by_model["matris"])
    matris_force = [by_model["matris"][reaction]["force_vector_rmse_eV_per_A"] for reaction in reactions]
    meta_force = [
        by_model["conservative_meta"][reaction]["force_vector_rmse_eV_per_A"]
        for reaction in reactions
    ]
    energy_reactions = [
        reaction
        for reaction in reactions
        if by_model["matris"][reaction]["relative_energy_rmse_eV"] is not None
        and by_model["conservative_meta"][reaction]["relative_energy_rmse_eV"] is not None
    ]
    matris_energy = [
        by_model["matris"][reaction]["relative_energy_rmse_eV"]
        for reaction in energy_reactions
    ]
    meta_energy = [
        by_model["conservative_meta"][reaction]["relative_energy_rmse_eV"]
        for reaction in energy_reactions
    ]
    seed = int(gate["random_seed"])
    resamples = int(gate["bootstrap_resamples"])
    force_improvement = bootstrap_relative_improvement(
        matris_force, meta_force, resamples=resamples, seed=seed
    )
    energy_improvement = bootstrap_relative_improvement(
        matris_energy, meta_energy, resamples=resamples, seed=seed + 1
    )
    force_p = exact_sign_flip_pvalue(
        baseline - candidate for baseline, candidate in zip(matris_force, meta_force)
    )
    energy_p = exact_sign_flip_pvalue(
        baseline - candidate for baseline, candidate in zip(matris_energy, meta_energy)
    )
    force_wins = sum(candidate < baseline for baseline, candidate in zip(matris_force, meta_force))
    energy_wins = sum(candidate < baseline for baseline, candidate in zip(matris_energy, meta_energy))
    max_regressions = []
    for reaction in reactions:
        baseline_max = by_model["matris"][reaction]["force_vector_max_eV_per_A"]
        candidate_max = by_model["conservative_meta"][reaction]["force_vector_max_eV_per_A"]
        max_regressions.append(candidate_max / baseline_max - 1.0)

    threshold = float(gate["minimum_macro_relative_improvement"])
    alpha = float(gate["one_sided_exact_sign_flip_alpha"])
    checks = {
        "force_macro_improvement": force_improvement["estimate"] >= threshold,
        "energy_macro_improvement": energy_improvement["estimate"] >= threshold,
        "force_exact_sign_flip": force_p < alpha,
        "energy_exact_sign_flip": energy_p < alpha,
        "force_every_reaction_win": (
            force_wins == len(reactions)
            if gate["require_force_win_on_every_reaction"]
            else True
        ),
        "energy_every_reaction_win": (
            energy_wins == len(energy_reactions)
            if gate["require_energy_win_on_every_eligible_reaction"]
            else True
        ),
        "force_vector_max_regression": max(max_regressions)
        <= float(gate["maximum_allowed_force_vector_max_regression_fraction"]),
    }
    passed = all(checks.values())
    return {
        "decision": gate["pass_action"] if passed else gate["fail_action"],
        "promotion_gate_passed": passed,
        "checks": checks,
        "force": {
            "reaction_count": len(reactions),
            "wins": force_wins,
            "macro_relative_improvement": force_improvement,
            "one_sided_exact_sign_flip_p": force_p,
            "maximum_vector_max_regression_fraction": float(max(max_regressions)),
        },
        "relative_energy": {
            "reaction_count": len(energy_reactions),
            "wins": energy_wins,
            "macro_relative_improvement": energy_improvement,
            "one_sided_exact_sign_flip_p": energy_p,
        },
        "statistical_boundary": (
            "exploratory reaction-blocked inference with only five reactions; "
            "the exact sign-flip test has coarse resolution"
        ),
    }


def comparisons_against_matris(
    fold_rows: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    gate = config["promotion_gate"]
    by_model = {
        model: {row["reaction_id"]: row for row in fold_rows if row["model"] == model}
        for model in MODEL_ORDER
    }
    reactions = sorted(by_model["matris"])
    comparisons: dict[str, dict[str, Any]] = {}
    for model_index, model in enumerate(MODEL_ORDER[1:], start=1):
        force_baseline = [
            by_model["matris"][reaction]["force_vector_rmse_eV_per_A"]
            for reaction in reactions
        ]
        force_candidate = [
            by_model[model][reaction]["force_vector_rmse_eV_per_A"]
            for reaction in reactions
        ]
        energy_reactions = [
            reaction
            for reaction in reactions
            if by_model["matris"][reaction]["relative_energy_rmse_eV"] is not None
            and by_model[model][reaction]["relative_energy_rmse_eV"] is not None
        ]
        energy_baseline = [
            by_model["matris"][reaction]["relative_energy_rmse_eV"]
            for reaction in energy_reactions
        ]
        energy_candidate = [
            by_model[model][reaction]["relative_energy_rmse_eV"]
            for reaction in energy_reactions
        ]
        seed = int(gate["random_seed"]) + model_index * 10
        comparisons[model] = {
            "force": {
                "wins": sum(
                    candidate < baseline
                    for baseline, candidate in zip(force_baseline, force_candidate)
                ),
                "reaction_count": len(reactions),
                "macro_relative_improvement": bootstrap_relative_improvement(
                    force_baseline,
                    force_candidate,
                    resamples=int(gate["bootstrap_resamples"]),
                    seed=seed,
                ),
                "one_sided_exact_sign_flip_p": exact_sign_flip_pvalue(
                    baseline - candidate
                    for baseline, candidate in zip(force_baseline, force_candidate)
                ),
            },
            "relative_energy": {
                "wins": sum(
                    candidate < baseline
                    for baseline, candidate in zip(energy_baseline, energy_candidate)
                ),
                "reaction_count": len(energy_reactions),
                "macro_relative_improvement": bootstrap_relative_improvement(
                    energy_baseline,
                    energy_candidate,
                    resamples=int(gate["bootstrap_resamples"]),
                    seed=seed + 1,
                ),
                "one_sided_exact_sign_flip_p": exact_sign_flip_pvalue(
                    baseline - candidate
                    for baseline, candidate in zip(energy_baseline, energy_candidate)
                ),
            },
        }
    return comparisons


def macro_summary(fold_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary = {}
    for model in MODEL_ORDER:
        rows = [row for row in fold_rows if row["model"] == model]
        energy_values = [
            row["relative_energy_rmse_eV"]
            for row in rows
            if row["relative_energy_rmse_eV"] is not None
        ]
        summary[model] = {
            "reaction_count": len(rows),
            "macro_force_vector_rmse_eV_per_A": float(
                np.mean([row["force_vector_rmse_eV_per_A"] for row in rows])
            ),
            "macro_force_vector_max_eV_per_A": float(
                np.mean([row["force_vector_max_eV_per_A"] for row in rows])
            ),
            "energy_reaction_count": len(energy_values),
            "macro_relative_energy_rmse_eV": float(np.mean(energy_values)),
        }
    return summary


def _write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _plot_metric(
    fold_rows: list[dict[str, Any]], metric: str, ylabel: str, output: Path
) -> None:
    reactions = sorted({row["reaction_id"] for row in fold_rows})
    width = 0.19
    x = np.arange(len(reactions), dtype=float)
    fig, axis = plt.subplots(figsize=(11.0, 5.5))
    for model_index, model in enumerate(MODEL_ORDER):
        mapped = {
            row["reaction_id"]: row[metric]
            for row in fold_rows
            if row["model"] == model
        }
        values = [mapped[reaction] for reaction in reactions]
        axis.bar(
            x + (model_index - 1.5) * width,
            values,
            width=width,
            label=MODEL_LABELS[model],
        )
    axis.set_xticks(x)
    axis.set_xticklabels(reactions, rotation=20, ha="right")
    axis.set_ylabel(ylabel)
    axis.set_title("Leave-one-reaction-out offline fusion test")
    axis.legend(frameon=False, ncol=2)
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _report_markdown(
    audit: dict[str, Any],
    macro: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
    promotion: dict[str, Any],
    fold_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# MatRIS–AQCat25 离线融合可行性试验",
        "",
        "## 结论",
        "",
        f"晋级判定：`{promotion['decision']}`。",
        "",
        "本试验只使用既有 VASP 标签和既有两模型预测；没有运行新推理、VASP、GPU训练或远程作业。",
        "",
        "## 数据",
        "",
        f"- 样本：{audit['sample_count']} 个；反应留一折：{audit['reaction_count']} 个。",
        "- 力指标仅使用清单声明的可移动原子。",
        "- 能量只在同组成、同 energy_group 内计算相对能量。",
        "- 未发现跨反应完全相同结构哈希泄漏。",
        "",
        "## 宏平均指标",
        "",
        "| 模型 | 力矢量 RMSE (eV/Å) | 相对能量 RMSE (eV) |",
        "|---|---:|---:|",
    ]
    for model in MODEL_ORDER:
        row = macro[model]
        lines.append(
            f"| {MODEL_LABELS[model]} | {row['macro_force_vector_rmse_eV_per_A']:.6f} "
            f"| {row['macro_relative_energy_rmse_eV']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## 各候选相对 MatRIS",
            "",
            "| 候选 | 力宏平均改善 | 力胜出折数 | 力 p | 能量宏平均改善 | 能量胜出折数 | 能量 p |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for model in MODEL_ORDER[1:]:
        comparison = comparisons[model]
        lines.append(
            f"| {MODEL_LABELS[model]} | "
            f"{comparison['force']['macro_relative_improvement']['estimate']:.2%} | "
            f"{comparison['force']['wins']}/{comparison['force']['reaction_count']} | "
            f"{comparison['force']['one_sided_exact_sign_flip_p']:.5f} | "
            f"{comparison['relative_energy']['macro_relative_improvement']['estimate']:.2%} | "
            f"{comparison['relative_energy']['wins']}/{comparison['relative_energy']['reaction_count']} | "
            f"{comparison['relative_energy']['one_sided_exact_sign_flip_p']:.5f} |"
        )
    lines.extend(
        [
            "",
            "## 保守型元模型相对 MatRIS 的晋级检查",
            "",
            f"- 力宏平均相对改善：{promotion['force']['macro_relative_improvement']['estimate']:.2%}；"
            f"精确单侧符号翻转 p={promotion['force']['one_sided_exact_sign_flip_p']:.5f}；"
            f"胜出 {promotion['force']['wins']}/{promotion['force']['reaction_count']} 折。",
            f"- 相对能量宏平均改善：{promotion['relative_energy']['macro_relative_improvement']['estimate']:.2%}；"
            f"精确单侧符号翻转 p={promotion['relative_energy']['one_sided_exact_sign_flip_p']:.5f}；"
            f"胜出 {promotion['relative_energy']['wins']}/{promotion['relative_energy']['reaction_count']} 折。",
            "",
            "| 检查 | 结果 |",
            "|---|---|",
        ]
    )
    for name, passed in promotion["checks"].items():
        lines.append(f"| `{name}` | {'PASS' if passed else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## 逐反应结果",
            "",
            "| 留出反应 | 模型 | 力矢量 RMSE (eV/Å) | 相对能量 RMSE (eV) |",
            "|---|---|---:|---:|",
        ]
    )
    for row in sorted(fold_rows, key=lambda value: (value["reaction_id"], MODEL_ORDER.index(value["model"]))):
        energy = row["relative_energy_rmse_eV"]
        energy_text = "NA" if energy is None else f"{energy:.6f}"
        lines.append(
            f"| {row['reaction_id']} | {MODEL_LABELS[row['model']]} | "
            f"{row['force_vector_rmse_eV_per_A']:.6f} | {energy_text} |"
        )
    lines.extend(
        [
            "",
            "## 模型边界",
            "",
            "- 线性融合使用同一个 0–1 权重混合两模型能量和力。",
            "- 保守型元模型以 MatRIS 为锚点，增加有界 AQCat25差分和低容量 pair-RBF 能量修正；力由同一能量表达式解析导出。",
            "- 这不是论文 GNN 的完整复现，而是小数据条件下的预注册、低容量可行性门。",
            "- 只有全部晋级条件通过，才允许另行评审主动学习扩充和蒸馏；本报告本身不晋升 checkpoint。",
            "- 反应数只有五个，统计检验分辨率有限，结果属于反应块级探索性证据。",
            "",
        ]
    )
    return "\n".join(lines)


def _source_bindings(config_path: Path, source_paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "config": {"path": str(config_path.resolve()), "sha256": sha256_file(config_path)},
        **{
            name: {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for name, path in source_paths.items()
        },
    }


def _prepare_destination(destination: Path, resume: bool, bindings: dict[str, Any]) -> dict[str, Any]:
    if destination.exists() and any(destination.iterdir()):
        if not resume:
            raise FileExistsError(
                f"destination is nonempty; use a new directory or --resume: {destination}"
            )
        state_path = destination / "run_state.json"
        if not state_path.is_file():
            raise ValueError("resume destination lacks run_state.json")
        state = load_json_object(state_path)
        if state.get("source_bindings") != bindings:
            raise ValueError("resume source bindings differ from the original run")
        return state
    destination.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "document_kind": "offline_mlip_fusion_feasibility_run_state",
        "status": "running",
        "source_bindings": bindings,
        "completed_reactions": [],
        "automatic_submissions": 0,
    }
    write_json_atomic(destination / "run_state.json", state, ensure_ascii=True)
    return state


def run(config_path: Path, output: Path, resume: bool = False) -> dict[str, Any]:
    config_path = config_path.resolve()
    root = config_path.parents[1]
    config = _load_config(config_path)
    source_paths = {
        name: _resolve_source(root, configured)
        for name, configured in config["sources"].items()
    }
    bindings = _source_bindings(config_path, source_paths)
    state = _prepare_destination(output, resume, bindings)
    try:
        samples, audit = load_samples(
            source_paths["benchmark_manifest"],
            source_paths["matris_results"],
            source_paths["aqcat25_results"],
            config,
        )
        write_json_atomic(output / "data_audit.json", audit, ensure_ascii=True)
        pair_types = species_pair_types(samples)
        feature_cache = PairFeatureCache(
            pair_types,
            float(config["models"]["conservative_meta"]["radial_center_min_A"]),
        )
        minimum_size = int(config["data_contract"]["minimum_energy_group_size"])
        objective = config["fit_objective"]
        reactions = sorted({sample.reaction_id for sample in samples})
        fold_rows: list[dict[str, Any]] = []
        sample_rows: list[dict[str, Any]] = []
        selection_records = []
        completed = set(state.get("completed_reactions", []))
        for heldout_reaction in reactions:
            fold_path = output / "folds" / f"{heldout_reaction}.json"
            if resume and heldout_reaction in completed and fold_path.is_file():
                fold = load_json_object(fold_path)
            else:
                training = [sample for sample in samples if sample.reaction_id != heldout_reaction]
                testing = [sample for sample in samples if sample.reaction_id == heldout_reaction]
                linear_weight = fit_linear_weight(training, minimum_size, objective)
                selected, nested = select_meta_parameters(training, feature_cache, config)
                coefficients = fit_meta_coefficients(
                    training, feature_cache, selected, minimum_size, objective
                )
                predictions_by_model: dict[str, dict[str, Prediction]] = {
                    model: {} for model in MODEL_ORDER
                }
                for sample in testing:
                    baselines = predict_baselines(sample, linear_weight)
                    for model, prediction in baselines.items():
                        predictions_by_model[model][sample.sample_id] = prediction
                    predictions_by_model["conservative_meta"][sample.sample_id] = predict_meta(
                        sample, feature_cache, selected, coefficients
                    )
                metrics = {
                    model: reaction_metrics(
                        testing, predictions_by_model[model], minimum_size
                    )
                    for model in MODEL_ORDER
                }
                fold = {
                    "schema_version": 1,
                    "document_kind": "offline_mlip_fusion_leave_one_reaction_fold",
                    "heldout_reaction": heldout_reaction,
                    "training_reactions": sorted(
                        {sample.reaction_id for sample in training}
                    ),
                    "training_sample_count": len(training),
                    "test_sample_count": len(testing),
                    "linear_weight_aqcat25": linear_weight,
                    "selected_meta_parameters": {
                        "cutoff_A": selected.cutoff_A,
                        "radial_basis_count": selected.radial_basis_count,
                        "ridge_alpha": selected.ridge_alpha,
                    },
                    "meta_aqcat25_weight": float(coefficients[0]),
                    "meta_coefficient_l2_norm": float(np.linalg.norm(coefficients[1:])),
                    "nested_model_selection": nested,
                    "metrics": metrics,
                    "sample_metrics": sample_metric_rows(
                        testing, predictions_by_model, minimum_size
                    ),
                    "heldout_used_for_fit_or_selection": False,
                }
                write_json_atomic(fold_path, fold, ensure_ascii=True)
                completed.add(heldout_reaction)
                state["completed_reactions"] = sorted(completed)
                write_json_atomic(output / "run_state.json", state, ensure_ascii=True)

            for model in MODEL_ORDER:
                fold_rows.append(
                    {
                        "reaction_id": heldout_reaction,
                        "model": model,
                        **fold["metrics"][model],
                        "linear_weight_aqcat25": fold["linear_weight_aqcat25"],
                        "meta_aqcat25_weight": fold["meta_aqcat25_weight"],
                        "meta_cutoff_A": fold["selected_meta_parameters"]["cutoff_A"],
                        "meta_radial_basis_count": fold["selected_meta_parameters"][
                            "radial_basis_count"
                        ],
                        "meta_ridge_alpha": fold["selected_meta_parameters"]["ridge_alpha"],
                    }
                )
            sample_rows.extend(fold["sample_metrics"])
            selection_records.append(
                {
                    "heldout_reaction": heldout_reaction,
                    "linear_weight_aqcat25": fold["linear_weight_aqcat25"],
                    "selected_meta_parameters": fold["selected_meta_parameters"],
                    "meta_aqcat25_weight": fold["meta_aqcat25_weight"],
                    "nested_model_selection": fold["nested_model_selection"],
                }
            )

        macro = macro_summary(fold_rows)
        comparisons = comparisons_against_matris(fold_rows, config)
        promotion = promotion_assessment(fold_rows, config)
        summary = {
            "schema_version": 1,
            "document_kind": "offline_mlip_fusion_feasibility_summary",
            "workflow_kind": config["workflow_kind"],
            "source_bindings": bindings,
            "data_audit": audit,
            "model_definition": config["models"],
            "macro_metrics": macro,
            "comparisons_vs_matris": comparisons,
            "promotion_assessment": promotion,
            "scientific_boundaries": config["scientific_boundaries"],
            "new_calculations_submitted": 0,
            "new_model_predictions_run": 0,
            "checkpoints_modified": 0,
        }
        _write_csv_atomic(output / "fold_metrics.csv", fold_rows)
        _write_csv_atomic(output / "sample_metrics.csv", sample_rows)
        write_json_atomic(
            output / "model_selection.json",
            {"folds": selection_records},
            ensure_ascii=True,
        )
        write_json_atomic(output / "summary.json", summary, ensure_ascii=True)
        (output / "report.md").write_text(
            _report_markdown(audit, macro, comparisons, promotion, fold_rows),
            encoding="utf-8",
            newline="\n",
        )
        _plot_metric(
            fold_rows,
            "force_vector_rmse_eV_per_A",
            "Force vector RMSE (eV/Angstrom)",
            output / "force_rmse_by_reaction.png",
        )
        _plot_metric(
            fold_rows,
            "relative_energy_rmse_eV",
            "Relative-energy RMSE (eV)",
            output / "relative_energy_rmse_by_reaction.png",
        )
        state.update(
            {
                "status": "complete",
                "completed_reactions": reactions,
                "summary_sha256": sha256_file(output / "summary.json"),
                "promotion_gate_passed": promotion["promotion_gate_passed"],
                "decision": promotion["decision"],
            }
        )
        write_json_atomic(output / "run_state.json", state, ensure_ascii=True)
        return summary
    except BaseException as error:
        state.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        )
        write_json_atomic(output / "run_state.json", state, ensure_ascii=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/offline_mlip_fusion_feasibility.yaml"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume completed reaction folds only when source hashes are unchanged.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = run(args.config, args.output, resume=args.resume)
    print(json.dumps(summary["promotion_assessment"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
