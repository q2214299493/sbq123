#!/usr/bin/env python3
"""Run exact-structure MatRIS/AQCat25 energy-and-force predictions for a TS path."""

from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import numpy as np
from ase.io import read

try:
    from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic, require_sha256 as _sha256
    from scripts.mlip_same_structure_benchmark import _load_calculator
except ModuleNotFoundError:  # MZ73 deploys these files in one directory.
    from artifact_io import load_json_object, sha256_file, write_json_atomic, require_sha256 as _sha256
    from mlip_same_structure_benchmark import _load_calculator


CalculatorLoader = Callable[[str, Path, str], Any]


def _attach_model_context(
    atoms: Any,
    bond_changes: list[dict[str, Any]],
    adsorbate_indices: list[int],
) -> None:
    atoms.info["is_spin_off"] = False
    atoms.info["is_low_fi"] = False
    atoms.info["bonds_TS"] = [
        [change["atoms_1based"][0] - 1, change["atoms_1based"][1] - 1, change["change"]]
        for change in bond_changes
    ]
    atoms.info["indices_ads"] = adsorbate_indices




def _relative_file(root: Path, value: Any, *, label: str) -> Path:
    relative = PurePosixPath(str(value))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must be a safe POSIX relative path")
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*relative.parts).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError(f"{label} escapes its root")
    if not candidate.is_file():
        raise FileNotFoundError(f"{label} does not exist: {candidate}")
    return candidate


