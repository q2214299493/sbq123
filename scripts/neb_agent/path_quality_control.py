from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

import numpy as np
from ase.io import read as ase_read

from scripts.neb_agent.utils_structure import (
    compatible,
    displacement_cart,
    numbered_image_dirs,
    pbc_distance,
    preferred_image_structure,
    read_poscar,
)
from scripts.neb_agent.utils_vasp import (
    parse_oszicar,
    parse_outcar,
    trailing_threshold_count,
)


def quality_source_paths(workdir: Path, extras: list[Path]) -> list[Path]:
    paths = [*extras]
    for directory in numbered_image_dirs(workdir):
        paths.extend(
            directory / name
            for name in ("POSCAR", "CONTCAR", "OSZICAR", "OUTCAR", "XDATCAR")
        )
    return paths


def _median_positive(values: list[float]) -> float:
    positive = [value for value in values if value > 1e-12]
    return statistics.median(positive) if positive else 0.0


def _decreasing(values: list[float]) -> bool:
    return len(values) >= 3 and statistics.fmean(values[-3:]) < statistics.fmean(values[:3])


def _current_pair_metrics(structures: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for left, right in zip(structures, structures[1:], strict=False):
        displacements = [
            float(np.linalg.norm(displacement_cart(left, left.frac[index], right.frac[index])))
            for index in range(left.atom_count)
        ]
        order = sorted(range(len(displacements)), key=displacements.__getitem__, reverse=True)
        rows.append(
            {
                "max_displacement_A": max(displacements),
                "rms_displacement_A": math.sqrt(statistics.fmean(value * value for value in displacements)),
                "largest_moves": [
                    {
                        "atom_index_zero_based": index,
                        "element": left.labels[index],
                        "displacement_A": displacements[index],
                    }
                    for index in order[:3]
                ],
            }
        )
    return rows


def _coordinate_series(directory: Path, pair: tuple[int, int], current: float, limit: int) -> list[float]:
    xdatcar = directory / "XDATCAR"
    if not xdatcar.is_file() or xdatcar.stat().st_size == 0:
        return [current] * limit
    frames = ase_read(xdatcar, index=":")
    values = [float(frame.get_distance(pair[0], pair[1], mic=True)) for frame in frames]
    return values[-limit:]


def collect_evidence(
    workdir: Path,
    pair: tuple[int, int],
    important_interval: tuple[float, float],
    cycles: int,
    monitor: dict[str, Any],
) -> dict[str, Any]:
    directories = numbered_image_dirs(workdir)
    structures = [read_poscar(preferred_image_structure(directory)) for directory in directories]
    if len(structures) < 3:
        raise ValueError("at least three NEB image directories are required")
    for structure in structures[1:]:
        errors = compatible(structures[0], structure)
        if errors:
            raise ValueError(f"incompatible NEB structures: {errors}")
    if min(pair) < 0 or max(pair) >= structures[0].atom_count:
        raise ValueError("reaction pair is outside the atom range")
    current = [pbc_distance(structure, *pair) for structure in structures]
    series = [
        _coordinate_series(directory, pair, value, cycles)
        for directory, value in zip(directories, current, strict=True)
    ]
    common = min(len(values) for values in series)
    history = [[values[-common + cycle] for values in series] for cycle in range(common)]
    oszicar = {directory.name: parse_oszicar(directory / "OSZICAR") for directory in directories}
    outcar = {directory.name: parse_outcar(directory / "OUTCAR") for directory in directories}
    force_history = {
        name: record.get("neb_force_history", [])[-cycles:]
        for name, record in outcar.items()
        if record.get("neb_force_history")
    }
    energy_series = [oszicar[directory.name].get("energies", [])[-cycles:] for directory in directories]
    common_energy = min((len(values) for values in energy_series), default=0)
    highest_history = (
        [
            directories[
                max(
                    range(len(directories)),
                    key=lambda image: energy_series[image][-common_energy + cycle],
                )
            ].name
            for cycle in range(common_energy)
        ]
        if common_energy
        else []
    )
    return {
        "image_names": [directory.name for directory in directories],
        "reaction_coordinate_name": f"distance({pair[0]},{pair[1]})",
        "reaction_pair_zero_based": list(pair),
        "important_interval_A": list(important_interval),
        "coordinate_history_A": history,
        "adjacent_pair_metrics": _current_pair_metrics(structures),
        "energies_eV": [
            (oszicar[name]["energies"] or [None])[-1] for name in [directory.name for directory in directories]
        ],
        "scf_iterations": {
            name: oszicar[name].get("scf_iterations", [])[-cycles:] for name in oszicar
        },
        "total_magnetic_moment_muB": {
            name: oszicar[name].get("magnetization_history_muB", [])[-cycles:] for name in oszicar
        },
        "projected_force_history_eV_per_A": monitor.get(
            "projected_force_history_eV_per_A", force_history
        ),
        "highest_image_history": monitor.get("highest_image_history", highest_history),
        "image_ordering_valid": bool(monitor.get("image_ordering_valid", True)),
        "mixed_elementary_steps": bool(monitor.get("mixed_elementary_steps", False)),
        "invalid_endpoints": bool(monitor.get("invalid_endpoints", False)),
    }


def evaluate_quality(evidence: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    names = evidence["image_names"]
    history = evidence["coordinate_history_A"]
    current = history[-1]
    gaps = [abs(right - left) for left, right in zip(current, current[1:], strict=False)]
    critical_index = max(range(len(gaps)), key=gaps.__getitem__)
    gap_history = [
        abs(row[critical_index + 1] - row[critical_index]) for row in history
    ]
    metrics = evidence["adjacent_pair_metrics"]
    displacement_values = [row["max_displacement_A"] for row in metrics]
    interval_low, interval_high = evidence["important_interval_A"]
    left_history = [row[critical_index] for row in history]
    right_history = [row[critical_index + 1] for row in history]
    persistence = thresholds["persistence"]
    geometry = thresholds["geometry"]
    enough_history = len(history) >= int(persistence["monitoring_cycles_min"])
    median_gap = _median_positive(gaps)
    median_displacement = _median_positive(displacement_values)
    right_name = names[critical_index + 1]
    force_history = evidence["projected_force_history_eV_per_A"].get(right_name, [])
    energies = evidence.get("energies_eV", [])
    energy_corner = False
    if all(value is not None for value in energies):
        nearby = range(max(1, critical_index), min(len(energies) - 1, critical_index + 2))
        energy_corner = any(
            abs(float(energies[index + 1]) - 2 * float(energies[index]) + float(energies[index - 1]))
            >= float(thresholds["energy"]["sharp_corner_threshold_eV"])
            for index in nearby
        )
    straddles = current[critical_index] < interval_low and current[critical_index + 1] > interval_high
    conditions = {
        "A_abnormal_adjacent_displacement": (
            displacement_values[critical_index] > float(geometry["image_jump_warning_A"])
            or (
                median_displacement > 0
                and displacement_values[critical_index] / median_displacement
                >= float(geometry["abnormal_gap_ratio_to_median_min"])
            )
        ),
        "B_large_reaction_coordinate_gap": (
            straddles
            or (
                median_gap > 0
                and gaps[critical_index] / median_gap
                >= float(geometry["abnormal_gap_ratio_to_median_min"])
            )
        ),
        "C_gap_persistent_or_increasing": (
            enough_history
            and gap_history[-1]
            >= gap_history[0] * float(geometry["gap_non_decrease_fraction"])
        ),
        "E_important_interval_unsampled": not any(interval_low <= value <= interval_high for value in current),
        "F_sharp_energy_corner": energy_corner,
        "G_neighbouring_images_in_separate_basins": (
            enough_history
            and max(left_history) - min(left_history) <= float(geometry["reactant_basin_span_max_A"])
            and right_history[-1] > right_history[0]
        ),
        "H_force_drop_from_product_basin_motion": (
            enough_history and right_history[-1] > right_history[0] and _decreasing(force_history)
        ),
        "I_unstable_highest_image": len(set(evidence["highest_image_history"][-5:])) > 1,
        "J_image_ordering_or_collapse": not evidence["image_ordering_valid"],
    }
    condition_families = {
        "discontinuity": any(
            conditions[name]
            for name in ("A_abnormal_adjacent_displacement", "B_large_reaction_coordinate_gap")
        ),
        "persistence": conditions["C_gap_persistent_or_increasing"],
        "basin_separation": any(
            conditions[name]
            for name in (
                "G_neighbouring_images_in_separate_basins",
                "H_force_drop_from_product_basin_motion",
            )
        ),
        "energy_shape": conditions["F_sharp_energy_corner"],
        "ordering": conditions["J_image_ordering_or_collapse"],
    }
    underresolved_reasons = [name for name, passed in conditions.items() if passed]
    independent_families = [name for name, passed in condition_families.items() if passed]
    underresolved = bool(
        enough_history
        and condition_families["discontinuity"]
        and len(independent_families)
        >= int(persistence["underresolved_independent_family_count_min"])
    )
    nelm = int(evidence["configured_nelm"])
    hard_scf_count = int(thresholds["electronic"]["consecutive_nelm_exhaustion_hard_min"])
    electronic_images = [
        name
        for name, values in evidence["scf_iterations"].items()
        if trailing_threshold_count(values, nelm) >= hard_scf_count
    ]
    monitor_warnings = [
        name
        for name, active in (
            ("UNVERIFIED_INVALID_ENDPOINT_FLAG", evidence["invalid_endpoints"]),
            ("UNVERIFIED_MIXED_ELEMENTARY_STEPS_FLAG", evidence["mixed_elementary_steps"]),
        )
        if active
    ]
    if underresolved:
        status = "UNDERRESOLVED_REACTION_COORDINATE"
        suggested_check = "REVIEW_DENSIFIED_FULL_IS_FS_PATH_REQUIREMENT"
    elif electronic_images:
        status = "ELECTRONIC_FAILURE"
        suggested_check = "TEST_FAILED_IMAGE_AS_SINGLE_POINT"
    else:
        readiness = thresholds.get("readiness", {})
        pre_ci_force = readiness.get("pre_ci_projected_force_eV_per_A_max")
        all_force_histories = evidence["projected_force_history_eV_per_A"]
        stable_highest = (
            len(evidence["highest_image_history"]) >= int(persistence["monitoring_cycles_min"])
            and len(set(evidence["highest_image_history"][-int(persistence["monitoring_cycles_min"]):])) == 1
        )
        coordinate_drift = max(
            abs(history[-1][index] - history[0][index]) for index in range(len(current))
        )
        stable_highest_required = bool(readiness.get("require_stable_highest_image", True))
        electronic_required = bool(readiness.get("require_electronic_convergence", True))
        coordinate_coverage_required = bool(
            readiness.get("require_reaction_coordinate_coverage", True)
        )
        ready_for_ci = bool(
            enough_history
            and pre_ci_force is not None
            and all(name in all_force_histories for name in names[1:-1])
            and all(
                all_force_histories[name]
                and all_force_histories[name][-1] <= float(pre_ci_force)
                for name in names[1:-1]
            )
            and (stable_highest or not stable_highest_required)
            and (not electronic_images or not electronic_required)
            and not energy_corner
            and (
                any(interval_low <= value <= interval_high for value in current)
                or not coordinate_coverage_required
            )
            and coordinate_drift <= float(readiness["recent_coordinate_drift_A_max"])
        )
        status = "CI_NEB_READINESS_EVIDENCE" if ready_for_ci else "ORDINARY_NEB_PROGRESS_EVIDENCE"
        suggested_check = "REVIEW_CI_NEB_READINESS" if ready_for_ci else "REVIEW_NEXT_MONITORING_CHECKPOINT"
    return {
        "schema_version": 2,
        "PATH_QUALITY_STATUS": status,
        "REASON_CODES": [
            *underresolved_reasons,
            *(["ELECTRONIC_CONVERGENCE_FAILURE"] if electronic_images else []),
            *monitor_warnings,
        ],
        "CRITICAL_IMAGES": [names[critical_index], names[critical_index + 1]],
        "EVIDENCE": {
            "reaction_coordinate_A": dict(zip(names, current, strict=True)),
            "critical_gap_history_A": gap_history,
            "critical_pair_displacement": metrics[critical_index],
            "electronic_failure_images": electronic_images,
            "conditions": conditions,
            "condition_families": condition_families,
            "independent_evidence_families": independent_families,
            "monitor_warnings": monitor_warnings,
        },
        "CHEMICAL_INTERPRETATION": (
            "reactant-side image remains bonded while its neighbour moves deeper into the product basin"
            if underresolved
            else "no persistent underresolved reaction-coordinate gap was proven"
        ),
        "FILES_SAVED": [],
        "NEXT_REQUIRED_EVIDENCE_CHECK": suggested_check,
        "execution_authority": "scripts.ts_strategy_engine.execution_gate.decide_execution",
        "COMPUTE_COST_ASSESSMENT": (
            "rebuilding is cheaper and more reliable than converging an underresolved path"
            if underresolved
            else "continue only while the path remains structurally valid"
        ),
    }
