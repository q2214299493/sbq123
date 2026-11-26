#!/usr/bin/env python3
"""Evaluate one fixed ML-NEB path with a real multi-checkpoint committee.

This script performs inference only.  It never submits VASP, changes the path,
or treats disagreement as calibrated uncertainty without held-out VASP evidence.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
from ase.io import read

try:
    from scripts.aqcat25_handoff import validate_handoff
    from scripts.aqcat25_ml_neb import (
        _attach_model_context,
        _build_aqcat_calculator,
        _movable_indices,
    )
    from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
    from scripts.ts_strategy_engine.ml_neb_path import validate_gpu_ml_neb_path_manifest
except ModuleNotFoundError:  # Standalone deployment on MZ73.
    from aqcat25_handoff import validate_handoff
    from aqcat25_ml_neb import _attach_model_context, _build_aqcat_calculator, _movable_indices
    from artifact_io import load_json_object, sha256_file, write_json_atomic
    from ml_neb_path import validate_gpu_ml_neb_path_manifest


CalculatorFactory = Callable[[Path, str], Any]


def _member(value: str) -> tuple[str, Path]:
    member_id, separator, path = value.partition("=")
    if not separator or not member_id or not path:
        raise argparse.ArgumentTypeError("committee member must be MEMBER_ID=CHECKPOINT_PATH")
    return member_id, Path(path)


def prepare_committee_request(
    path_manifest: Path,
    members: list[tuple[str, Path]],
    output: Path,
) -> dict[str, Any]:
    manifest = validate_gpu_ml_neb_path_manifest(path_manifest)
    if len(members) < 3:
        raise ValueError("a path committee requires at least three checkpoints")
    ids = [member_id for member_id, _ in members]
    if len(ids) != len(set(ids)):
        raise ValueError("committee member IDs must be unique")
    records = []
    for member_id, checkpoint in members:
        if not checkpoint.is_file():
            raise FileNotFoundError(f"committee checkpoint does not exist: {checkpoint}")
        records.append(
            {
                "member_id": member_id,
                "checkpoint": {
                    "path": str(checkpoint.resolve()),
                    "sha256": sha256_file(checkpoint),
                },
            }
        )
    hashes = {row["checkpoint"]["sha256"] for row in records}
    if len(hashes) != len(records):
        raise ValueError("committee checkpoints must have unique SHA256 hashes")
    if manifest["checkpoint_sha256"] not in hashes:
        raise ValueError("committee must include the primary ML-NEB checkpoint")
    request = {
        "schema_version": 1,
        "document_kind": "aqcat25_ml_path_committee_request",
        "source_path_manifest": {
            "path": str(path_manifest.resolve()),
            "sha256": sha256_file(path_manifest),
        },
        "primary_checkpoint_sha256": manifest["checkpoint_sha256"],
        "members": records,
        "inference_policy": {
            "same_fixed_path_structures": True,
            "serial_checkpoint_loading": True,
            "minimum_unique_checkpoints": 3,
            "automatic_submission": False,
        },
    }
    write_json_atomic(output, request, ensure_ascii=True)
    return request


def _validate_request(
    request_path: Path,
    path_manifest_path: Path,
    path_manifest: dict[str, Any],
) -> dict[str, Any]:
    request = load_json_object(request_path)
    if request.get("document_kind") != "aqcat25_ml_path_committee_request":
        raise ValueError("invalid path committee request")
    source = request.get("source_path_manifest") or {}
    if source.get("sha256") != sha256_file(path_manifest_path):
        raise ValueError("committee request is not bound to the path manifest")
    if request.get("primary_checkpoint_sha256") != path_manifest["checkpoint_sha256"]:
        raise ValueError("committee primary checkpoint mismatch")
    members = request.get("members")
    if not isinstance(members, list) or len(members) < 3:
        raise ValueError("committee request has fewer than three members")
    ids = [str(row.get("member_id", "")) for row in members]
    hashes = [str((row.get("checkpoint") or {}).get("sha256", "")) for row in members]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("committee member IDs are missing or duplicated")
    if len(hashes) != len(set(hashes)) or any(len(value) != 64 for value in hashes):
        raise ValueError("committee checkpoint hashes are invalid or duplicated")
    if path_manifest["checkpoint_sha256"] not in hashes:
        raise ValueError("committee does not contain the primary checkpoint")
    for row in members:
        checkpoint = Path(row["checkpoint"]["path"])
        if not checkpoint.is_file() or sha256_file(checkpoint) != row["checkpoint"]["sha256"]:
            raise ValueError(f"committee checkpoint hash mismatch: {row['member_id']}")
    return request


def assess_path_committee(
    path_manifest_path: Path,
    request_path: Path,
    output: Path,
    *,
    calculator_factory: CalculatorFactory | None = None,
) -> dict[str, Any]:
    path_manifest = validate_gpu_ml_neb_path_manifest(path_manifest_path)
    request = _validate_request(request_path, path_manifest_path, path_manifest)
    source_ref = path_manifest["source_handoff"]
    source_path = (path_manifest_path.parent / source_ref["path"]).resolve()
    source = validate_handoff(source_path, root=source_path.parent)
    changes = source["transition_state"]["indexed_bond_changes"]
    image_atoms = [
        read(path_manifest_path.parent / row["structure_path"], format="vasp")
        for row in path_manifest["images"]
    ]
    symbols = image_atoms[0].get_chemical_symbols()
    adsorbate = [index for index, symbol in enumerate(symbols) if symbol != "Fe"]
    member_energies: list[list[float]] = []
    member_forces: list[list[np.ndarray]] = []
    for member in request["members"]:
        checkpoint = Path(member["checkpoint"]["path"])
        calculator = (
            calculator_factory(checkpoint, member["member_id"])
            if calculator_factory is not None
            else _build_aqcat_calculator(checkpoint, False, False)
        )
        energies: list[float] = []
        forces: list[np.ndarray] = []
        for source_atoms in image_atoms:
            atoms = source_atoms.copy()
            _attach_model_context(
                atoms,
                changes,
                adsorbate,
                is_spin_off=False,
                is_low_fi=False,
            )
            atoms.calc = calculator
            energy = float(atoms.get_potential_energy())
            force = np.asarray(atoms.get_forces(), dtype=float)
            if not math.isfinite(energy) or force.shape != (len(atoms), 3) or not np.isfinite(force).all():
                raise ValueError(f"non-finite committee prediction: {member['member_id']}")
            energies.append(energy)
            forces.append(force)
        member_energies.append(energies)
        member_forces.append(forces)
        del calculator
    rows = []
    for image_index, image in enumerate(path_manifest["images"]):
        energies = np.asarray([values[image_index] for values in member_energies], dtype=float)
        forces = np.stack([values[image_index] for values in member_forces], axis=0)
        movable = _movable_indices(image_atoms[image_index])
        if not len(movable):
            raise ValueError(f"path image {image['image']} has no movable atoms")
        component_std = np.std(forces[:, movable, :], axis=0, ddof=0)
        atom_vector_std = np.linalg.norm(component_std, axis=1)
        rows.append(
            {
                "image": image["image"],
                "structure_sha256": image["structure_sha256"],
                "energy_mean_eV": float(np.mean(energies)),
                "energy_std_eV": float(np.std(energies, ddof=0)),
                "energy_range_eV": float(np.max(energies) - np.min(energies)),
                "force_component_std_rms_eV_per_A": float(
                    np.sqrt(np.mean(component_std * component_std))
                ),
                "force_vector_std_max_eV_per_A": float(np.max(atom_vector_std)),
                "member_energies_eV": {
                    member["member_id"]: float(energies[index])
                    for index, member in enumerate(request["members"])
                },
            }
        )
    assessment = {
        "schema_version": 1,
        "document_kind": "aqcat25_ml_path_committee_assessment",
        "status": "committee_disagreement_available_not_yet_calibrated_uncertainty",
        "source_path_manifest_sha256": sha256_file(path_manifest_path),
        "committee_request_sha256": sha256_file(request_path),
        "primary_checkpoint_sha256": path_manifest["checkpoint_sha256"],
        "members": [
            {
                "member_id": row["member_id"],
                "checkpoint_sha256": row["checkpoint"]["sha256"],
            }
            for row in request["members"]
        ],
        "images": rows,
        "interpretation": {
            "quantity": "model_committee_disagreement",
            "calibrated_uncertainty": False,
            "requires_held_out_vasp_error_calibration": True,
        },
        "restrictions": {
            "predicted_candidate_only": True,
            "reportable_dft": False,
            "automatic_vasp_submission": False,
            "scientific_acceptance": False,
        },
    }
    write_json_atomic(output, assessment, ensure_ascii=True)
    return assessment


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare or run a real multi-checkpoint AQCat25 path committee."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--path-manifest", type=Path, required=True)
    prepare.add_argument("--member", type=_member, action="append", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    assess = commands.add_parser("assess")
    assess.add_argument("--path-manifest", type=Path, required=True)
    assess.add_argument("--request", type=Path, required=True)
    assess.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = (
        prepare_committee_request(args.path_manifest, args.member, args.output)
        if args.command == "prepare"
        else assess_path_committee(args.path_manifest, args.request, args.output)
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
