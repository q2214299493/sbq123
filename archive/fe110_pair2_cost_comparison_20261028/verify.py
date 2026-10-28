"""Independently replay raw handoff scalars and threshold/cost arithmetic."""
import base64
import hashlib
import math
from pathlib import Path

from ase.io import read

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar
from .analyze import OUTPUT
from .collect import ML


def verify():
    analysis = load_json_object(OUTPUT / "analysis.json")
    checks = 0
    for result in analysis["cases"]:
        directory = OUTPUT / "snapshots" / result["name"] / result["model"]
        extracted = load_json_object(directory / "extracted.json")
        raw = base64.b64decode(extracted["frames"][0]["raw_force_table_base64"], validate=True)
        if hashlib.sha256(raw).hexdigest() != result["handoff"]["DFT_first_force_table_sha256"]:
            raise ValueError("raw force table binding failed")
        numbers = [list(map(float, line.split())) for line in raw.splitlines() if len(line.split()) == 6]
        forces = [row[3:] for row in numbers]
        expected = max(math.sqrt(sum(x*x for x in row)) for row in forces[18:])
        if not math.isclose(expected, result["handoff"]["DFT_same_geometry_movable_fmax_eV_A"], abs_tol=1e-14):
            raise ValueError("independent raw force maximum mismatch")
        model = read(ML / "returned/output" / result["model"] / result["name"] / "seed/optimization.traj", index=-1)
        predicted = model.get_forces(apply_constraint=False).tolist()
        squared = [sum((a-b)**2 for a, b in zip(ref, pred, strict=True)) for ref, pred in zip(forces[18:], predicted[18:], strict=True)]
        if not math.isclose(math.sqrt(sum(squared)/len(squared)), result["handoff"]["movable_force_error"]["vector_rmse_eV_A"], abs_tol=1e-14):
            raise ValueError("independent force RMSE mismatch")
        osz = parse_oszicar(directory / "OSZICAR")
        count = result["audited_completed_DFT_steps"]
        if sum(osz["scf_iterations"][:count]) != result["completed_SCF_iterations"]:
            raise ValueError("independent cumulative SCF mismatch")
        for threshold in result["thresholds"]:
            selected = [f for f in result["frames"] if f["SCF_pass"] and f["magnetic_review_pass"] and f["DFT_movable_fmax_eV_A"] <= threshold["threshold_eV_A"]]
            step = min((f["ionic_step"] for f in selected), default=None)
            if step != threshold["first_valid_crossing_step"]:
                raise ValueError("independent first-passage mismatch")
            checks += 1
        elapsed = result["VASP_elapsed_seconds"]
        if elapsed is not None and not math.isclose(elapsed * 32 / 3600, result["allocated_CPU_core_hours"], abs_tol=1e-10):
            raise ValueError("cost arithmetic mismatch")
        geometry = result["endpoint_geometry"]
        if geometry["fixed_max_displacement_A"] > 1e-7 or not geometry["input_adsorbate_graph_preserved"] or geometry["minimum_pair_distance_A"] < .8:
            raise ValueError("CONTCAR snapshot needs geometry review")
        if result["force_and_electronic_target_completed"] or result["official_ionic_accuracy_marker"]:
            raise ValueError("this frozen checkpoint cannot support a successful convergence claim")
        checks += 7
    receipt = {"status": "PASS", "independent_scalar_checks": checks,
        "first_force_tables_replayed": 4, "per_frame_SCF_and_moment_associations": sum(len(c["frames"]) for c in analysis["cases"]),
        "scope": "independent raw handoff vectors and cost/threshold arithmetic;later force curves use source-bound owner extraction,not full raw-vector replay",
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "analysis.json"])}
    write_json_exclusive(OUTPUT / "verification.json", receipt)
    print({k: v for k, v in receipt.items() if k != "source_files"})


if __name__ == "__main__":
    verify()