def validate_request(request_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    request = load_json_object(request_path)
    if request.get("schema_version") != 1 or request.get("document_kind") != (
        "dual_model_ts_path_force_prediction_batch_request"
    ):
        raise ValueError("invalid dual-model TS prediction request")
    if request.get("automatic_vasp_submission") is not False:
        raise ValueError("automatic_vasp_submission must be false")
    models = request.get("models")
    if not isinstance(models, dict) or set(models) != {"primary", "secondary"}:
        raise ValueError("request must bind primary and secondary models")
    expected_backends = {"primary": "matris", "secondary": "aqcat25"}
    for role, backend in expected_backends.items():
        model = models[role]
        if not isinstance(model, dict) or model.get("backend") != backend:
            raise ValueError(f"{role} backend must be {backend}")
        _sha256(model.get("checkpoint_sha256"), label=f"{role} checkpoint")

    changes = request.get("indexed_bond_changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("indexed_bond_changes must be a non-empty list")
    fixed = request.get("fixed_atom_indices_zero_based")
    if not isinstance(fixed, list) or any(not isinstance(value, int) or value < 0 for value in fixed):
        raise ValueError("fixed_atom_indices_zero_based is invalid")

    rows = request.get("structures")
    if not isinstance(rows, list) or len(rows) < 3:
        raise ValueError("at least three exact structures are required")
    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("structure row must be an object")
        sample_id = str(row.get("sample_id", ""))
        if not sample_id or sample_id in seen_ids:
            raise ValueError("sample IDs must be non-empty and unique")
        seen_ids.add(sample_id)
        structure_path = _relative_file(
            request_path.parent, row.get("path"), label=f"sample {sample_id} structure"
        )
        expected_hash = _sha256(row.get("sha256"), label=f"sample {sample_id} structure")
        if sha256_file(structure_path) != expected_hash:
            raise ValueError(f"sample {sample_id} structure hash mismatch")
        validated.append(
            {
                "sample_id": sample_id,
                "path": structure_path,
                "sha256": expected_hash,
                "source_stage": str(row.get("source_stage", "unspecified")),
                "image": str(row.get("image", sample_id)),
                "selection_role": str(row.get("selection_role", "path_member")),
            }
        )
    return request, validated


def _verify_checkpoint(path: Path, expected_sha256: str, *, role: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{role} checkpoint is missing: {path}")
    if sha256_file(path) != expected_sha256:
        raise ValueError(f"{role} checkpoint hash mismatch")


def _predict_all(
    rows: list[dict[str, Any]],
    *,
    backend: str,
    checkpoint: Path,
    device: str,
    indexed_bond_changes: list[dict[str, Any]],
    calculator_loader: CalculatorLoader,
) -> list[tuple[float, np.ndarray]]:
    calculator = calculator_loader(backend, checkpoint, device)
    predictions: list[tuple[float, np.ndarray]] = []
    try:
        for row in rows:
            atoms = read(row["path"])
            adsorbate_indices = [
                index for index, symbol in enumerate(atoms.get_chemical_symbols()) if symbol != "Fe"
            ]
            _attach_model_context(atoms, indexed_bond_changes, adsorbate_indices)
            atoms.calc = calculator
            energy = float(atoms.get_potential_energy())
            forces = np.asarray(atoms.get_forces(), dtype=float)
            if not math.isfinite(energy) or forces.shape != (len(atoms), 3):
                raise RuntimeError(f"{backend} returned an invalid prediction for {row['sample_id']}")
            if not np.isfinite(forces).all():
                raise RuntimeError(f"{backend} returned non-finite forces for {row['sample_id']}")
            predictions.append((energy, forces.copy()))
    finally:
        del calculator
        gc.collect()
        try:
            import torch

            if device.startswith("cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
    return predictions


def _geometry_records(
    rows: list[dict[str, Any]], indexed_bond_changes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        atoms = read(row["path"])
        bonds = []
        for change in indexed_bond_changes:
            first, second = (int(value) - 1 for value in change["atoms_1based"])
            bonds.append(
                {
                    "atoms_1based": change["atoms_1based"],
                    "change": change["change"],
                    "distance_A": float(atoms.get_distance(first, second, mic=True)),
                }
            )
        records.append(
            {
                "key_bond_distances_A": bonds,
                "reaction_coordinate_value_A": bonds[0]["distance_A"],
            }
        )
    return records


def run_batch(
    request_path: Path,
    primary_checkpoint: Path,
    secondary_checkpoint: Path,
    output_path: Path,
    *,
    device: str,
    calculator_loader: CalculatorLoader = _load_calculator,
) -> dict[str, Any]:
    request_path = request_path.resolve()
    request, rows = validate_request(request_path)
    models = request["models"]
    _verify_checkpoint(primary_checkpoint, models["primary"]["checkpoint_sha256"], role="primary")
    _verify_checkpoint(
        secondary_checkpoint, models["secondary"]["checkpoint_sha256"], role="secondary"
    )
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")

    primary = _predict_all(
        rows,
        backend=models["primary"]["backend"],
        checkpoint=primary_checkpoint,
        device=device,
        indexed_bond_changes=request["indexed_bond_changes"],
        calculator_loader=calculator_loader,
    )
    secondary = _predict_all(
        rows,
        backend=models["secondary"]["backend"],
        checkpoint=secondary_checkpoint,
        device=device,
        indexed_bond_changes=request["indexed_bond_changes"],
        calculator_loader=calculator_loader,
    )
    geometries = _geometry_records(rows, request["indexed_bond_changes"])

    fixed = set(request["fixed_atom_indices_zero_based"])
    records: list[dict[str, Any]] = []
    for row, geometry, (primary_energy, primary_forces), (
        secondary_energy,
        secondary_forces,
    ) in zip(
        rows, geometries, primary, secondary, strict=True
    ):
        if primary_forces.shape != secondary_forces.shape:
            raise RuntimeError(f"model force-shape mismatch for {row['sample_id']}")
        movable = np.asarray(
            [index for index in range(len(primary_forces)) if index not in fixed], dtype=int
        )
        difference = primary_forces[movable] - secondary_forces[movable]
        vector_norms = np.linalg.norm(difference, axis=1)
        records.append(
            {
                "sample_id": row["sample_id"],
                "image": row["image"],
                "source_stage": row["source_stage"],
                "selection_role": row["selection_role"],
                "structure_sha256": row["sha256"],
                **geometry,
                "primary_energy_eV": primary_energy,
                "secondary_energy_eV": secondary_energy,
                "primary_forces_eV_per_A": primary_forces.tolist(),
                "secondary_forces_eV_per_A": secondary_forces.tolist(),
                "movable_force_difference": {
                    "component_rmse_eV_per_A": float(np.sqrt(np.mean(difference**2))),
                    "vector_rmse_eV_per_A": float(np.sqrt(np.mean(vector_norms**2))),
                    "vector_max_eV_per_A": float(vector_norms.max()) if len(vector_norms) else 0.0,
                },
            }
        )

    result = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_path_force_prediction_set",
        "source_request_sha256": sha256_file(request_path),
        "models": {
            role: {
                "backend": models[role]["backend"],
                "identifier": models[role].get("identifier"),
                "checkpoint_sha256": models[role]["checkpoint_sha256"],
            }
            for role in ("primary", "secondary")
        },
        "fixed_atom_indices_zero_based": request["fixed_atom_indices_zero_based"],
        "predictions": records,
        "comparison_scope": "exact_structure_hashes; full per-atom forces; movable-atom disagreement",
        "interpretation": "model_model_disagreement_for_sampling_not_calibrated_uncertainty",
        "reportable_dft": False,
        "automatic_vasp_submission": False,
    }
    write_json_atomic(output_path, result, ensure_ascii=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a hash-bound exact-structure MatRIS/AQCat25 TS prediction batch."
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--primary-checkpoint", type=Path, required=True)
    parser.add_argument("--secondary-checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    request, rows = validate_request(args.request)
    if args.validate_only:
        print(
            json.dumps(
                {
                    "status": "valid",
                    "request_sha256": sha256_file(args.request),
                    "sample_count": len(rows),
                    "models": request["models"],
                },
                indent=2,
            )
        )
        return
    result = run_batch(
        args.request,
        args.primary_checkpoint,
        args.secondary_checkpoint,
        args.output,
        device=args.device,
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "sample_count": len(result["predictions"]),
                "output": str(args.output.resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
