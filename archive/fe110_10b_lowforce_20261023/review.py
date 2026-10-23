"""Review an isolated legacy force supplement; never train or modify frozen pools."""
from __future__ import annotations

import base64
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import yaml
from ase.io import read, write

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_isomers import connectivity, surface_pose_symmetries
from scripts.adsorption.force_finetune import validate_label_row
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.artifact_io import sha256_file, source_file_manifest, write_json_exclusive
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import final_scf_state, read_incar_values

from .collect import OUTPUT, PRIOR, ROOT, SUBMISSION, reader_source, selected_steps, source_record
from .legacy_helpers import check_inputs, restore_input_lattice, verify_frame, collapse_redundant, pose_distance, pose_variants


def restore_sources(source, record):
    raw = OUTPUT / "raw"
    raw.mkdir(exist_ok=False)
    for name, encoded in source["files"].items():
        if name not in {"POSCAR", "CONTCAR", "INCAR", "KPOINTS", "OSZICAR", "XDATCAR"}:
            raise ValueError("unexpected extracted filename")
        (raw / name).write_bytes(base64.b64decode(encoded, validate=True))
    check_inputs(raw, record)
    return raw


def scf_for_frame(frame, cycle, values):
    """Apply the existing SCF interpreter to this exact completed ionic cycle."""
    if (not cycle or not cycle["complete"] or cycle["malformed"]
            or cycle["ionic_step"] != frame["ionic_step"]
            or cycle["iteration"] != frame["electronic_iteration"]
            or frame["EDIFF_marker_before_force"] is not True
            or cycle["iteration"] >= int(values["NELM"])):
        raise ValueError("SCF frame/cycle/explicit-EDIFF association failed")
    parsed = {"latest_started_electronic_cycle": cycle, "latest_completed_electronic_cycle": cycle,
              "final_target_complete": True}
    out = {"exists": True, "final_target_step": cycle, "incomplete": False,
           "electronic_convergence_reached": True}
    result = final_scf_state(parsed, values, out)
    if not result["electronically_converged"]:
        raise ValueError("canonical SCF check failed")
    return result


def magnetic_review(moments, total_steps, steps, local_tables):
    if len(moments) != total_steps or not np.isfinite(moments).all():
        raise ValueError("total magnetization cannot be associated with every ionic frame")
    window = np.asarray(moments[min(steps)-1:max(steps)], dtype=float)
    if np.any(window <= 0):
        raise ValueError("late-window total magnetization requires branch review")
    return {"level": "LEGACY_TOTAL_MAGNETIZATION_ONLY", "local_moment_table_count": local_tables,
            "local_Fe_signs_verified": False, "global_magnetic_ground_state_verified": False,
            "selected_total_moments_muB": {str(s): moments[s-1] for s in steps},
            "late_window_total_range_muB": [float(window.min()), float(window.max())],
            "maximum_adjacent_late_window_change_muB": float(np.abs(np.diff(window)).max()),
            "strict_new_static_local_moment_QC_passed": False}


