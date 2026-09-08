from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import read

from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.artifact_io import sha256_file, write_json_atomic
from scripts.ts_strategy_engine.contract import load_contract


def _fixed_indices(atoms: Atoms) -> list[int]:
    indices: set[int] = set()
    for constraint in atoms.constraints:
        if isinstance(constraint, FixAtoms):
            indices.update(int(index) for index in constraint.get_indices())
    return sorted(indices)


def _structure_ref(path: Path, root: Path, atoms: Atoms) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "format": "vasp_poscar",
        "atom_count": len(atoms),
        "atom_order_sha256": atom_order_sha256(atoms.get_chemical_symbols()),
    }


def _require_compatible(reference: Atoms, candidate: Atoms, label: str) -> None:
    if reference.get_chemical_symbols() != candidate.get_chemical_symbols():
        raise ValueError(f"{label} atom order differs from the initial structure")
    if not np.allclose(reference.cell.array, candidate.cell.array, atol=1.0e-8):
        raise ValueError(f"{label} cell differs from the initial structure")
    if not np.array_equal(reference.pbc, candidate.pbc):
        raise ValueError(f"{label} PBC differs from the initial structure")
    if _fixed_indices(reference) != _fixed_indices(candidate):
        raise ValueError(f"{label} Selective Dynamics differs from the initial structure")


def prepare_handoff(
    *,
    contract_path: Path,
    initial_path: Path,
    final_path: Path,
    waypoint_paths: list[Path],
    output: Path,
    handoff_id: str,
    checkpoint_sha256: str,
    model_identifier: str,
    fmax_eV_per_A: float,
    max_steps: int,
    schema_path: Path,
) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    structures = output / "structures"
    structures.mkdir()

    initial = read(initial_path, format="vasp")
    final = read(final_path, format="vasp")
    waypoints = [read(path, format="vasp") for path in waypoint_paths]
    _require_compatible(initial, final, "final")
    for index, waypoint in enumerate(waypoints, start=1):
        _require_compatible(initial, waypoint, f"waypoint {index}")

    contract = load_contract(contract_path)
    expected_fixed = contract["compatibility"].get("fixed_atom_indices_zero_based")
    if expected_fixed is None or _fixed_indices(initial) != expected_fixed:
        raise ValueError("endpoint fixed atoms do not match the normalized reaction contract")
    if len(contract["atom_map"]) != len(initial):
        raise ValueError("reaction atom map does not cover every endpoint atom")

    copied_initial = structures / "IS.vasp"
    copied_final = structures / "FS.vasp"
    shutil.copy2(initial_path, copied_initial)
    shutil.copy2(final_path, copied_final)
    copied_waypoints: list[Path] = []
    for index, source in enumerate(waypoint_paths, start=1):
        target = structures / f"WP_{index:02d}.vasp"
        shutil.copy2(source, target)
        copied_waypoints.append(target)

    normalized_contract = output / "reaction_contract.normalized.json"
    write_json_atomic(normalized_contract, contract, ensure_ascii=True)
    initial_ref = _structure_ref(copied_initial, output, initial)
    final_ref = _structure_ref(copied_final, output, final)
    waypoint_refs = [
        _structure_ref(path, output, atoms)
        for path, atoms in zip(copied_waypoints, waypoints, strict=True)
    ]
    bond_changes = [
        {"atoms_1based": [left + 1, right + 1], "change": change}
        for change, pairs in (("break", contract["broken_bonds"]), ("form", contract["formed_bonds"]))
        for left, right in pairs
    ]
    if not bond_changes:
        raise ValueError("reaction contract has no indexed bond changes")

    compatibility = contract["compatibility"]
    handoff = {
        "schema_version": 2,
        "direction": "work_to_gpu",
        "handoff_id": handoff_id,
        "workflow_kind": "transition_state",
        "source_workflow_sha256": sha256_file(normalized_contract),
        "candidate_structure": initial_ref,
        "compatibility": {
            "branch": compatibility["branch"],
            "sha256": contract["compatibility_sha256"],
            "slab_model": compatibility["slab_model"],
            "facet": "Fe(110)",
        },
        "model": {
            "identifier": model_identifier,
            "checkpoint_sha256": checkpoint_sha256,
            "fmax_eV_per_A": fmax_eV_per_A,
            "max_steps": max_steps,
        },
        "selective_dynamics": {
            "fixed_atom_indices_1based": [index + 1 for index in expected_fixed],
            "free_atom_count": len(initial) - len(expected_fixed),
        },
        "transition_state": {
            "normalized_reaction_contract_sha256": contract["contract_sha256"],
            "atom_map_sha256": contract["atom_map_sha256"],
            "initial_structure": initial_ref,
            "waypoint_structures": waypoint_refs,
            "final_structure": final_ref,
            "indexed_bond_changes": bond_changes,
        },
        "restrictions": {
            "predicted_candidate_only": True,
            "submit_vasp": False,
            "scientific_acceptance": False,
            "direct_gpu_to_vasp_handoff": False,
        },
    }
    handoff_path = output / "handoff.json"
    write_json_atomic(handoff_path, handoff, ensure_ascii=True)
    validate_handoff(handoff_path, root=output, schema_path=schema_path)
    return handoff_path


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--waypoint", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--handoff-id", required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--model-identifier", default="AQCat25 demo_single model.pt")
    parser.add_argument("--fmax", type=float, default=0.10)
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "configs" / "aqcat25_handoff.schema.json",
    )
    return parser


def main() -> None:
    args = make_parser().parse_args()
    handoff = prepare_handoff(
        contract_path=args.contract,
        initial_path=args.initial,
        final_path=args.final,
        waypoint_paths=args.waypoint,
        output=args.output,
        handoff_id=args.handoff_id,
        checkpoint_sha256=args.checkpoint_sha256,
        model_identifier=args.model_identifier,
        fmax_eV_per_A=args.fmax,
        max_steps=args.max_steps,
        schema_path=args.schema,
    )
    print(handoff)


if __name__ == "__main__":
    main()
