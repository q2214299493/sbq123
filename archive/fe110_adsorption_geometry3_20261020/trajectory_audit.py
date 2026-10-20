"""Read-only audit of every returned short-optimization frame."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from ase.io import read

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.workflow_geometry import minimum_image_delta_xy

from .compare import DEST, same_graph


def audit(path: Path, reference) -> dict:
    frames = read(path, index=":", format="traj")
    first = frames[0].get_scaled_positions(wrap=False)
    intended = connectivity(reference, list(range(45, len(reference.frac))))
    minimum, min_ad_fe, max_step, fixed_max = np.inf, np.inf, 0., 0.
    changed = []
    previous = None
    for index, atoms in enumerate(frames):
        pose = replace(reference, frac=atoms.get_scaled_positions(wrap=False))
        if not np.isfinite(pose.frac).all() or not np.allclose(atoms.cell, reference.cell, rtol=0, atol=1e-10):
            raise ValueError("trajectory nonfinite/cell mismatch")
        distances = np.linalg.norm(minimum_image_delta_xy(pose.frac[:, None, :]-pose.frac[None, :, :]) @ pose.cell, axis=2)
        np.fill_diagonal(distances, np.inf)
        minimum = min(minimum, float(distances.min()))
        min_ad_fe = min(min_ad_fe, float(distances[45:, :45].min()))
        fixed_max = max(fixed_max, float(np.linalg.norm(minimum_image_delta_xy(pose.frac[:18]-first[:18]) @ pose.cell, axis=1).max()))
        if previous is not None:
            max_step = max(max_step, float(np.linalg.norm(minimum_image_delta_xy(pose.frac-previous) @ pose.cell, axis=1).max()))
        if not same_graph(connectivity(pose, list(range(45, len(pose.frac)))), intended):
            changed.append(index)
        previous = pose.frac
    return {"frame_count": len(frames), "graph_changed_frame_indices_0based": changed,
        "minimum_pair_distance_A": minimum, "minimum_adsorbate_Fe_distance_A": min_ad_fe,
        "maximum_adjacent_atom_displacement_A": max_step, "maximum_fixed_atom_displacement_A": fixed_max}


def main():
    request = load_json_object(DEST / "validation_request.json")
    returned = DEST / "returned/output"
    records = []
    for model in request["models"]:
        for case in request["geometry_cases"]:
            reference = read_poscar(DEST / case["reference_path"])
            for origin in ("seed", "minimum"):
                path = returned / model / case["name"] / origin / "optimization.traj"
                records.append({"name": case["name"], "model": model, "origin": origin,
                                "trajectory_sha256": sha256_file(path), **audit(path, reference)})
    result = {"request_sha256": sha256_file(DEST / "validation_request.json"), "records": records,
        "total_frames": sum(r["frame_count"] for r in records), "new_GPU_or_VASP": False,
        "source_sha256": sha256_file(Path(__file__)), "graph_cutoff_is_diagnostic_not_scientific_acceptance": True}
    write_json_exclusive(DEST / "trajectory_audit.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
