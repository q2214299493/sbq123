"""Bounded geometry/force diagnostic of the two existing 80-step C3 paths."""
from pathlib import Path

import numpy as np
from ase.io import iread, read

from scripts.adsmind_lite.relaxed_analysis import connectivity_edges
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar

from .collect import CASES, OUTPUT


if __name__ == "__main__":
    records = []
    for case in CASES:
        root = OUTPUT / case["job_id"]
        initial = read(root / "POSCAR", format="vasp")
        initial.pbc = [True, True, False]
        ads = list(range(45, len(initial)))
        initial_edges = connectivity_edges(initial, ads, 1.25, .35)
        frames = []
        for step, atoms in enumerate(iread(root / "OUTCAR", format="vasp-out", index=":"), 1):
            forces = atoms.get_forces(apply_constraint=False)
            atoms.pbc = [True, True, False]
            frames.append({"step": step, "fmax_movable_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
                           "initial_graph_preserved": connectivity_edges(atoms, ads, 1.25, .35) == initial_edges})
        summary = load_json_object(root / "review_precision_v2.json")
        osz = parse_oszicar(root / "OSZICAR")
        if len(frames) != osz["ionic_steps"] or not np.isclose(frames[-1]["fmax_movable_eV_A"], summary["fmax_movable_eV_A"], atol=1e-12, rtol=0):
            raise ValueError("trajectory/OSZICAR/final force alignment failed")
        intact = [row for row in frames if row["initial_graph_preserved"]]
        record = {"job_id": case["job_id"], "frames": frames, "intact_frame_count": len(intact),
                  "minimum_force_frame": min(frames, key=lambda row: row["fmax_movable_eV_A"]),
                  "minimum_force_intact_frame": min(intact, key=lambda row: row["fmax_movable_eV_A"]) if intact else None,
                  "intact_frames_below_0p05": sum(row["fmax_movable_eV_A"] <= .05 for row in intact),
                  "source_OUTCAR_sha256": sha256_file(root / "OUTCAR"),
                  "per_frame_electronic_convergence_reviewed": False}
        records.append(record)
        print({key: record[key] for key in ("job_id", "intact_frame_count", "minimum_force_intact_frame", "intact_frames_below_0p05")}, flush=True)
    write_json_exclusive(OUTPUT / "trajectory_diagnostic.json", {"cases": records,
                         "scope": "Force/geometry diagnostic only; every retained training frame still needs per-cycle SCF and magnetic review.",
                         "source_files": source_file_manifest([Path(__file__), Path("configs/adsmind_lite/analysis_rules.yaml")])})
