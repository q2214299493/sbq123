#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from ase.io import read

try:
    from scripts.artifact_io import sha256_file, write_json_atomic
    from scripts.aqcat25_ts_schema import load_document, validate_document
except ModuleNotFoundError:  # MZ73 deploys this runner beside the standalone validator.
    from artifact_io import sha256_file, write_json_atomic
    from aqcat25_ts_schema import load_document, validate_document


def _bond(value: str) -> list[object]:
    action, left, right = value.split(":", 2)
    if action not in {"form", "break"}:
        raise argparse.ArgumentTypeError("bond action must be form or break")
    return [int(left) - 1, int(right) - 1, action]


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict hash-bound AQCat25 forces for one TS active-learning label.")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--structure", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--bond", action="append", type=_bond)
    parser.add_argument("--adsorbate-indices", help="Comma-separated one-based indices")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--is-spin-off", action="store_true")
    parser.add_argument("--is-low-fi", action="store_true")
    args = parser.parse_args()

    request_sha256 = None
    if args.request:
        request = load_document(args.request, expected_kind="aqcat25_ts_force_prediction_request")
        structure = args.request.parent / request["structure"]["path"]
        checkpoint = Path(request["checkpoint"]["path"])
        bonds = [
            [int(item["atoms_1based"][0]) - 1, int(item["atoms_1based"][1]) - 1, item["change"]]
            for item in request["indexed_bond_changes"]
        ]
        adsorbate_indices = [int(value) - 1 for value in request["adsorbate_indices_1based"]]
        request_sha256 = sha256_file(args.request)
        if sha256_file(structure) != request["structure"]["sha256"]:
            raise ValueError("force-prediction request structure hash mismatch")
        if sha256_file(checkpoint) != request["checkpoint"]["sha256"]:
            raise ValueError("force-prediction request checkpoint hash mismatch")
    else:
        if not args.structure or not args.checkpoint or not args.bond or not args.adsorbate_indices:
            parser.error("use --request or provide --structure, --checkpoint, --bond and --adsorbate-indices")
        structure = args.structure
        checkpoint = args.checkpoint
        bonds = args.bond
        adsorbate_indices = [int(value) - 1 for value in args.adsorbate_indices.split(",")]

    from fairchem.core.common.relaxation.ase_utils import patched_calc

    atoms = read(structure, format="vasp")
    atoms.info.update(
        {
            "is_spin_off": args.is_spin_off,
            "is_low_fi": args.is_low_fi,
            "bonds_TS": bonds,
            "indices_ads": adsorbate_indices,
        }
    )
    atoms.calc = patched_calc(
        checkpoint_path=str(checkpoint),
        is_spin_off=args.is_spin_off,
        is_low_fi=args.is_low_fi,
    )
    energy = float(atoms.get_potential_energy())
    forces = np.asarray(atoms.get_forces(), dtype=float)
    if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all() or not np.isfinite(energy):
        raise RuntimeError("AQCat25 returned invalid energy or forces")
    payload = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_force_prediction",
        "request_sha256": request_sha256,
        "structure_sha256": sha256_file(structure),
        "checkpoint_sha256": sha256_file(checkpoint),
        "predicted_energy_eV": energy,
        "forces_eV_per_A": forces.tolist(),
        "result_class": "predicted_transition_state_candidate_only",
        "reportable_dft": False,
        "scientifically_validated_ts": False,
    }
    validate_document(payload, expected_kind="aqcat25_ts_force_prediction")
    write_json_atomic(args.output, payload)


if __name__ == "__main__":
    main()
