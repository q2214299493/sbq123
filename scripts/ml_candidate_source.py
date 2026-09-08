"""Shared hash, identity and geometry checks for saved ML candidate paths."""
from __future__ import annotations

import numpy as np
from ase.io import read

from scripts.artifact_io import sha256_file
from scripts.aqcat25_ml_neb import _fixed_indices
from scripts.dual_model_ml_neb import _geometry_guard_evidence, _load_images
from scripts.prepare_dual_model_ts_active_learning_round import _safe_snapshot_file


def _structure_row(path, expected, sample_id, image, role, method, reference):
    if sha256_file(path) != expected:
        raise ValueError(f"candidate structure hash mismatch: {sample_id}")
    value = read(path, format="vasp")
    if not np.isfinite(value.positions).all() or not np.isfinite(value.cell).all():
        raise ValueError("candidate coordinates must be finite")
    fixed = _fixed_indices(reference)
    if (value.get_chemical_symbols() != reference.get_chemical_symbols()
            or _fixed_indices(value) != fixed or len(value.constraints) != len(reference.constraints)
            or not np.array_equal(value.pbc, reference.pbc)
            or not np.allclose(value.cell, reference.cell, rtol=0, atol=1e-8)
            or not np.allclose(value.positions[fixed], reference.positions[fixed], rtol=0, atol=1e-8)):
        raise ValueError("candidate atom order, cell, or fixed-mask mismatch")
    row = {"sample_id": sample_id, "image": image, "source_stage": method,
           "selection_role": role, "path": f"structures/{sample_id}.vasp", "sha256": expected,
           "source_path": path}
    return value, row


def load_candidate_path(request, manifest, manifest_path, source_request_path, *, method, minimum_images=5):
    initial = _load_images(request, source_request_path.parent)
    rows, atoms = [], []
    images = manifest.get("images", [])
    if len(images) != len(initial) or len(images) < minimum_images:
        raise ValueError("a complete path with enough images is required")

    for index, row in enumerate(images):
        if row["image"] != f"{index:02d}":
            raise ValueError("candidate path image order mismatch")
        path = _safe_snapshot_file(manifest_path.parent, row["structure_path"])
        value, record = _structure_row(path, row["structure_sha256"], f"pre_{index:02d}", row["image"],
                                       "path_member", method, initial[0])
        atoms.append(value)
        rows.append(record)
    for index in (0, len(atoms) - 1):
        if not np.allclose(atoms[index].positions, initial[index].positions, rtol=0, atol=1e-8):
            raise ValueError("candidate endpoint changed")
    if _geometry_guard_evidence(atoms, request).get("passed") is not True:
        raise ValueError("candidate path failed recomputed geometry gates")
    return atoms, rows
