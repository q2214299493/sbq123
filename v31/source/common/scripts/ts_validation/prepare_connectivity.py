from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import numpy as np

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.neb_agent.utils_structure import copy_with_frac, read_poscar, write_poscar


def prepare_connectivity_displacements(
    source_saddle: Path,
    vfa_analysis_path: Path,
    review_path: Path,
    destination: Path,
    *,
    amplitude_A: float,
    mode_index: int | None = None,
) -> dict[str, Any]:
    """Create hash-bound positive/negative imaginary-mode displacements."""

    if not np.isfinite(amplitude_A) or amplitude_A <= 0:
        raise ValueError("connectivity displacement amplitude must be positive and finite")
    analysis = load_json_object(vfa_analysis_path)
    review = load_json_object(review_path)
    selected = mode_index or int(analysis.get("principal_mode_index", 0))
    modes = [mode for mode in analysis.get("modes", []) if int(mode.get("mode_index", -1)) == selected]
    if len(modes) != 1 or not modes[0].get("imaginary"):
        raise ValueError("selected connectivity mode must be one unique imaginary mode")
    if review.get("status") != "accepted_for_connectivity_displacement":
        raise ValueError("connectivity displacement requires explicit accepted review")
    if not review.get("reviewer") or not review.get("reviewed_at"):
        raise ValueError("connectivity review identity is incomplete")
    expected = {
        "source_saddle_sha256": sha256_file(source_saddle),
        "vfa_analysis_sha256": sha256_file(vfa_analysis_path),
        "mode_index": selected,
        "amplitude_A": amplitude_A,
    }
    for key, value in expected.items():
        if review.get(key) != value:
            raise ValueError(f"connectivity review is not bound to {key}")

    structure = read_poscar(source_saddle)
    if not structure.selective:
        raise ValueError("connectivity saddle must preserve Selective Dynamics")
    mode = np.zeros((structure.atom_count, 3), dtype=float)
    for atom in modes[0].get("dominant_atoms", []):
        index = int(atom["atom_index_zero_based"])
        if index < 0 or index >= structure.atom_count:
            raise ValueError("mode atom index is outside the saddle structure")
        mode[index] = [float(atom["dx"]), float(atom["dy"]), float(atom["dz"])]
    norm = float(np.linalg.norm(mode))
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError("connectivity mode must be finite and non-zero")
    mode /= norm
    fixed = [
        index
        for index, flags in enumerate(structure.flags)
        if flags and all(value == "F" for value in flags)
    ]
    if any(float(np.linalg.norm(mode[index])) > 1.0e-12 for index in fixed):
        raise ValueError("fixed atoms must have zero connectivity-mode components")

    destination.mkdir(parents=True, exist_ok=True)
    occupied = [destination / name for name in ("positive", "negative", "connectivity_displacement_manifest.json")]
    if any(path.exists() for path in occupied):
        raise FileExistsError("connectivity displacement destination already contains generated outputs")
    branch_records = []
    inv_cell = np.linalg.inv(structure.cell)
    for direction, sign in (("positive", 1.0), ("negative", -1.0)):
        branch = destination / direction
        branch.mkdir()
        displaced_frac = structure.frac + (sign * amplitude_A * mode) @ inv_cell
        displaced = copy_with_frac(
            structure,
            displaced_frac,
            f"{structure.comment} | mode {selected} {direction} {amplitude_A:.6f} A",
        )
        write_poscar(branch / "POSCAR", displaced)
        shutil.copy2(review_path, branch / "connectivity_displacement_review.json")
        handoff: dict[str, Any] = {
            "schema_version": 1,
            "document_kind": "ts_connectivity_relax_handoff",
            "direction": direction,
            "amplitude_A": amplitude_A,
            "mode_index": selected,
            "frequency_cm1": float(modes[0]["frequency_cm1"]),
            "source_saddle": str(source_saddle.resolve()),
            "source_saddle_sha256": sha256_file(source_saddle),
            "vfa_analysis": str(vfa_analysis_path.resolve()),
            "vfa_analysis_sha256": sha256_file(vfa_analysis_path),
            "displacement_review": "connectivity_displacement_review.json",
            "displacement_review_sha256": sha256_file(branch / "connectivity_displacement_review.json"),
            "displacement_poscar_sha256": sha256_file(branch / "POSCAR"),
            "contract_sha256": analysis.get("contract_sha256"),
            "atom_map_sha256": analysis.get("atom_map_sha256"),
            "compatibility_sha256": analysis.get("compatibility_sha256"),
            "reaction_atom_indices_zero_based": [45, 46],
            "fixed_atom_indices_zero_based": fixed,
            "mode_norm_before_normalization": norm,
            "maximum_atom_displacement_A": float(amplitude_A * np.max(np.linalg.norm(mode, axis=1))),
        }
        write_json(branch / "connectivity_handoff.json", handoff)
        branch_records.append({"direction": direction, "poscar_sha256": handoff["displacement_poscar_sha256"]})
    manifest = {
        "schema_version": 1,
        "document_kind": "ts_connectivity_displacement_pair",
        **expected,
        "branches": branch_records,
        "fixed_atom_indices_zero_based": fixed,
    }
    write_json(destination / "connectivity_displacement_manifest.json", manifest)
    return manifest
