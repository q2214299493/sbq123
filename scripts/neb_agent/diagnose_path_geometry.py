from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from scripts.artifact_io import source_file_manifest

from .cli_common import comma_tokens
from .utils_report import write_json
from .utils_structure import (
    Poscar,
    compatible,
    max_neighbor_step,
    minimum_image_delta,
    minimum_pair_distance,
    numbered_image_dirs,
    pbc_distance,
    read_poscar,
)


ROOT = Path(__file__).resolve().parents[2]
COVALENT_RADII_A = {
    "H": 0.31,
    "C": 0.76,
    "N": 0.71,
    "O": 0.66,
    "Fe": 1.32,
}


def _reaction_indices(labels: list[str], tokens: list[str]) -> tuple[list[int], list[str]]:
    indices: list[int] = []
    errors: list[str] = []
    for token in tokens:
        if not str(token).isdigit():
            errors.append(f"reaction_atom_must_be_numeric:{token}")
            continue
        index = int(token)
        if 0 <= index < len(labels):
            indices.append(index)
        else:
            errors.append(f"reaction_atom_out_of_range:{token}")
    if not indices:
        errors.append("explicit_reaction_atoms_required")
    return sorted(set(indices)), errors


def _incar_images(path: Path) -> int | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0]
        if "=" not in clean:
            continue
        key, value = (part.strip() for part in clean.split("=", 1))
        if key.upper() == "IMAGES":
            try:
                return int(value.split()[0])
            except ValueError:
                return None
    return None


