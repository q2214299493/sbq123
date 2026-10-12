#!/usr/bin/env python3
"""Manifest-driven AQCat25 pre-relaxation for one adsorption candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from ase.io import read, write


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atom_order_sha256(symbols: list[str]) -> str:
    return hashlib.sha256(("\n".join(symbols) + "\n").encode("utf-8")).hexdigest()


def fixed_indices_1based(atoms) -> list[int]:
    fixed: set[int] = set()
    for constraint in atoms.constraints:
        if hasattr(constraint, "get_indices"):
            fixed.update(int(index) + 1 for index in constraint.get_indices())
    return sorted(fixed)


def _pair_distance(atoms, pair: list[int]) -> float:
    return float(atoms.get_distance(pair[0] - 1, pair[1] - 1, mic=True))


def geometry_snapshot(atoms, adsorption: dict[str, Any]) -> dict[str, Any]:
    symbols = atoms.get_chemical_symbols()
    pair_records: dict[str, dict[str, Any]] = {}
    for source in (adsorption["connectivity_constraints"], adsorption["monitored_pairs"]):
        for pair in source:
            label = pair["label"]
            pair_records[label] = {
                "atoms_1based": pair["atoms_1based"],
                "distance_A": _pair_distance(atoms, pair["atoms_1based"]),
            }

    surface_indices = [
        index for index, symbol in enumerate(symbols) if symbol in set(adsorption["surface_elements"])
    ]
    if not surface_indices:
        raise ValueError("candidate contains none of the declared surface elements")
    anchor_records: list[dict[str, Any]] = []
    for item in adsorption["adsorbate_atoms"]:
        if item["role"] != "anchor":
            continue
        atom_index = item["index_1based"] - 1
        nearest_distance, nearest_index = min(
            (float(atoms.get_distance(atom_index, surface_index, mic=True)), surface_index)
            for surface_index in surface_indices
        )
        anchor_records.append(
            {
                "atom_index_1based": atom_index + 1,
                "symbol": item["symbol"],
                "nearest_surface_atom_index_1based": nearest_index + 1,
                "nearest_surface_distance_A": nearest_distance,
            }
        )
    return {"pairs": pair_records, "anchors": anchor_records}


def evaluate_connectivity(atoms, adsorption: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for rule in adsorption["connectivity_constraints"]:
        distance = _pair_distance(atoms, rule["atoms_1based"])
        passed = True
        if "min_distance_A" in rule:
            passed = passed and distance >= float(rule["min_distance_A"])
        if "max_distance_A" in rule:
            passed = passed and distance <= float(rule["max_distance_A"])
        checks.append(
            {
                "label": rule["label"],
                "atoms_1based": rule["atoms_1based"],
                "distance_A": distance,
                "min_distance_A": rule.get("min_distance_A"),
                "max_distance_A": rule.get("max_distance_A"),
                "passed": passed,
            }
        )
    return {"status": "pass" if all(check["passed"] for check in checks) else "fail", "checks": checks}


def load_candidate(handoff_path: Path):
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if handoff.get("schema_version") != 2 or handoff.get("direction") != "work_to_gpu":
        raise ValueError("runner requires a schema-version 2 work_to_gpu handoff")
    if handoff.get("workflow_kind") != "adsorption":
        raise ValueError("this runner accepts adsorption handoffs only")
    structure_ref = handoff["candidate_structure"]
    structure_path = (handoff_path.parent / structure_ref["path"]).resolve()
    if not structure_path.is_file():
        raise FileNotFoundError(structure_path)
    if sha256_file(structure_path) != structure_ref["sha256"]:
        raise ValueError("candidate structure SHA256 does not match the handoff")

    atoms = read(structure_path, format="vasp")
    symbols = atoms.get_chemical_symbols()
    if len(symbols) != structure_ref["atom_count"]:
        raise ValueError("candidate atom count does not match the handoff")
    if atom_order_sha256(symbols) != structure_ref["atom_order_sha256"]:
        raise ValueError("candidate atom order does not match the handoff")
    declared_fixed = sorted(handoff["selective_dynamics"]["fixed_atom_indices_1based"])
    if fixed_indices_1based(atoms) != declared_fixed:
        raise ValueError("candidate Selective Dynamics does not match the handoff")

    seen: set[int] = set()
    for item in handoff["adsorption"]["adsorbate_atoms"]:
        index = item["index_1based"]
        if index in seen or not 1 <= index <= len(symbols):
            raise ValueError("adsorbate atom indices are invalid or duplicated")
        seen.add(index)
        if symbols[index - 1] != item["symbol"]:
            raise ValueError(f"adsorbate symbol mismatch at atom {index}")
    return handoff, atoms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from ase.optimize import LBFGS
    from fairchem.core.common.relaxation.ase_utils import patched_calc
    from fairchem.core.models.equiformer_v2 import equiformer_v2_film  # noqa: F401

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {args.output}")
    args.output.mkdir(parents=True, exist_ok=True)

    handoff, atoms = load_candidate(args.handoff)
    model = handoff["model"]
    if sha256_file(args.checkpoint) != model["checkpoint_sha256"]:
        raise ValueError("checkpoint SHA256 does not match the handoff")

    adsorption = handoff["adsorption"]
    symbols_before = atoms.get_chemical_symbols()
    cell_before = np.asarray(atoms.cell.array, dtype=float).copy()
    positions_before = np.asarray(atoms.positions, dtype=float).copy()
    fixed = np.asarray([index - 1 for index in handoff["selective_dynamics"]["fixed_atom_indices_1based"]], dtype=int)
    before = geometry_snapshot(atoms, adsorption)

    atoms.info["is_spin_off"] = False
    atoms.info["is_low_fi"] = False
    atoms.calc = patched_calc(checkpoint_path=str(args.checkpoint), is_spin_off=False, is_low_fi=False)
    optimizer = LBFGS(atoms, logfile="-")
    converged = bool(optimizer.run(fmax=float(model["fmax_eV_per_A"]), steps=int(model["max_steps"])))
    forces = np.asarray(atoms.get_forces(), dtype=float)
    free_mask = np.ones(len(atoms), dtype=bool)
    free_mask[fixed] = False
    movable_fmax = float(np.linalg.norm(forces[free_mask], axis=1).max()) if np.any(free_mask) else 0.0
    after = geometry_snapshot(atoms, adsorption)
    connectivity = evaluate_connectivity(atoms, adsorption)
    invariants = {
        "atom_order_preserved": atoms.get_chemical_symbols() == symbols_before,
        "cell_preserved": bool(np.allclose(atoms.cell.array, cell_before, atol=1e-10, rtol=0.0)),
        "fixed_atoms_preserved": bool(np.allclose(atoms.positions[fixed], positions_before[fixed], atol=1e-8, rtol=0.0)),
    }
    write(args.output / "POSCAR", atoms, format="vasp", direct=True, vasp5=True)
    record = {
        "handoff_id": handoff["handoff_id"],
        "converged": converged,
        "optimizer_steps": int(optimizer.nsteps),
        "energy_eV": float(atoms.get_potential_energy()),
        "movable_fmax_eV_per_A": movable_fmax,
        "geometry_before": before,
        "geometry_after": after,
        "connectivity": connectivity,
        "structure_invariants": invariants,
    }
    (args.output / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
