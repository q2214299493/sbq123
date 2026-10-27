"""Independent source/trajectory/input audit;does not run models or DFT."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from ase.io import read

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .prepare import OUTPUT, PACKAGE, ROOT


def check_sources(payload):
    for row in payload["source_files"]:
        if sha256_file(Path(row["path"])) != row["sha256"]:
            raise ValueError("review source changed")


def verify_results():
    request = load_json_object(PACKAGE / "request.json")
    review = load_json_object(OUTPUT / "geometry_review_v2.json")
    plan_path = OUTPUT / "dft_screen80/plan.json"
    plan = load_json_object(plan_path)
    for payload in [review, plan, load_json_object(OUTPUT / "postrun_review.json")]:
        check_sources(payload)
    expected = {(c["name"], m) for c in request["scope"]["cases"] for m in request["scope"]["models"]}
    if {(r["name"], r["model"]) for r in review["cases"]} != expected or {(j["name"], j["model"]) for j in plan["jobs"]} != expected:
        raise ValueError("paired case set changed")
    frame_count = 0
    fmax_verified = []
    for row in review["cases"]:
        case = next(c for c in request["scope"]["cases"] if c["name"] == row["name"])
        seed = read(PACKAGE / case["seed_path"], format="vasp")
        folder = OUTPUT / "returned/output" / row["model"] / row["name"] / "seed"
        trajectory = read(folder / "optimization.traj", index=":")
        for frame in trajectory:
            if frame.get_chemical_symbols() != seed.get_chemical_symbols() or not np.allclose(frame.cell, seed.cell, rtol=0, atol=1e-12):
                raise ValueError("trajectory species/order/cell changed")
            if not np.allclose(frame.positions[:18], seed.positions[:18], rtol=0, atol=1e-10):
                raise ValueError("fixed positions changed")
            forces = frame.get_forces(apply_constraint=False)
            if forces.shape != (len(seed), 3) or not np.isfinite(forces).all():
                raise ValueError("raw ML forces invalid")
        forces = trajectory[-1].get_forces(apply_constraint=False)
        maximum = max(sum(float(v)**2 for v in force)**0.5 for force in forces[18:])
        if not np.isclose(maximum, row["ML_movable_fmax_eV_A"], rtol=1e-6):
            raise ValueError("independent scalar fmax differs")
        frame_count += len(trajectory)
        fmax_verified.append({"case": row["name"], "model": row["model"], "scalar_fmax_eV_A": maximum})
    for job in plan["jobs"]:
        folder = ROOT / job["path"]
        for name, digest in job["files"].items():
            if sha256_file(folder / name) != digest:
                raise ValueError("prepared DFT input changed")
        poscar = read_poscar(folder / "POSCAR")
        if len(poscar.frac) not in [50, 51] or sum(flags == ("F", "F", "F") for flags in poscar.flags) != 18:
            raise ValueError("DFT fixed mask or composition changed")
    if frame_count != 247 or any(plan[k] for k in ["VASP_execution_authorized", "uploaded", "submitted"]):
        raise ValueError("scope or no-submission boundary changed")
    result = {"status": "PASS_PAIR2_SOURCE_TRAJECTORY_AND_DFT_INPUT_AUDIT", "frames": 247,
        "ML_cases": 4, "DFT_inputs": 4, "raw_force_fmax_scalar_replay": fmax_verified,
        "all_24_DFT_input_hashes_match": True, "atomic_order_cell_fixed_layers_verified_all_frames": True,
        "not_proven": ["DFT_convergence", "intact_C3_stability", "same_DFT_minimum", "acceleration_or_amortized_cost_recovery"],
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "geometry_review_v2.json", plan_path,
            OUTPUT / "postrun_review.json", OUTPUT / "primary_tests.xml", PACKAGE / "request.json"])}
    write_json_exclusive(OUTPUT / "independent_verification_v2.json", result)
    print({k: v for k, v in result.items() if k != "source_files"}, flush=True)


if __name__ == "__main__":
    verify_results()
