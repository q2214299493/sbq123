from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .cli_common import add_common_arguments, require_paths
from .utils_report import write_json
from .utils_structure import (
    Poscar,
    compatible,
    copy_with_frac,
    max_neighbor_step,
    minimum_image_delta,
    read_poscar,
    write_poscar,
    write_xyz,
)
from scripts.ts_strategy_engine.execution_gate import require_action


def _ase_idpp(start: Poscar, end: Poscar, interior_count: int) -> list[Poscar]:
    if interior_count == 0:
        return [
            copy_with_frac(start, start.frac, start.comment),
            copy_with_frac(start, end.frac, end.comment),
        ]
    try:
        from ase import Atoms
        from ase.constraints import FixAtoms
        from ase.mep import NEB
    except ImportError as exc:
        raise RuntimeError('ASE is required for IDPP path generation; install with: pip install ".[neb]"') from exc

    first = Atoms(start.labels, cell=start.cell, pbc=True, scaled_positions=start.frac)
    last = Atoms(end.labels, cell=end.cell, pbc=True, scaled_positions=end.frac)
    images = [first]
    images.extend(first.copy() for _ in range(interior_count))
    images.append(last)
    fixed = [
        index
        for index, flags in enumerate(start.flags)
        if start.selective and flags and all(value == "F" for value in flags)
    ]
    if fixed:
        for image in images:
            image.set_constraint(FixAtoms(indices=fixed))
    neb = NEB(images, method="improvedtangent")
    neb.interpolate(method="idpp", mic=True, apply_constraint=True)
    structures = [copy_with_frac(start, atoms.get_scaled_positions(wrap=False), f"IDPP image {i}") for i, atoms in enumerate(images)]
    if fixed:
        for structure in structures:
            structure.frac[fixed] = start.frac[fixed]
    return structures


def _allocate_segment_images(points: list[Poscar], interior_count: int) -> list[int]:
    waypoint_count = len(points) - 2
    if interior_count < waypoint_count:
        raise ValueError("interior image count is smaller than the number of reviewed waypoints")
    remaining = interior_count - waypoint_count
    weights = [max(1e-12, max_neighbor_step(points[index], points[index + 1])) for index in range(len(points) - 1)]
    total = sum(weights)
    raw = [remaining * weight / total for weight in weights]
    allocated = [int(value) for value in raw]
    for index in sorted(range(len(raw)), key=lambda item: raw[item] - allocated[item], reverse=True)[: remaining - sum(allocated)]:
        allocated[index] += 1
    return allocated


def _segmented_idpp(points: list[Poscar], interior_count: int) -> tuple[list[Poscar], list[int]]:
    allocations = _allocate_segment_images(points, interior_count)
    structures: list[Poscar] = []
    for index, count in enumerate(allocations):
        segment = _ase_idpp(points[index], points[index + 1], count)
        structures.extend(segment if not structures else segment[1:])
    return structures, allocations


def _continuous_periodic_branch(structures: list[Poscar]) -> list[Poscar]:
    if not structures:
        return []
    first = structures[0]
    fixed = [
        index
        for index, flags in enumerate(first.flags)
        if first.selective and flags and all(value == "F" for value in flags)
    ]
    continuous = [
        copy_with_frac(first, first.frac, first.comment)
    ]
    for structure in structures[1:]:
        previous = continuous[-1]
        frac = previous.frac + minimum_image_delta(previous.frac, structure.frac)
        if fixed:
            frac[fixed] = first.frac[fixed]
        continuous.append(copy_with_frac(structure, frac, structure.comment))
    return continuous


