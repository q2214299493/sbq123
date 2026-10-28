"""Compare ML handoff accuracy and actual remaining DFT work,without fitting."""
from __future__ import annotations

import base64
from pathlib import Path
import re

import numpy as np
from ase.io import read

from archive.fe110_10b_lowforce_20261023.legacy_helpers import verify_frame
from archive.fe110_10b_lowforce_20261023.review import scf_for_frame
from archive.fe110_grouped_qc_20261026.review import force_table, magnetic_status
from archive.fe110_fixed53_comparison_20261027.analyze import force_metrics
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import read_incar_values
from scripts.workflow_geometry import minimum_image_delta_xy
from .collect import BASE, ML, SUBMITTED
from archive.fe110_pair2_20261027.review import fragment_formulas

OUTPUT = BASE / "paired_cost_comparison_20261028_v5"

THRESHOLDS = [0.10, 0.05, 0.02]


def threshold_work(frames, threshold):
    """First valid raw-force crossing is a diagnostic,not official convergence."""
    eligible = [f for f in frames if f["SCF_pass"] and f["magnetic_review_pass"]]
    crossing = next((f for f in eligible if f["DFT_movable_fmax_eV_A"] <= threshold), None)
    return {"threshold_eV_A": threshold, "first_valid_crossing_step": crossing["ionic_step"] if crossing else None,
        "cumulative_SCF_iterations_at_crossing": crossing["cumulative_SCF_iterations"] if crossing else None,
        "minimum_valid_fmax_eV_A": min((f["DFT_movable_fmax_eV_A"] for f in eligible), default=None),
        "official_convergence_implied": False}


