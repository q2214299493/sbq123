from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts.ts_strategy_engine.contract import load_contract

from .utils_report import write_json
from .utils_structure import compatible, displacement_cart, read_poscar


def check_endpoints(
    initial_path: Path,
    final_path: Path,
    contract: dict[str, Any],
    *,
    mapped_displacement_warning_a: float = 3.0,
    fixed_position_tolerance_a: float = 1e-4,
) -> dict[str, Any]:
    initial = read_poscar(initial_path)
    final = read_poscar(final_path)
    errors = compatible(initial, final)
    warnings: list[str] = []
    labels_initial = initial.labels
    labels_final = final.labels
    atom_map = contract["atom_map"]
    initial_indices = [pair["is"] for pair in atom_map]
    final_indices = [pair["fs"] for pair in atom_map]
    expected = list(range(initial.atom_count))
    if sorted(initial_indices) != expected or sorted(final_indices) != expected:
        errors.append("atom_map_must_cover_each_endpoint_atom_exactly_once")

    displacements: list[float] = []
    mapped_rows: list[dict[str, Any]] = []
    for pair in atom_map:
        left, right = pair["is"], pair["fs"]
        if left >= initial.atom_count or right >= final.atom_count:
            errors.append("atom_map_index_out_of_range")
            continue
        if labels_initial[left] != labels_final[right]:
            errors.append(f"atom_map_element_mismatch:{left}->{right}")
            continue
        if left != right:
            errors.append(f"non_identity_atom_map_requires_endpoint_reorder:{left}->{right}")
        vector = displacement_cart(initial, initial.frac[left], final.frac[right])
        distance = float((vector @ vector) ** 0.5)
        displacements.append(distance)
        mapped_rows.append(
            {"index_zero_based": left, "final_index_zero_based": right, "label": labels_initial[left], "distance_A": distance}
        )

    fixed = [
        index
        for index, flags in enumerate(initial.flags)
        if initial.selective and flags and all(value == "F" for value in flags)
    ]
    for index in fixed:
        distance = float(
            (
                displacement_cart(initial, initial.frac[index], final.frac[index])
                @ displacement_cart(initial, initial.frac[index], final.frac[index])
            )
            ** 0.5
        )
        if distance > fixed_position_tolerance_a:
            errors.append(f"fixed_atom_coordinate_mismatch:{index}:{distance:.6f}_A")
    if displacements and max(displacements) > mapped_displacement_warning_a:
        warnings.append(
            f"mapped_displacement_exceeds_{mapped_displacement_warning_a:g}_A"
        )
    if any(index >= initial.atom_count for index in contract["reaction_atoms"]):
        errors.append("reaction_atom_index_out_of_range")

    moving = sorted(mapped_rows, key=lambda item: item["distance_A"], reverse=True)[:10]
    unique_errors = sorted(set(errors))
    unique_warnings = sorted(set(warnings))
    return {
        "status": "STOP" if unique_errors else "REVIEW" if unique_warnings else "PASS",
        "initial": str(initial_path),
        "final": str(final_path),
        "atom_count": initial.atom_count,
        "symbols": initial.symbols,
        "counts": initial.counts,
        "selective_dynamics": initial.selective,
        "atom_map_sha256": contract["atom_map_sha256"],
        "reaction_atom_indices_zero_based": contract["reaction_atoms"],
        "broken_bonds_zero_based": contract["broken_bonds"],
        "formed_bonds_zero_based": contract["formed_bonds"],
        "fixed_atom_indices_zero_based": fixed,
        "errors": unique_errors,
        "warnings": unique_warnings,
        "max_minimum_image_displacement_A": max(displacements, default=0.0),
        "largest_displacements": moving,
        "elementary_step_assessment": (
            "invalid"
            if unique_errors
            else "mapped_contract_valid_needs_review"
            if unique_warnings
            else "mapped_contract_valid"
        ),
    }


def write_report(workdir: Path, payload: dict[str, Any]) -> None:
    write_json(workdir / "endpoint_check.json", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate mapped NEB endpoint compatibility without modifying endpoints.")
    parser.add_argument("--is", dest="initial", type=Path, required=True)
    parser.add_argument("--fs", dest="final", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args()
    payload = check_endpoints(args.initial, args.final, load_contract(args.contract))
    write_report(args.workdir, payload)
    print(payload["status"])
    if payload["status"] == "STOP":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