def _periodic_branch_metrics(structures: list[Poscar]) -> dict[str, object]:
    if len(structures) < 2:
        return {
            "method": "sequential_minimum_image_unwrap",
            "max_raw_fractional_step": 0.0,
            "max_raw_cartesian_step_A": 0.0,
            "fixed_atoms_exactly_preserved": True,
        }
    first = structures[0]
    fixed = [
        index
        for index, flags in enumerate(first.flags)
        if first.selective and flags and all(value == "F" for value in flags)
    ]
    raw_deltas = [
        right.frac - left.frac
        for left, right in zip(structures, structures[1:])
    ]
    return {
        "method": "sequential_minimum_image_unwrap",
        "max_raw_fractional_step": max(
            float(np.max(np.abs(delta))) for delta in raw_deltas
        ),
        "max_raw_cartesian_step_A": max(
            float(np.max(np.linalg.norm(delta @ first.cell, axis=1)))
            for delta in raw_deltas
        ),
        "fixed_atoms_exactly_preserved": all(
            np.array_equal(structure.frac[fixed], first.frac[fixed])
            for structure in structures
        )
        if fixed
        else True,
    }


def _constraint_midpoint(start: Poscar, end: Poscar, constraints: dict) -> tuple[Poscar | None, list[str]]:
    warnings: list[str] = []
    reaction = constraints.get("reaction_coordinate") or {}
    bond = reaction.get("breaking_bond") or reaction.get("bond")
    target = reaction.get("target_distance_A") or reaction.get("midpoint_distance_A")
    breaking_bonds = reaction.get("breaking_bonds") or []
    if breaking_bonds and isinstance(breaking_bonds[0], dict):
        bond_record = breaking_bonds[0]
        bond = bond_record.get("atoms") or bond
        target = bond_record.get("target_ts_distance_A") or bond_record.get("target_distance_A") or target
    if not isinstance(bond, (list, tuple)) or len(bond) != 2 or target is None:
        return None, ["Retrieval prior has no executable breaking-bond indices and target distance; used ordinary IDPP."]
    try:
        i, j = (int(bond[0]), int(bond[1]))
        target = float(target)
    except (TypeError, ValueError):
        return None, ["Retrieved bond constraint is malformed; used ordinary IDPP."]
    if constraints.get("index_base", reaction.get("index_base", 0)) == 1:
        i -= 1
        j -= 1
    if min(i, j) < 0 or max(i, j) >= start.atom_count or i == j or target <= 0:
        return None, ["Retrieved bond constraint is outside the endpoint atom map; used ordinary IDPP."]

    delta = minimum_image_delta(start.frac, end.frac)
    frac = start.frac + 0.5 * delta
    cart = frac @ start.cell
    vector = cart[j] - cart[i]
    vector -= np.round(vector @ np.linalg.inv(start.cell)) @ start.cell
    norm = float(np.linalg.norm(vector))
    if norm < 1e-8:
        return None, ["Constrained bond direction is undefined; used ordinary IDPP."]
    center = cart[i] + 0.5 * vector
    unit = vector / norm
    cart[i] = center - 0.5 * target * unit
    cart[j] = center + 0.5 * target * unit
    midpoint = copy_with_frac(start, cart @ np.linalg.inv(start.cell), "Retrieval-constrained IDPP midpoint")
    warnings.append(f"Applied reviewable bond constraint to atoms {i},{j}: {target:.3f} A.")
    return midpoint, warnings


def _stop(method: str, errors: list[str], warnings: list[str] | None = None) -> dict:
    return {"status": "STOP", "errors": errors, "warnings": warnings or [], "method_requested": method}


def _load_constraints(path: Path | None) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else {}


def _select_waypoints(
    initial: Poscar,
    final: Poscar,
    method: str,
    constraints: dict,
    waypoint_paths: list[Path],
) -> tuple[str, list[Poscar], list[str], list[str]]:
    selected = str(constraints.get("recommended_path_method", "idpp")) if method == "auto" else method
    if waypoint_paths:
        waypoints = [read_poscar(path) for path in waypoint_paths]
        errors = [
            f"waypoint_{index}:{value}"
            for index, waypoint in enumerate(waypoints)
            for value in compatible(initial, waypoint)
        ]
        return "segmented_idpp", waypoints, [], errors
    if selected not in {"segmented_idpp", "constrained_idpp"}:
        return selected, [], [], []
    if constraints.get("review_status") != "accepted":
        return selected, [], [], ["reviewed executable waypoint or accepted retrieval constraint is required"]
    midpoint, warnings = _constraint_midpoint(initial, final, constraints)
    return (selected, [midpoint], warnings, []) if midpoint else (selected, [], warnings, ["no executable waypoint"])