def main():
    if (OUTPUT / "review_summary.json").exists():
        raise ValueError("completed review is immutable; choose a new checkpoint")
    source_path = OUTPUT / "source.json"
    receipt = json.loads((OUTPUT / "collection_receipt.json").read_bytes())
    record = source_record()
    if (receipt["exit_code"] or receipt["output_sha256"] != sha256_file(source_path)
            or receipt["reader_sha256"] != hashlib.sha256(reader_source(record).encode()).hexdigest()):
        raise ValueError("source/reader receipt changed")
    source = json.loads(source_path.read_bytes())
    previous = json.loads(PRIOR.read_bytes())
    if (source["record"] != record or source["OUTCAR_sha256"] != previous["OUTCAR_sha256"]
            or source["POTCAR_sha256"] != record["potcar_sha256"] or not source["normal_completion"]
            or not source["ionic_converged"]):
        raise ValueError("closed-source/compatibility binding failed")
    raw = restore_sources(source, record)
    values = read_incar_values(raw / "INCAR")
    initial = read(raw / "POSCAR", format="vasp")
    trajectory = read(raw / "XDATCAR", format="vasp-xdatcar", index=":")
    osz = parse_oszicar(raw / "OSZICAR")
    steps = selected_steps(source["total_steps"])
    if len(trajectory) != source["total_steps"] or osz["ionic_steps"] != len(trajectory):
        raise ValueError("XDATCAR/OSZICAR trajectory lengths differ")
    if [f["ionic_step"] for f in source["frames"]] != steps:
        raise ValueError("selection changed")
    magnetism = magnetic_review(osz["magnetization_history_muB"], len(trajectory), steps,
                                source["local_moment_table_count"])
    cycles = {c["ionic_step"]: c for c in osz["electronic_cycles"]}
    if [c["ionic_step"] for c in osz["electronic_cycles"]] != list(range(1, len(trajectory)+1)):
        raise ValueError("restarted or duplicate OSZICAR cycle identity")
    intended = sorted(connectivity(read_poscar(raw / "POSCAR"), list(range(45, 50))))
    clean_path = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    slab = read_poscar(clean_path)
    operations = surface_pose_symmetries(slab)
    cfg_path = ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json"
    cfg = json.loads(cfg_path.read_bytes())
    prior_path = ROOT / cfg["prior_manifest"]
    prior = json.loads(prior_path.read_bytes())
    inventory = json.loads((ROOT / cfg["inventory"]).read_bytes())
    reserved = reserved_geometries(inventory, prior, prior_path.parent, cfg["reserved_geometry_catalogs"])
    protected_jobs = {str(r.get("source_job_id")) for r, _ in reserved}
    if record["job_id"] in protected_jobs:
        raise ValueError("whole-job reserved leakage")
    reserved_variants = [(r["sample_id"], pose_variants(read_poscar(Path(r["structure_path"])), operations))
                         for r, a in reserved if Counter(a.get_chemical_symbols()) == Counter(initial.get_chemical_symbols())]
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    rows, diagnostics, poses, variants = [], [], {}, {}
    (OUTPUT / "structures").mkdir(exist_ok=False)
    for frame in source["frames"]:
        step = frame["ionic_step"]
        scf = scf_for_frame(frame, cycles.get(step), values)
        atoms = trajectory[step-1]
        restore_input_lattice(atoms, initial, raw / "XDATCAR")
        atoms.set_constraint(initial.constraints)
        atoms.pbc = [True, True, False]
        forces = verify_frame(atoms, frame)
        if abs(frame["toten_eV"]-osz["energies"][step-1]) > 1e-4:
            raise ValueError("energy/frame mismatch")
        fixed_delta = atoms.get_scaled_positions(wrap=False)[:18]-slab.frac[:18]
        fixed_delta[:, :2] -= np.round(fixed_delta[:, :2])
        if not np.allclose(atoms.cell, slab.cell, atol=1e-8, rtol=0) or np.max(np.abs(fixed_delta @ slab.cell)) > 1e-7:
            raise ValueError("fixed-layer/cell mismatch")
        distances = atoms.get_all_distances(mic=True)
        np.fill_diagonal(distances, np.inf)
        if distances.min() < rules["contact_validation"]["hard_contact_distance_angstrom"]:
            raise ValueError("hard atomic contact")
        sid = f"10_B_step{step:03d}"
        path = OUTPUT / "structures" / (sid + ".vasp")
        write(path, atoms, format="vasp", direct=True, vasp5=True)
        pose = read_poscar(path)
        if sorted(connectivity(pose, list(range(45, 50)))) != intended:
            raise ValueError("selected frame no longer has intact target graph")
        table = raw / (sid + "_force_table.txt")
        table.write_bytes(base64.b64decode(frame["force_table_base64"], validate=True))
        nearest = sorted((pose_distance(pose, v), name) for name, v in reserved_variants)
        conflicts = [name for distance, name in nearest if distance <= .20]
        diagnostics.append({"sample_id": sid, "SCF": scf, "total_magnetization_muB": osz["magnetization_history_muB"][step-1],
            "reserved_geometry_conflicts": conflicts, "nearest_reserved": nearest[:1],
            "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max())})
        if conflicts:
            continue
        rows.append({"sample_id": sid, "structure_path": str(path.relative_to(OUTPUT)), "structure_sha256": sha256_file(path),
            "source_name": "10_B", "source_job_id": record["job_id"], "calculation_group": "current_vasp_job_9848812",
            "split": "train", "origin": "expanded_closed_trajectory", "ionic_step": step, "source_total_steps": len(trajectory),
            "symbols": atoms.get_chemical_symbols(), "fixed_atom_indices_0based": list(range(18)),
            "forces_eV_per_A": forces.tolist(), "energy_eV_force_label_only": frame["toten_eV"], "toten_eV_force_label_only": frame["toten_eV"],
            "source_OUTCAR_sha256": source["OUTCAR_sha256"], "source_XDATCAR_sha256": sha256_file(raw / "XDATCAR"),
            "source_force_table_sha256": sha256_file(table), "electronic_converged": True, "geometry_review_pass": True,
            "original_graph_preserved": True, "movable_fmax_eV_A": diagnostics[-1]["movable_fmax_eV_A"],
            "total_magnetization_muB": diagnostics[-1]["total_magnetization_muB"], "magnetic_review_level": magnetism["level"],
            "accepted_endpoint": False, "reportable_final_energy": False, "training_authorized": False})
        poses[sid], variants[sid] = pose, pose_variants(pose, operations)
    kept, redundant = collapse_redundant(sorted(rows, key=lambda r: -r["ionic_step"]),
        lambda a, b: pose_distance(poses[a["sample_id"]], variants[b["sample_id"]]))
    labels_path = OUTPUT / "candidate_labels.json"
    write_json_exclusive(labels_path, {"samples": rows, "magnetic_review": magnetism})
    for row in kept:
        row["label_source"] = {"path": labels_path.name, "sha256": sha256_file(labels_path), "sample_id": row["sample_id"]}
        validate_label_row(OUTPUT, row)
    write_json_exclusive(OUTPUT / "force_supplement.json", {"document_kind": "reviewed_legacy_adsorption_force_supplement",
        "samples": kept, "training_target": "forces_only", "energy_loss_coefficient": 0, "training_authorized": False,
        "magnetic_review_level": magnetism["level"], "merged_into_existing_manifest": False})
    files = [Path(__file__), Path(__file__).with_name("collect.py"), Path(__file__).with_name("legacy_helpers.py"), source_path, OUTPUT / "collection_receipt.json",
             SUBMISSION, PRIOR, cfg_path, prior_path, ROOT / cfg["inventory"], clean_path, rules_path,
             labels_path, OUTPUT / "force_supplement.json", ROOT / "docs/reviews/fe110_adsorption_pool_rebuild_20261019.md",
             ROOT / "scripts/neb_agent/utils_vasp.py", ROOT / "scripts/vasp_result_gate.py"]
    summary = {"status": "LEGACY_FORCE_SUPPLEMENT_REVIEWED", "extracted_frames": len(steps), "frame_reviews": diagnostics,
        "retained_force_candidates": len(kept), "retained_sample_ids": [r["sample_id"] for r in kept],
        "redundant_same_job_frames": redundant, "magnetic_review": magnetism,
        "reserved_geometries": len(reserved), "same_composition_reserved_geometries": len(reserved_variants),
        "isolation": "clean-Fe110 symmetry,XY PBC,all same-element permutations;conservative adsorbate-only RMSD<=0.20A exclusion",
        "reserved_labels_used": False, "strict_new_static_local_moment_QC_passed": False,
        "decision": "Retain an isolated legacy force-only supplement under the existing20261019 trajectory review scope;do not classify as local-moment-complete new statics or merge frozen packages.",
        "new_DFT_or_GPU_or_training": False, "source_files": source_file_manifest(files)}
    write_json_exclusive(OUTPUT / "review_summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("status", "extracted_frames", "retained_force_candidates", "retained_sample_ids", "magnetic_review")}), flush=True)


if __name__ == "__main__":
    main()
