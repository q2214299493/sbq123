#!/usr/bin/env python3
"""Extract compatible VASP force labels and calibrate AQCat25 force error."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, sha256_text
from scripts.execution_backends import load_execution_backends

def parse_poscar_symbols(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    symbols = lines[5].split()
    counts = [int(value) for value in lines[6].split()]
    if len(symbols) != len(counts):
        raise ValueError(f"{path}: symbol/count mismatch")
    return [symbol for symbol, count in zip(symbols, counts, strict=True) for _ in range(count)]


def parse_final_outcar(path: Path) -> dict[str, Any]:
    latest_forces: list[list[float]] | None = None
    latest_toten: float | None = None
    ionic_converged = False
    normal_completion = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        iterator = iter(handle)
        for line in iterator:
            if "reached required accuracy" in line:
                ionic_converged = True
            if "General timing and accounting informations" in line:
                normal_completion = True
            if "free  energy   TOTEN" in line:
                fields = line.split()
                try:
                    latest_toten = float(fields[4])
                except (IndexError, ValueError):
                    pass
            if "TOTAL-FORCE (eV/Angst)" not in line:
                continue
            next(iterator, None)
            block: list[list[float]] = []
            for force_line in iterator:
                stripped = force_line.strip()
                if not stripped or set(stripped) == {"-"}:
                    if block:
                        break
                    continue
                fields = stripped.split()
                if len(fields) < 6:
                    break
                try:
                    block.append([float(value) for value in fields[3:6]])
                except ValueError:
                    break
            if block:
                latest_forces = block
    if latest_forces is None:
        raise ValueError(f"{path}: no TOTAL-FORCE block")
    if latest_toten is None:
        raise ValueError(f"{path}: no TOTEN value")
    return {
        "ionic_converged": ionic_converged,
        "normal_completion": normal_completion,
        "final_toten_eV": latest_toten,
        "forces_eV_per_A": latest_forces,
    }


def extract_labels(samples: list[list[str]], fixed_count: int) -> dict[str, Any]:
    backend = load_execution_backends().vasp
    records: list[dict[str, Any]] = []
    for sample_id, family, directory_text in samples:
        directory = Path(directory_text).expanduser()
        structure_path = directory / "CONTCAR"
        outcar_path = directory / "OUTCAR"
        symbols = parse_poscar_symbols(structure_path)
        parsed = parse_final_outcar(outcar_path)
        if len(parsed["forces_eV_per_A"]) != len(symbols):
            raise ValueError(
                f"{sample_id}: OUTCAR/POSCAR atom-count mismatch "
                f"({len(parsed['forces_eV_per_A'])} forces, {len(symbols)} atoms)"
            )
        records.append(
            {
                "sample_id": sample_id,
                "family": family,
                "source_directory": str(directory),
                "structure_sha256": sha256_file(structure_path),
                "atom_order_sha256": sha256_text("\n".join(symbols) + "\n"),
                "symbols": symbols,
                "fixed_atom_indices_1based": list(range(1, fixed_count + 1)),
                **parsed,
            }
        )
    return {
        "calibration_id": "aqcat25_fe45_v1",
        "source_backend": backend.server_alias,
        "compatibility_branch": "true_fe110_5layer_5x5x1",
        "samples": records,
    }


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate percentile of an empty sequence")
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def calibrate(labels: dict[str, Any], predictions: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    predicted_by_id = {item["sample_id"]: item for item in predictions["samples"]}
    sample_results: list[dict[str, Any]] = []
    all_component_errors: list[float] = []
    all_vector_errors: list[float] = []
    families: set[str] = set()
    scope_failures: list[str] = []
    scope = gate["reference_scope"]
    for label in labels["samples"]:
        sample_id = label["sample_id"]
        prediction = predicted_by_id.get(sample_id)
        if prediction is None:
            raise ValueError(f"missing AQCat25 prediction for {sample_id}")
        if prediction["structure_sha256"] != label["structure_sha256"]:
            raise ValueError(f"structure hash mismatch for {sample_id}")
        reference_forces = label["forces_eV_per_A"]
        predicted_forces = prediction["forces_eV_per_A"]
        if len(reference_forces) != len(predicted_forces):
            raise ValueError(f"force-count mismatch for {sample_id}")
        fixed = set(label["fixed_atom_indices_1based"])
        movable = [index for index in range(len(reference_forces)) if index + 1 not in fixed]
        component_errors = [
            abs(predicted_forces[index][axis] - reference_forces[index][axis])
            for index in movable
            for axis in range(3)
        ]
        vector_errors = [
            math.sqrt(sum((predicted_forces[index][axis] - reference_forces[index][axis]) ** 2 for axis in range(3)))
            for index in movable
        ]
        all_component_errors.extend(component_errors)
        all_vector_errors.extend(vector_errors)
        families.add(label["family"])
        symbols = label["symbols"]
        if symbols.count("Fe") != scope["required_fe_count"]:
            scope_failures.append(f"{sample_id}: Fe count {symbols.count('Fe')}")
        if not set(symbols) <= set(scope["allowed_elements"]):
            scope_failures.append(f"{sample_id}: unsupported element")
        adsorbate_count = len(symbols) - symbols.count("Fe")
        lower, upper = scope["adsorbate_atom_count_range"]
        if not lower <= adsorbate_count <= upper:
            scope_failures.append(f"{sample_id}: adsorbate atom count {adsorbate_count}")
        sample_results.append(
            {
                "sample_id": sample_id,
                "family": label["family"],
                "structure_sha256": label["structure_sha256"],
                "component_mae_eV_per_A": fmean(component_errors),
                "vector_rmse_eV_per_A": math.sqrt(fmean(value * value for value in vector_errors)),
                "vector_max_eV_per_A": max(vector_errors),
                "aqcat_predicted_energy_eV_non_dft": prediction["predicted_energy_eV"],
            }
        )

    missing_families = sorted(set(scope["required_families"]) - families)
    if missing_families:
        scope_failures.append(f"missing families: {', '.join(missing_families)}")
    if len(sample_results) < scope["minimum_total_samples"]:
        scope_failures.append(f"only {len(sample_results)} samples")
    metrics = {
        "sample_count": len(sample_results),
        "force_component_count": len(all_component_errors),
        "component_mae_eV_per_A": fmean(all_component_errors),
        "vector_rmse_eV_per_A": math.sqrt(fmean(value * value for value in all_vector_errors)),
        "vector_p95_eV_per_A": percentile(all_vector_errors, 95.0),
        "vector_max_eV_per_A": max(all_vector_errors),
    }
    thresholds = gate["force_acceptance"]
    threshold_checks = {
        "component_mae": metrics["component_mae_eV_per_A"] <= thresholds["component_mae_eV_per_A_max"],
        "vector_rmse": metrics["vector_rmse_eV_per_A"] <= thresholds["vector_rmse_eV_per_A_max"],
        "vector_p95": metrics["vector_p95_eV_per_A"] <= thresholds["vector_p95_eV_per_A_max"],
        "vector_max": metrics["vector_max_eV_per_A"] <= thresholds["vector_max_eV_per_A_max"],
    }
    if scope_failures:
        status = "out_of_domain"
    elif not all(threshold_checks.values()):
        status = "calibration_failed"
    else:
        status = "in_domain"
    return {
        "calibration_id": labels["calibration_id"],
        "checkpoint_sha256": predictions["checkpoint_sha256"],
        "status": status,
        "uncertainty_method": "empirical force error on compatible VASP final-force labels; no per-candidate uncertainty from one checkpoint",
        "reference_scope": scope,
        "scope_failures": scope_failures,
        "metrics": metrics,
        "thresholds": thresholds,
        "threshold_checks": threshold_checks,
        "samples": sample_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract")
    extract.add_argument("--sample", nargs=3, action="append", required=True, metavar=("ID", "FAMILY", "DIRECTORY"))
    extract.add_argument("--fixed-count", type=int, default=18)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--labels", type=Path, required=True)
    evaluate.add_argument("--predictions", type=Path, required=True)
    evaluate.add_argument("--gate", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "extract":
        result = extract_labels(args.sample, args.fixed_count)
    else:
        import yaml

        labels = load_json_object(args.labels)
        predictions = load_json_object(args.predictions)
        gate = yaml.safe_load(args.gate.read_text(encoding="utf-8"))
        result = calibrate(labels, predictions, gate)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