def _expected_interior(workdir: Path, explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    report = workdir / "path_generation_report.json"
    if report.is_file():
        try:
            return int(json.loads(report.read_text(encoding="utf-8"))["interior_images"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
    return _incar_images(workdir / "INCAR")


def _load_images(workdir: Path, expected_interior: int | None) -> tuple[list[Path], list[Path], list[Poscar], list[str]]:
    directories = numbered_image_dirs(workdir)
    used_directories: list[Path] = []
    errors: list[str] = []
    if directories:
        highest = expected_interior + 1 if expected_interior is not None else max(int(path.name) for path in directories)
        expected = [f"{index:02d}" for index in range(highest + 1)]
        actual = [path.name for path in directories]
        if actual != expected:
            errors.append("nonconsecutive_or_incomplete_image_directories")
    used_files: list[Path] = []
    structures: list[Poscar] = []
    for directory in directories:
        candidate = directory / "CONTCAR"
        if not candidate.is_file() or candidate.stat().st_size == 0:
            candidate = directory / "POSCAR"
        if not candidate.is_file() or candidate.stat().st_size == 0:
            errors.append(f"image_{directory.name}:structure_missing")
            continue
        used_directories.append(directory)
        used_files.append(candidate)
        structures.append(read_poscar(candidate))
    if len(used_files) != len(directories):
        errors.append("one_or_more_image_structures_missing")
    return used_directories, used_files, structures, errors


def _fixed_atom_indices(structure: Poscar, tokens: list[str]) -> tuple[list[int], list[str]]:
    if tokens:
        fixed, errors = _reaction_indices(structure.labels, tokens)
        return fixed, [error.replace("reaction_atom", "fixed_atom") for error in errors]
    if not structure.selective:
        return [], ["selective_dynamics_required_for_slab_path"]
    return (
        [index for index, flags in enumerate(structure.flags) if flags and all(value == "F" for value in flags)],
        [],
    )


def _reaction_distances(structure: Poscar, pairs: list[list[int]]) -> list[dict[str, Any]]:
    labels = structure.labels
    return [
        {
            "atoms_zero_based": [left, right],
            "labels": [labels[left], labels[right]],
            "distance_A": pbc_distance(structure, left, right),
        }
        for left, right in pairs
    ]


def _collision(structure: Poscar, factor: float, cap_a: float) -> tuple[float, tuple[int, int], float, bool]:
    minimum, minimum_pair = minimum_pair_distance(structure)
    worst_ratio = float("inf")
    worst_pair = minimum_pair
    worst_threshold = 0.0
    collision = False
    labels = structure.labels
    for right in range(structure.atom_count):
        for left in range(right):
            distance = pbc_distance(structure, left, right)
            radii = COVALENT_RADII_A.get(labels[left]), COVALENT_RADII_A.get(labels[right])
            threshold = min(cap_a, factor * sum(radii)) if all(value is not None for value in radii) else cap_a
            ratio = distance / max(threshold, 1e-12)
            if ratio < worst_ratio:
                worst_ratio, worst_pair, worst_threshold = ratio, (left, right), threshold
            collision = collision or distance < threshold
    return minimum, worst_pair, worst_threshold, collision


def _surface_warnings(
    structure: Poscar,
    reaction: list[int],
    initial_heights: dict[int, float],
    penetration_buffer_a: float,
    desorption_change_a: float,
) -> list[str]:
    cart = structure.frac @ structure.cell
    fe_indices = [index for index, label in enumerate(structure.labels) if label == "Fe"]
    if not fe_indices:
        return []
    top = max(float(cart[index, 2]) for index in fe_indices)
    warnings: list[str] = []
    for index in reaction:
        if structure.labels[index] == "Fe":
            continue
        height = float(cart[index, 2] - top)
        if height < -penetration_buffer_a:
            warnings.append(f"reaction_atom_{index}:surface_penetration_{height:.3f}_A")
        if height - initial_heights.get(index, height) > desorption_change_a:
            warnings.append(
                f"reaction_atom_{index}:desorption_height_change_"
                f"{height - initial_heights[index]:.3f}_A"
            )
    return warnings


def _measure_images(
    directories: list[Path],
    files: list[Path],
    structures: list[Poscar],
    reaction: list[int],
    reaction_pairs: list[list[int]],
    fixed: list[int],
    thresholds: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    first = structures[0]
    first_cart = first.frac @ first.cell
    fe = [index for index, label in enumerate(first.labels) if label == "Fe"]
    top = max((float(first_cart[index, 2]) for index in fe), default=0.0)
    initial_heights = {index: float(first_cart[index, 2] - top) for index in reaction}
    for image_index, structure in enumerate(structures):
        image = directories[image_index].name
        for error in compatible(first, structure):
            errors.append(f"image_{image}:{error}")
        minimum, pair, collision_threshold, collision = _collision(
            structure,
            float(thresholds["min_distance_factor"]),
            float(thresholds["absolute_min_distance_A"]),
        )
        jump = 0.0 if image_index == 0 else max_neighbor_step(structures[image_index - 1], structure)
        fixed_move = 0.0 if image_index == 0 or not fixed else max_neighbor_step(first, structure, fixed)
        raw_step = 0.0
        branch_shift_atoms: list[int] = []
        if image_index:
            previous = structures[image_index - 1]
            raw_delta = structure.frac - previous.frac
            minimum_delta = minimum_image_delta(previous.frac, structure.frac)
            raw_step = float(np.max(np.abs(raw_delta)))
            branch_shift_atoms = np.flatnonzero(
                np.any(np.abs(raw_delta - minimum_delta) > 1e-8, axis=1)
            ).tolist()
        fixed_raw_move = (
            0.0
            if not fixed
            else float(np.max(np.abs(structure.frac[fixed] - first.frac[fixed])))
        )
        rows.append(
            {
                "image": image,
                "source": str(files[image_index]),
                "minimum_pair_distance_A": minimum,
                "minimum_pair_zero_based": list(pair),
                "collision_threshold_A": collision_threshold,
                "max_step_from_previous_A": jump,
                "max_raw_fractional_step_from_previous": raw_step,
                "periodic_branch_shift_atom_indices_zero_based": branch_shift_atoms,
                "max_fixed_displacement_from_initial_A": fixed_move,
                "max_fixed_raw_fractional_displacement_from_initial": fixed_raw_move,
                "reaction_distances": _reaction_distances(structure, reaction_pairs),
            }
        )
        if collision:
            errors.append(f"image_{image}:unphysical_contact_pair_{pair[0]}_{pair[1]}")
        if image_index and jump > float(thresholds["image_jump_warning_A"]):
            warnings.append(f"image_{image}:path_jump_{jump:.3f}_A")
        if branch_shift_atoms:
            atoms = ",".join(str(index) for index in branch_shift_atoms)
            errors.append(
                f"image_{image}:raw_periodic_branch_discontinuity_atoms_{atoms}"
            )
        if fixed_move > float(thresholds["fixed_position_tolerance_A"]):
            errors.append(f"image_{image}:fixed_atom_moved_{fixed_move:.6f}_A")
        if fixed_raw_move > 1e-10:
            errors.append(
                f"image_{image}:fixed_atom_raw_coordinate_mismatch_"
                f"{fixed_raw_move:.12f}"
            )
        warnings.extend(
            f"image_{image}:{error}"
            for error in _surface_warnings(
                structure,
                reaction,
                initial_heights,
                float(thresholds["surface_penetration_warning_A"]),
                float(thresholds["desorption_height_change_warning_A"]),
            )
        )
    return rows, errors, warnings


def _coordinate_backtrack_warning(
    rows: list[dict[str, Any]],
    threshold_a: float,
) -> str | None:
    if not rows or len(rows[0]["reaction_distances"]) != 1:
        return None
    coordinate = [row["reaction_distances"][0]["distance_A"] for row in rows]
    endpoint_change = coordinate[-1] - coordinate[0]
    if abs(endpoint_change) <= 0.5:
        return None
    direction = 1 if endpoint_change > 0 else -1
    signed_steps = [(right - left) * direction for left, right in zip(coordinate, coordinate[1:])]
    backtrack = min(signed_steps, default=0.0)
    return (
        f"reaction_coordinate_backtrack_{abs(backtrack):.3f}_A"
        if backtrack < -threshold_a
        else None
    )


def _write_diagnosis(workdir: Path, payload: dict[str, Any]) -> None:
    write_json(workdir / "path_geometry_diagnosis.json", payload)


def diagnose(
    workdir: Path,
    reaction_atoms: list[str],
    fixed_indices: list[str],
    thresholds_path: Path,
    *,
    reaction_pairs: list[list[int]] | None = None,
    expected_interior: int | None = None,
) -> dict[str, Any]:
    thresholds = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    directories, used_files, structures, errors = _load_images(workdir, _expected_interior(workdir, expected_interior))
    if len(structures) < 2:
        return {"status": "STOP", "errors": sorted(set([*errors, "fewer_than_two_images"])), "warnings": [], "images": []}

    reaction, reaction_errors = _reaction_indices(structures[0].labels, reaction_atoms)
    fixed, fixed_errors = _fixed_atom_indices(structures[0], fixed_indices)
    errors.extend(reaction_errors)
    errors.extend(fixed_errors)
    pairs = reaction_pairs or ([reaction] if len(reaction) == 2 else [])
    if any(len(pair) != 2 or min(pair) < 0 or max(pair) >= structures[0].atom_count for pair in pairs):
        errors.append("reaction_pair_out_of_range")
        pairs = []
    rows, measured_errors, measured_warnings = _measure_images(
        directories,
        used_files,
        structures,
        reaction,
        pairs,
        fixed,
        thresholds,
    )
    errors.extend(measured_errors)
    backtrack_warning = _coordinate_backtrack_warning(
        rows,
        float(thresholds["reaction_coordinate_backtrack_warning_A"]),
    )
    if backtrack_warning:
        measured_warnings.append(backtrack_warning)
    status = "STOP" if errors else "REVIEW" if measured_warnings else "PASS"
    payload = {
        "schema_version": 1,
        "document_kind": "neb_path_geometry_diagnosis",
        "producer": "scripts.neb_agent.diagnose_path_geometry",
        "source_files": source_file_manifest(
            [workdir / "INCAR", thresholds_path, *used_files]
        ),
        "status": status,
        "errors": sorted(set(errors)),
        "warnings": sorted(
            set([*measured_warnings, "nebmovie.pl visual review remains required"])
        ),
        "thresholds": thresholds,
        "reaction_atom_indices_zero_based": reaction,
        "reaction_pairs_zero_based": pairs,
        "fixed_atom_indices_zero_based": fixed,
        "images": rows,
        "requires_visual_review": True,
    }
    _write_diagnosis(workdir, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose complete NEB path continuity and geometry without changing structures.")
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--reaction-atoms", required=True)
    parser.add_argument("--reaction-pair", action="append", default=[])
    parser.add_argument("--fixed-indices", default="")
    parser.add_argument("--expected-interior", type=int)
    parser.add_argument("--thresholds", type=Path, default=ROOT / "configs" / "neb_agent" / "default_thresholds.yaml")
    args = parser.parse_args()
    pairs = [[int(value) for value in token.split(":", 1)] for token in args.reaction_pair]
    payload = diagnose(
        args.workdir,
        comma_tokens(args.reaction_atoms),
        comma_tokens(args.fixed_indices),
        args.thresholds,
        reaction_pairs=pairs,
        expected_interior=args.expected_interior,
    )
    print(payload["status"])
    if payload["status"] == "STOP":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