def _write_path(output_dir: Path, structures: list[Poscar]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, structure in enumerate(structures):
        write_poscar(output_dir / f"{index:02d}" / "POSCAR", structure)
    write_xyz(output_dir / "neb_path.xyz", structures)


def generate_path(
    initial_path: Path,
    final_path: Path,
    output_dir: Path,
    images: int,
    method: str,
    constraints_path: Path | None,
    waypoint_paths: list[Path] | None,
    *,
    rebuild: bool = False,
    gate_decision: Path | None = None,
    gate_state_sha256: str | None = None,
) -> dict:
    if rebuild:
        if gate_decision is None or gate_state_sha256 is None:
            return _stop(method, ["REBUILD_PATH requires a current authoritative gate decision"])
        try:
            require_action(gate_decision, "REBUILD_PATH", gate_state_sha256)
        except (OSError, ValueError, PermissionError) as exc:
            return _stop(method, [str(exc)])
    initial = read_poscar(initial_path)
    final = read_poscar(final_path)
    errors = compatible(initial, final)
    if errors:
        return _stop(method, errors)
    if images < 1:
        return _stop(method, ["images_must_be_positive"])
    existing = [output_dir / f"{i:02d}" for i in range(images + 2) if (output_dir / f"{i:02d}").exists()]
    if existing:
        return _stop(
            method, ["numbered_image_directories_already_exist"], ["Use a new output directory; existing paths are never overwritten."]
        )

    constraints = _load_constraints(constraints_path)
    selected, waypoints, warnings, waypoint_errors = _select_waypoints(
        initial, final, method, constraints, waypoint_paths or []
    )
    if waypoint_errors:
        return _stop(method, waypoint_errors, warnings)

    try:
        if waypoints:
            structures, segment_allocations = _segmented_idpp([initial, *waypoints, final], images)
        else:
            structures = _ase_idpp(initial, final, images)
            segment_allocations = [images]
    except (RuntimeError, ValueError) as exc:
        return _stop(method, [str(exc)], warnings)

    structures[0] = copy_with_frac(initial, initial.frac, initial.comment)
    structures[-1] = copy_with_frac(initial, final.frac, final.comment)
    structures = _continuous_periodic_branch(structures)
    _write_path(output_dir, structures)
    payload = {
        "status": "READY_FOR_GEOMETRY_REVIEW",
        "method_requested": method,
        "method_used": selected,
        "interior_images": images,
        "image_directories": [f"{i:02d}" for i in range(images + 2)],
        "constraints_source": str(constraints_path) if constraints_path else None,
        "waypoint_sources": [str(path) for path in waypoint_paths or []],
        "segment_additional_images": segment_allocations,
        "periodic_branch": _periodic_branch_metrics(structures),
        "warnings": warnings,
        "requires_human_review": True,
    }
    write_json(output_dir / "path_generation_report.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a non-linear NEB path with ASE IDPP and optional reviewed midpoint constraints.")
    add_common_arguments(parser)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--method", choices=("auto", "idpp", "segmented_idpp", "constrained_idpp"), default="auto")
    parser.add_argument("--constraints", type=Path)
    parser.add_argument("--waypoint", type=Path, action="append", default=[])
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--gate-decision", type=Path)
    parser.add_argument("--gate-state-sha256")
    args = parser.parse_args()
    require_paths(args, "initial", "final")
    output_dir = args.output_dir or args.workdir / "path_candidate"
    payload = generate_path(
        args.initial,
        args.final,
        output_dir,
        args.images,
        args.method,
        args.constraints,
        args.waypoint,
        rebuild=args.rebuild,
        gate_decision=args.gate_decision,
        gate_state_sha256=args.gate_state_sha256,
    )
    print(payload["status"])
    if payload["status"] == "STOP":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
