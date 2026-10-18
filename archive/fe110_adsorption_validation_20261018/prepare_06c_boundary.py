"""Prepare three saved06_C ML boundary structures for review; never submit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import yaml
from ase.io import read, write

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import (
    connectivity, equivalent_pose_rmsd, pair_distances, surface_pose_symmetries,
)
from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.neb_agent.submission import preflight
from scripts.vasp_inputs import build_fe110_active_learning_force_label
from scripts.workflow_geometry import minimum_image_delta_xy

from .prepare import BASE, DEST as PREVIOUS, OLD, ROOT

DEST = BASE / "adsorption_06c_boundary_labels_20261018_v1"
PROFILE = ROOT / "configs/true_fe110_production.yaml"
TRAJECTORY = PREVIOUS / "returned/output/candidate/06_C/seed/optimization.traj"
CUSTODIAN = Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")


def validate_frame(atoms, initial) -> np.ndarray:
    if initial.get_chemical_symbols() != ["Fe"] * 45 + ["C", "C", "O", "H"]:
        raise ValueError("not the frozen49-atom06_C system")
    fixed = sorted(int(i) for constraint in atoms.constraints for i in constraint.get_indices())
    if atoms.get_chemical_symbols() != initial.get_chemical_symbols() or fixed != list(range(18)):
        raise ValueError("source atom order/fixed mask changed")
    if (not np.array_equal(atoms.cell, initial.cell) or not np.array_equal(atoms.pbc, initial.pbc)
            or not np.allclose(atoms.positions[:18], initial.positions[:18], atol=1e-12, rtol=0)):
        raise ValueError("source cell/PBC/fixed coordinates changed")
    forces = np.asarray(atoms.calc.results["forces"])
    if forces.shape != (len(atoms), 3) or not np.isfinite(forces).all() or not np.isfinite(atoms.positions).all():
        raise ValueError("nonfinite/incomplete saved ML frame")
    return forces


def scan(frames: list, template) -> tuple[list, list]:
    rows, poses = [], []
    for index, atoms in enumerate(frames):
        forces = validate_frame(atoms, frames[0])
        pose = replace(template, frac=atoms.get_scaled_positions(wrap=False))
        distances = np.linalg.norm(minimum_image_delta_xy(pose.frac[:, None] - pose.frac[None, :]) @ pose.cell, axis=2)
        np.fill_diagonal(distances, np.inf)
        step = minimum_image_delta_xy(pose.frac - poses[-1].frac) @ pose.cell if poses else np.zeros((len(atoms), 3))
        pairs = pair_distances(pose, list(range(45, len(atoms))))
        rows.append({"frame_index_0based": index, "ML_optimizer_step": index,
            "graph_adsorbate_local": connectivity(pose, list(range(45, len(atoms)))),
            "C45_O47_A": pairs[45, 47], "C46_O47_A": pairs[46, 47], "C45_H48_A": pairs[45, 48],
            "minimum_pair_distance_A": float(distances.min()), "minimum_Fe_adsorbate_A": float(distances[:45, 45:].min()),
            "ML_movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
            "adjacent_max_atom_displacement_MIC_A": float(np.linalg.norm(step, axis=1).max()),
            "nearest_Fe": [{"atom_index_0based": i, "symbol": atoms[i].symbol,
                "Fe_index_0based": int(np.argmin(distances[i, :45])), "distance_A": float(distances[i, :45].min())}
                for i in range(45, len(atoms))]})
        poses.append(pose)
    return rows, poses


def choose(rows: list) -> list[tuple[str, int]]:
    target = rows[0]["graph_adsorbate_local"]
    candidates = [i for i in range(1, len(rows)) if rows[i - 1]["graph_adsorbate_local"] == target
                  and all(r["graph_adsorbate_local"] != target for r in rows[i:])]
    if not candidates:
        raise ValueError("no persistent target-motif loss; do not invent a boundary")
    first = candidates[0]
    selected = [("before", first - 1), ("after", first), ("final", len(rows) - 1)]
    if len({index for _, index in selected}) != 3:
        raise ValueError("boundary and final are not three distinct frames")
    return selected


def source_review() -> tuple[dict, list, object, dict]:
    request = json.loads((PREVIOUS / "validation_request.json").read_bytes())
    returned = PREVIOUS / "returned"
    manifest = json.loads((returned / "return_manifest.json").read_bytes())
    entries = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    for relative in ("output/candidate/06_C/seed/optimization.traj", "output/candidate/06_C/seed/case_record.json", "output/candidate/06_C/seed/POSCAR"):
        if sha256_file(returned / relative) != entries[relative]:
            raise ValueError("saved source return changed")
    failure = json.loads((PREVIOUS / "failure_case.json").read_bytes())
    if (failure["model_sha256"] != request["models"]["candidate"]["sha256"]
            or failure["source_geometry_sha256"] != sha256_file(PREVIOUS / failure["source_geometry"])):
        raise ValueError("failure/checkpoint binding changed")
    seed = PREVIOUS / "geometry/06_C/seed.vasp"
    record = json.loads((TRAJECTORY.parent / "case_record.json").read_bytes())
    if sha256_file(seed) != record["source_structure_sha256"]:
        raise ValueError("raw seed changed")
    frames = read(TRAJECTORY, index=":")
    initial = read(seed, format="vasp")
    validate_frame(frames[0], initial)
    if not np.allclose(frames[0].positions, initial.positions, atol=1e-12, rtol=0):
        raise ValueError("trajectory does not start at frozen seed")
    if len(frames) != record["optimizer_steps"] + 1:
        raise ValueError("saved optimization frames are incomplete")
    source = ROOT / "calculations/fe110_c2_adsorption_06_10_20261012/vasp_batch_v1/06_C/submission_record.json"
    submission = json.loads(source.read_bytes())
    evidence = {"trajectory_sha256": sha256_file(TRAJECTORY), "source_request_sha256": sha256_file(PREVIOUS / "validation_request.json"),
        "failure_case_sha256": sha256_file(PREVIOUS / "failure_case.json"), "VASP_potcar_reference": {
            "source_record": str(source.relative_to(ROOT).as_posix()), "source_record_sha256": sha256_file(source),
            "source_job_id": submission["job_id"], "path": submission["potcar_source"], "sha256": submission["potcar_sha256"],
            "current_remote_hash_recheck_required": True}}
    return request, frames, read_poscar(seed), evidence


def reference_overlap(poses: list) -> dict:
    old_path = OLD / "training_manifest.json"
    manifest = json.loads(old_path.read_bytes())
    pool = BASE / "adsorption_calibration_20261018_v1/current_trajectories"
    pool_path = pool / "dataset_review.json"
    current = json.loads(pool_path.read_bytes())
    references = [(split, row["sample_id"], read_poscar(OLD / row["structure_path"]))
                  for split, rows in manifest["splits"].items() for row in rows if row["symbols"] == ["Fe"] * 45 + ["C", "C", "O", "H"]]
    references += [("untrained24", row["sample_id"], read_poscar(pool / row["structure_path"]))
                   for row in current["samples"] if row["symbols"] == ["Fe"] * 45 + ["C", "C", "O", "H"]]
    clean = read_poscar(ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    operations = surface_pose_symmetries(clean)
    tolerance = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"]
    result = []
    for pose in poses:
        best = {}
        for group, sample_id, reference in references:
            rmsd = equivalent_pose_rmsd(pose, reference, operations, remove_height_shift=False)
            if group not in best or rmsd < best[group]["adsorbate_RMSD_A"]:
                best[group] = {"sample_id": sample_id, "adsorbate_RMSD_A": rmsd}
        result.append({"nearest_by_dataset": best, "near_existing_heldout": best.get("heldout", {}).get("adsorbate_RMSD_A", float("inf")) <= tolerance})
    return {"prior_manifest_sha256": sha256_file(old_path), "untrained24_dataset_sha256": sha256_file(pool_path),
            "compatible_reference_count": len(references),
            "incompatible_composition_or_atom_order_excluded": len(current["samples"]) - sum(group == "untrained24" for group, _, _ in references),
            "near_warning_A": tolerance, "metric": "clean-slab symmetries;xyPBC;absolute height retained;no COM/Kabsch fit",
            "samples": result, "training_authorized": False, "independent_heldout": False}


def render(rows: list, frames: list, selected: list) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(10, 3.6), constrained_layout=True)
    for key, label in (("C46_O47_A", "C46-O47"), ("C45_H48_A", "C45-H48")):
        axes[0].plot([r["frame_index_0based"] for r in rows], [r[key] for r in rows], label=label)
    for role, index in selected:
        axes[0].scatter(index, rows[index]["C46_O47_A"], s=45)
        axes[0].annotate(role + " " + str(index), (index, rows[index]["C46_O47_A"]), xytext=(3, 5), textcoords="offset points", fontsize=8)
    axes[0].set(xlabel="ML optimizer step", ylabel="MIC bond distance (A)")
    axes[0].legend()
    axes[1].plot([r["frame_index_0based"] for r in rows], [r["ML_movable_fmax_eV_A"] for r in rows])
    axes[1].set(xlabel="ML optimizer step", ylabel="Stored ML movable fmax (eV/A)")
    figure.savefig(DEST / "boundary_trajectory.png", dpi=170)
    plt.close(figure)
    figure, axes = plt.subplots(2, 3, figsize=(11, 6), constrained_layout=True)
    colors = {"Fe": "#aaaeb5", "C": "#20242c", "O": "#d63b3b", "H": "#38a5d8"}
    for column, (role, index) in enumerate(selected):
        atoms = frames[index]
        frac = atoms.get_scaled_positions(wrap=False)
        cart = minimum_image_delta_xy(frac - frac[47]) @ atoms.cell + atoms.positions[47]
        top = np.argsort(atoms.positions[:45, 2])[-9:]
        for ax, dimensions, fe_indices in ((axes[0, column], (0, 1), top), (axes[1, column], (1, 2), range(45))):
            x, y = dimensions
            ax.scatter(cart[fe_indices, x], cart[fe_indices, y], color=colors["Fe"], s=70)
            for i in range(45, len(atoms)):
                ax.scatter(cart[i, x], cart[i, y], color=colors[atoms[i].symbol], s=80, edgecolor="white", zorder=3)
                ax.annotate(atoms[i].symbol + str(i), (cart[i, x], cart[i, y]), xytext=(4, 4), textcoords="offset points", fontsize=8)
            ax.set_aspect("equal")
            ax.set(xlabel="xyz"[x] + " (A)", ylabel="xyz"[y] + " (A)")
        axes[0, column].set_title(f"{role}, frame {index}\nC46-O47 {rows[index]['C46_O47_A']:.3f} A")
    figure.suptitle("Saved ML geometries; periodic display centered on O47 only")
    figure.savefig(DEST / "selected_structures.png", dpi=160)
    plt.close(figure)


def prepare() -> None:
    previous, frames, template, evidence = source_review()
    rows, poses = scan(frames, template)
    selected = choose(rows)
    overlaps = reference_overlap([poses[index] for _, index in selected])
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text(encoding="utf-8"))
    minimum = rules["contact_validation"]["hard_contact_distance_angstrom"]
    if any(rows[index]["minimum_pair_distance_A"] < minimum for _, index in selected):
        raise ValueError("selected frame has a verified hard collision")
    DEST.mkdir(exist_ok=False)
    prepared = []
    for (role, index), overlap in zip(selected, overlaps["samples"], strict=True):
        name = f"06C_{role}_{index:03d}"
        directory = DEST / name
        directory.mkdir(exist_ok=False)
        write(directory / "POSCAR", frames[index], format="vasp", direct=True, sort=False, vasp5=True)
        restored = read(directory / "POSCAR", format="vasp")
        delta = float(np.abs(restored.positions - frames[index].positions).max())
        if delta > 1e-12 or restored.get_chemical_symbols() != frames[index].get_chemical_symbols():
            raise ValueError("POSCAR serialization changed source geometry")
        fixed = sorted(int(i) for constraint in restored.constraints for i in constraint.get_indices())
        if fixed != list(range(18)) or not np.allclose(restored.cell, frames[index].cell, atol=1e-12, rtol=0):
            raise ValueError("POSCAR serialization changed cell/fixed mask")
        inputs = build_fe110_active_learning_force_label(directory, profile_path=PROFILE)
        write_json_exclusive(directory / "input_profile.json", inputs)
        checked = preflight(directory, "diagnostic_static")
        if not checked["passed"]:
            raise ValueError("static input preflight failed: " + repr(checked["errors"]))
        process = subprocess.run([sys.executable, str(CUSTODIAN), "--mode", "validate", "--workdir", str(directory),
            "--incar", str(directory / "INCAR"), "--poscar", str(directory / "POSCAR"), "--calculation-type", "adsorption_static",
            "--surface-family", "metal_fe", "--material", "Fe110", "--read-only"], capture_output=True, check=True)
        custody = json.loads(process.stdout)
        write_json_exclusive(directory / "custodian_readonly.json", custody)
        if custody["blockers"] or custody["changes"] or custody["status"] != "VALIDATION_ONLY":
            raise ValueError("custodian found a blocker or unexpected parameter change")
        force_evidence = {"checkpoint_sha256": previous["models"]["candidate"]["sha256"], "trajectory_sha256": evidence["trajectory_sha256"],
            "frame_index_0based": index, "raw_saved_forces_eV_per_A": validate_frame(frames[index], frames[0]).tolist(),
            "POSCAR_roundtrip_max_coordinate_delta_A": delta, "role": "stored_ML_prediction_not_DFT_label"}
        write_json_exclusive(directory / "source_ML_frame.json", force_evidence)
        request = {"sample_id": name, "role": role, "source_frame": rows[index], "overlap_review": overlap,
            "candidate_structure_sha256": sha256_file(directory / "POSCAR"), "requested_backend": "sunboquan-codex",
            "kind": "diagnostic_static", "result_class": "exact_structure_force_label_only", "eligible_for_training": False,
            "reportable_final_energy": False, "user_review_required": True, "submission_authorized": False}
        write_json_exclusive(directory / "label_request.json", request)
        prepared.append({"sample_id": name, "directory": name, "role": role, "frame_index_0based": index,
            "structure_sha256": request["candidate_structure_sha256"], "bundle_sha256": checked["bundle_sha256"],
            "input_hashes": checked["files"], "label_request_sha256": sha256_file(directory / "label_request.json")})
    selection = {"status": "GEOMETRY_REVIEW_REQUIRED_NOT_SUBMITTED", "evidence": evidence,
        "all_frames": rows, "selected": prepared, "overlap_review": overlaps,
        "graph_rule": "existing care-isomer connectivity;1.25*covalent-radii;descriptive sampling only,not a physical bond-breaking threshold",
        "external_retrieval": "local verified trajectory only;no new motif or external parameter",
        "geometry_scope": "finite/noncollision/order/cell/fixed-mask diagnostic eligibility,not accepted adsorption chemistry",
        "training_authorized": False}
    write_json_exclusive(DEST / "selection_review.json", selection)
    batch = {"document_kind": "adsorption_failure_boundary_static_label_batch", "status": "PREPARED_NOT_SUBMITTED",
        "samples": prepared, "source": evidence, "input_profile_sha256": sha256_file(PROFILE),
        "backend_policy_sha256": sha256_file(ROOT / "configs/execution_backends.yaml"), "cores_per_sample": inputs["cores"],
        "POTCAR": evidence["VASP_potcar_reference"], "remote_transfer_performed": False, "jobs_submitted": 0,
        "submission_authorized": False, "canonical_execution_gate_required": "SUBMIT_DIAGNOSTIC_VASP",
        "scientific_acceptance": False, "required_outputs": ["electronic_EDIFF_before_NELM", "normal_termination",
            "full_raw_all_atom_forces", "TOTEN_force_label_only", "total_and_atom_resolved_magnetic_moments", "exact_input_geometry_hash"],
        "before_submission": ["user_structure_review", "explicit_three_job_authorization", "current_canonical_execution_gate",
            "remote_POTCAR_hash_check", "duplicate_submission_check"], "training_performed": False}
    write_json_exclusive(DEST / "batch_request.json", batch)
    write_json_exclusive(DEST / "exact_prediction_plan.json", {"status": "LOCAL_PLAN_NOT_GPU_EXECUTABLE",
        "models": previous["models"], "samples": prepared, "geometry_optimization": False, "training": False,
        "fresh_exact_POSCAR_inference_required_before_error_assessment": True, "GPU_submission_authorized": False})
    render(rows, frames, selected)
    print(json.dumps({"status": batch["status"], "selected_frames": [i for _, i in selected],
        "samples": len(prepared), "jobs_submitted": 0, "all_local_preflights_passed": True}))


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    prepare()