def frame_checks(extracted, directory):
    values = read_incar_values(directory / "INCAR")
    osz = parse_oszicar(directory / "OSZICAR")
    cycles = {c["ionic_step"]: c for c in osz["electronic_cycles"] if c["ionic_step"] is not None}
    counts = osz["scf_iterations"]
    rows = []
    for frame in extracted["frames"]:
        step = frame["ionic_step"]
        if step > len(counts):
            continue  # A live-file snapshot never admits a cycle not completed in OSZICAR.
        error = None
        try:
            scf_for_frame(frame, cycles.get(step), values)
        except ValueError as exc:
            error = str(exc)
        magnetic = magnetic_status(frame["local_moment_tables"], extracted["row"]["atom_count"])
        if abs(frame["toten_eV"] - osz["energies"][step - 1]) > 1e-4:
            raise ValueError("ionic energy association mismatch")
        rows.append({"ionic_step": step, "DFT_movable_fmax_eV_A": frame["movable_fmax_eV_A"],
            "DFT_adsorbate_fmax_eV_A": frame["adsorbate_fmax_eV_A"], "SCF_iterations": counts[step - 1],
            "cumulative_SCF_iterations": sum(counts[:step]), "SCF_pass": error is None, "SCF_error": error,
            "magnetic_review_pass": not magnetic["magnetic_review_flags"], "Fe_local_moment_range_muB": magnetic["Fe_moment_range_muB"],
            "total_magnetization_muB": osz["magnetization_history_muB"][step - 1],
            "raw_force_table_sha256": frame["raw_force_table_sha256"], "source_byte_range": frame["source_byte_range"]})
    if not rows or [r["ionic_step"] for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("missing or reordered complete force cycles")
    return rows


def handoff(extracted, directory):
    row = extracted["row"]
    initial = read(directory / "POSCAR", format="vasp")
    first = extracted["frames"][0]
    raw = base64.b64decode(first["raw_force_table_base64"], validate=True)
    import hashlib
    if hashlib.sha256(raw).hexdigest() != first["raw_force_table_sha256"]:
        raise ValueError("initial raw force-table bytes changed")
    _, values, _ = force_table(raw.splitlines(keepends=True), 0, len(initial))
    reference = verify_frame(initial, first)
    if not np.array_equal(reference, np.asarray(values)[:, 3:]):
        raise ValueError("independent raw-table force replay differs")
    trajectory = ML / "returned/output" / row["model"] / row["name"] / "seed/optimization.traj"
    final = read(trajectory, index=-1)
    if initial.get_chemical_symbols() != final.get_chemical_symbols() or not np.allclose(initial.cell, final.cell, atol=1e-12, rtol=0):
        raise ValueError("ML/DFT atom order or cell differs")
    delta = minimum_image_delta_xy(initial.get_scaled_positions(wrap=False) - final.get_scaled_positions(wrap=False)) @ initial.cell.array
    if np.max(np.abs(delta)) > 1e-10:
        raise ValueError("ML final and DFT first calculation are not the same geometry")
    predicted = final.get_forces(apply_constraint=False)
    free, ads = list(range(18, len(initial))), list(range(45, len(initial)))
    symbols = initial.get_chemical_symbols()
    worst = 18 + int(np.argmax(np.linalg.norm(reference[18:], axis=1)))
    return {"geometry_verified_same": True, "maximum_ML_DFT_coordinate_difference_A": float(np.max(np.abs(delta))),
        "ML_predicted_movable_fmax_eV_A": float(np.linalg.norm(predicted[free], axis=1).max()),
        "DFT_same_geometry_movable_fmax_eV_A": float(np.linalg.norm(reference[free], axis=1).max()),
        "DFT_same_geometry_adsorbate_fmax_eV_A": float(np.linalg.norm(reference[ads], axis=1).max()),
        "movable_force_error": force_metrics(reference[free], predicted[free]),
        "adsorbate_force_error": force_metrics(reference[ads], predicted[ads]),
        "DFT_max_force_atom": {"index_0based": worst, "element": symbols[worst]},
        "ML_trajectory_sha256": sha256_file(trajectory), "DFT_first_force_table_sha256": first["raw_force_table_sha256"]}


def endpoint_geometry(directory):
    """Snapshot chemistry/fixed-layer checks;not minimum or endpoint acceptance."""
    initial, final = [read_poscar(directory / name) for name in ["POSCAR", "CONTCAR"]]
    if initial.symbols != final.symbols or initial.counts != final.counts or initial.flags != final.flags:
        raise ValueError("DFT atom order or fixed mask changed")
    if not np.allclose(initial.cell, final.cell, atol=1e-10, rtol=0):
        raise ValueError("DFT cell changed")
    delta = minimum_image_delta_xy(final.frac - initial.frac) @ initial.cell
    fixed = float(np.linalg.norm(delta[:18], axis=1).max())
    distances = np.linalg.norm(minimum_image_delta_xy(final.frac[:, None] - final.frac[None]) @ final.cell, axis=2)
    np.fill_diagonal(distances, np.inf)
    ads = list(range(45, len(initial.frac)))
    symbols = [s for s, n in zip(final.symbols, final.counts, strict=True) for _ in range(n)][45:]
    return {"fixed_max_displacement_A": fixed, "minimum_pair_distance_A": float(distances.min()),
        "input_adsorbate_graph_preserved": sorted(connectivity(initial, ads)) == sorted(connectivity(final, ads)),
        "fragment_formulas": fragment_formulas(symbols, connectivity(final, ads)),
        "CONTCAR_sha256": sha256_file(directory / "CONTCAR"), "accepted_endpoint": False,
        "scope": "CONTCAR snapshot only;live CONTCAR is not asserted to equal last conservative OUTCAR prefix frame"}


def case_result(directory, submitted):
    extracted = load_json_object(directory / "extracted.json")
    row = extracted["row"]
    for name, saved in extracted["files"].items():
        if sha256_file(directory / name) != saved["sha256"]:
            raise ValueError("returned file hash changed")
    item = next(j for j in submitted["jobs"] if (j["name"], j["model"]) == (row["name"], row["model"]))
    for name in ["POSCAR", "INCAR", "KPOINTS"]:
        if sha256_file(directory / name) != item["files"][name] or sha256_file(directory / name) != extracted["files"][name]["sha256"]:
            raise ValueError("submitted geometry or numerical method changed")
    frames = frame_checks(extracted, directory)
    initial = handoff(extracted, directory)
    first = frames[0]
    initial["SCF_pass"] = first["SCF_pass"]
    initial["magnetic_review_pass"] = first["magnetic_review_pass"]
    header = base64.b64decode(extracted["header_base64"]).decode(errors="replace")
    tail = base64.b64decode(extracted["tail_base64"]).decode(errors="replace")
    ranks = re.search(r"running on\s+(\d+) total cores", header)
    elapsed = re.search(r"Elapsed time \(sec\):\s*([\d.]+)", tail)
    cores = int(ranks[1]) if ranks else None
    if cores != 32:
        raise ValueError("actual VASP MPI resource count changed")
    elapsed_seconds = float(elapsed[1]) if elapsed and extracted["normal_completion_footer"] else None
    success = bool(extracted["normal_completion_footer"] and extracted["ionic_accuracy_marker"]
        and frames[-1]["DFT_movable_fmax_eV_A"] <= .02 and all(f["SCF_pass"] and f["magnetic_review_pass"] for f in frames))
    return {"name": row["name"], "model": row["model"], "job_id": row["job_id"], "scheduler_state_at_snapshot": extracted["state"],
        "handoff": initial, "audited_completed_DFT_steps": len(frames), "normal_completion": extracted["normal_completion_footer"],
        "official_ionic_accuracy_marker": extracted["ionic_accuracy_marker"], "last_audited_fmax_eV_A": frames[-1]["DFT_movable_fmax_eV_A"],
        "force_and_electronic_target_completed": success, "SCF_valid_steps": sum(f["SCF_pass"] for f in frames),
        "magnetic_valid_steps": sum(f["magnetic_review_pass"] for f in frames), "completed_SCF_iterations": frames[-1]["cumulative_SCF_iterations"],
        "thresholds": [threshold_work(frames, t) for t in THRESHOLDS], "DFT_target_reached_within30": success and len(frames) <= 30,
        "DFT_target_reached_within50": success and len(frames) <= 50, "actual_MPI_ranks": cores, "VASP_elapsed_seconds": elapsed_seconds,
        "allocated_CPU_core_hours": elapsed_seconds * cores / 3600 if elapsed_seconds is not None else None,
        "cost_scope": "completed VASP elapsed*MPI ranks;queue,ML,training and label costs excluded;not a pure-DFT baseline speedup",
        "OUTCAR_source": extracted["OUTCAR"], "frames": frames, "endpoint_geometry": endpoint_geometry(directory),
        "magnetic_review_level": "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE" if all(f["magnetic_review_pass"] for f in frames) else "NEEDS_MAGNETIC_REVIEW",
        "magnetic_global_ground_state_verified": False,
        "source_files": source_file_manifest([directory / "extracted.json", directory / "POSCAR", directory / "OSZICAR", directory / "INCAR"])}


def analyze():
    collection = load_json_object(OUTPUT / "collection.json")
    if collection["status"] != "COMPLETE":
        raise ValueError("four complete case snapshots required")
    submitted = load_json_object(SUBMITTED / "ready_for_submission.json")
    cases = [case_result(OUTPUT / "snapshots" / job["name"] / job["model"], submitted) for job in submitted["jobs"]]
    result = {"status": "HANDOFF_AND_REMAINING_DFT_WORK_COMPARED_NO_SPEEDUP_PROVEN", "cases": cases,
        "DFT_force_target_eV_A": .02, "ML_stop_force_eV_A": .10, "ML_step_cap": 80,
        "primary_success_is_DFT_target_not_small_ML_force": True,
        "pure_DFT_same_raw_seed_control_in_this_batch": False, "no_model_promotion_or_training_data_admission": True,
        "source_files": source_file_manifest([Path(__file__), OUTPUT / "collection.json", SUBMITTED / "ready_for_submission.json"])}
    write_json_exclusive(OUTPUT / "analysis.json", result)
    for case in cases:
        print({k: case[k] for k in ["name", "model", "job_id", "audited_completed_DFT_steps", "last_audited_fmax_eV_A", "SCF_valid_steps", "magnetic_valid_steps", "completed_SCF_iterations", "force_and_electronic_target_completed", "allocated_CPU_core_hours"]}, flush=True)
        print("handoff", case["handoff"], "thresholds", case["thresholds"], flush=True)


if __name__ == "__main__":
    analyze()
