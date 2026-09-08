#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path
from statistics import fmean

import numpy as np
import yaml
from ase.db import connect

try:
    from scripts.artifact_io import sha256_file, write_json_atomic
except ModuleNotFoundError:  # Standalone deployment on MZ73.
    from artifact_io import sha256_file, write_json_atomic


def _fixed_indices(atoms) -> set[int]:
    fixed: set[int] = set()
    for constraint in atoms.constraints:
        getter = getattr(constraint, "get_indices", None)
        if getter is not None:
            fixed.update(int(value) for value in getter())
    return fixed


def validate_checkpoint(checkpoint: Path, database: Path, thresholds_path: Path, output: Path) -> dict:
    from fairchem.core.common.relaxation.ase_utils import patched_calc

    gate = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    thresholds = gate["force_acceptance"]
    calculator = patched_calc(checkpoint_path=str(checkpoint), is_spin_off=False, is_low_fi=False)
    component_errors: list[float] = []
    vector_errors: list[float] = []
    samples: list[dict] = []
    database_handle = connect(database)
    for row in database_handle.select():
        atoms = row.toatoms()
        reference = np.asarray(atoms.get_forces(), dtype=float)
        fixed = _fixed_indices(atoms)
        atoms.calc = calculator
        energy = float(atoms.get_potential_energy())
        predicted = np.asarray(atoms.get_forces(), dtype=float)
        if not np.isfinite(energy) or predicted.shape != reference.shape or not np.isfinite(predicted).all():
            raise RuntimeError(f"checkpoint returned invalid prediction for {row.id}")
        movable = [index for index in range(len(atoms)) if index not in fixed]
        if not movable:
            raise RuntimeError(f"validation sample has no movable atoms: {row.id}")
        delta = predicted[movable] - reference[movable]
        components = np.abs(delta).reshape(-1).tolist()
        vectors = np.linalg.norm(delta, axis=1).tolist()
        component_errors.extend(components)
        vector_errors.extend(vectors)
        samples.append(
            {
                "sample_id": row.data.get("sid", str(row.id)),
                "component_mae_eV_per_A": fmean(components),
                "vector_rmse_eV_per_A": math.sqrt(fmean(value * value for value in vectors)),
                "vector_max_eV_per_A": max(vectors),
                "predicted_energy_eV_non_dft": energy,
            }
        )
    if not samples:
        raise RuntimeError("checkpoint validation database is empty")
    ordered = sorted(vector_errors)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    metrics = {
        "sample_count": len(samples),
        "component_mae_eV_per_A": fmean(component_errors),
        "vector_rmse_eV_per_A": math.sqrt(fmean(value * value for value in vector_errors)),
        "vector_p95_eV_per_A": p95,
        "vector_max_eV_per_A": max(vector_errors),
    }
    checks = {
        "component_mae": metrics["component_mae_eV_per_A"] <= float(thresholds["component_mae_eV_per_A_max"]),
        "vector_rmse": metrics["vector_rmse_eV_per_A"] <= float(thresholds["vector_rmse_eV_per_A_max"]),
        "vector_p95": metrics["vector_p95_eV_per_A"] <= float(thresholds["vector_p95_eV_per_A_max"]),
        "vector_max": metrics["vector_max_eV_per_A"] <= float(thresholds["vector_max_eV_per_A_max"]),
    }
    payload = {
        "schema_version": 1,
        "document_kind": "aqcat25_finetuned_checkpoint_validation",
        "status": "passed" if all(checks.values()) else "failed",
        "checkpoint_sha256": sha256_file(checkpoint),
        "validation_database_sha256": sha256_file(database),
        "thresholds_sha256": sha256_file(thresholds_path),
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "samples": samples,
        "scope": "held_out_adsorption_regression_and_checkpoint_load_only_not_ts_domain",
        "reportable_final_energy": False,
    }
    write_json_atomic(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Load and regression-check one fine-tuned AQCat25 checkpoint.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate_checkpoint(args.checkpoint, args.database, args.thresholds, args.output)
    if result["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
