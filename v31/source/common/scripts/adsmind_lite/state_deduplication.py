from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from scripts.workflow_geometry import relative_positions_xy

from .adsmind_common import require_ase_structure
from .relaxed_analysis import structure_indices


def adsorbate_relative_positions(path: Path, adsorbate_indices: list[int], anchor_local: int) -> np.ndarray:
    atoms = require_ase_structure(path)
    adsorbate = atoms.positions[adsorbate_indices].copy()
    anchor = adsorbate[anchor_local].copy()
    cell = np.asarray(atoms.cell)
    return relative_positions_xy(cell, adsorbate, anchor)


def record_adsorbate_indices(record: dict[str, Any], path: Path) -> list[int]:
    atoms = require_ase_structure(path)
    _, adsorbate_indices = structure_indices(record, len(atoms))
    return adsorbate_indices


def kabsch_rmsd(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape:
        return math.inf
    first_centered = first - first.mean(axis=0)
    second_centered = second - second.mean(axis=0)
    covariance = first_centered.T @ second_centered
    left, _, right = np.linalg.svd(covariance)
    rotation = left @ right
    difference = first_centered @ rotation - second_centered
    return float(np.sqrt(np.mean(np.sum(difference**2, axis=1))))


def deduplicate_records(records: list[dict[str, Any]], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rules = analysis["duplicate_detection"]
    rmsd_tolerance = float(rules["geometry_rmsd_tolerance_angstrom"])
    energy_tolerance = float(rules["energy_tolerance_ev"])
    representatives: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    output: list[dict[str, Any]] = []
    for source in sorted(records, key=energy_sort_key):
        record = dict(source)
        key = (str(record["adsorbate"]), str(record.get("relaxed_site_class", "unknown")), str(record.get("connectivity_signature", "")))
        duplicate_of = find_duplicate(record, representatives[key], rmsd_tolerance, energy_tolerance)
        if duplicate_of is None:
            record["duplicate"] = False
            representatives[key].append(record)
        else:
            record["duplicate"] = True
            record["duplicate_of"] = duplicate_of["candidate_id"]
            record["recommend_for_vasp"] = False
            record["reason_code"] = "duplicate_relaxed_state"
        output.append(record)
    return output


def energy_sort_key(record: dict[str, Any]) -> tuple[float, str]:
    energy = record.get("energy_ev")
    return (math.inf if energy is None else float(energy), str(record.get("candidate_id", "")))


def find_duplicate(
    record: dict[str, Any],
    representatives: list[dict[str, Any]],
    rmsd_tolerance: float,
    energy_tolerance: float,
) -> dict[str, Any] | None:
    path = Path(record.get("selected_structure") or record.get("relaxed_structure") or record["initial_structure"])
    first = adsorbate_relative_positions(
        path,
        record_adsorbate_indices(record, path),
        int(record["anchor_index_adsorbate_0based"]),
    )
    for prior in representatives:
        prior_path = Path(prior.get("selected_structure") or prior.get("relaxed_structure") or prior["initial_structure"])
        second = adsorbate_relative_positions(
            prior_path,
            record_adsorbate_indices(prior, prior_path),
            int(prior["anchor_index_adsorbate_0based"]),
        )
        if kabsch_rmsd(first, second) > rmsd_tolerance:
            continue
        if record.get("energy_ev") is not None and prior.get("energy_ev") is not None:
            if abs(float(record["energy_ev"]) - float(prior["energy_ev"])) > energy_tolerance:
                continue
        return prior
    return None
