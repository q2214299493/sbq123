"""Bounded raw-label audit of12statics and two closed80-step trajectories."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import numpy as np
import yaml
from ase.geometry import find_mic
from ase.io import read, write

from archive.fe110_10b_lowforce_20261023.legacy_helpers import (
    collapse_redundant, restore_input_lattice, verify_frame,
)
from archive.fe110_10b_lowforce_20261023.review import scf_for_frame
from archive.fe110_combined_force_package_20261023.prepare import isolate
from archive.fe110_reico_followup_20261024.collect import save_once
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.force_finetune import validate_label_row
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.adsorption.reico_probe_review import validate_static
from scripts.adsorption.reico_selection import frame_distance
from scripts.artifact_io import (
    load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid,
)
from scripts.neb_agent.utils_vasp import LOCAL_MAGNETIZATION_ROW_PATTERN, parse_oszicar, parse_outcar
from scripts.vasp_result_gate import read_incar_values
from .collect import BASE, FILES, INPUT, OUTPUT, ROOT, scope

FROZEN = BASE / "combined_force_package_20261023_v2/training_manifest.json"
AUDIT = BASE / "joint_update_20261025_v1/audit_training_view_local_only.json"
RULES = ROOT / "configs/adsmind_lite/analysis_rules.yaml"


def moment_table(lines, start, atom_count):
    values, indices = [], []
    j = start + 1
    while j < len(lines):
        match = LOCAL_MAGNETIZATION_ROW_PATTERN.match(lines[j].decode("ascii"))
        if match:
            indices.append(int(match.group(1)))
            values.append(float(match.group(2)))
        elif values:
            break
        j += 1
    if indices != list(range(1, atom_count + 1)):
        raise ValueError("incomplete or reordered local-moment table")
    return j, values


def force_table(lines, start, atom_count):
    j, rows, tokens = start + 1, [], []
    while j < len(lines):
        fields = lines[j].split()
        if len(fields) == 6:
            try:
                values = [float(v) for v in fields]
            except ValueError:
                values = None
            if values is not None:
                rows.append(values)
                tokens.append([v.decode("ascii") for v in fields[:3]])
        elif rows:
            break
        j += 1
    if len(rows) != atom_count:
        raise ValueError("incomplete force table")
    return j, rows, tokens


def raw_frames(path, atom_count):
    """Associate byte-exact force/moment tables with their OUTCAR ionic index.

    Archival adapter only. SCF admission and coordinate precision are delegated
    to the existing owners, with independent ASE/XDATCAR checks below.
    """
    lines = path.read_bytes().splitlines(keepends=True)
    offsets = np.cumsum([0] + [len(line) for line in lines]).tolist()
    frames, active = [], None
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.search(rb"Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)", line)
        if match:
            step, iteration = map(int, match.groups())
            if active is None or step != active["ionic_step"]:
                active = {"ionic_step": step, "local_moment_tables": [], "EDIFF_marker_before_force": False}
                frames.append(active)
            active["electronic_iteration"] = iteration
            active["EDIFF_marker_before_force"] = False
        if active is not None:
            if b"aborting loop because EDIFF is reached" in line:
                active["EDIFF_marker_before_force"] = True
            if b"magnetization (x)" in line:
                j, values = moment_table(lines, i, atom_count)
                active["local_moment_tables"].append(values)
                i = j - 1
            if b"TOTAL-FORCE (eV/Angst)" in line:
                if "forces_eV_per_A" in active:
                    raise ValueError("duplicate force table in one ionic cycle")
                j, rows, tokens = force_table(lines, i, atom_count)
                active.update(positions_A=[r[:3] for r in rows], forces_eV_per_A=[r[3:] for r in rows],
                              position_tokens=tokens, source_byte_range=[offsets[i], offsets[j]],
                              raw_force_table=b"".join(lines[i:j]))
                i = j - 1
            if b"free  energy   TOTEN" in line and "forces_eV_per_A" in active:
                active["toten_eV"] = float(line.split()[4])
        i += 1
    if [f["ionic_step"] for f in frames] != list(range(1, len(frames) + 1)):
        raise ValueError("restarted or missing ionic cycle")
    return frames


def magnetic_status(tables, atom_count):
    values = np.asarray(tables, dtype=float)
    if values.ndim != 2 or values.shape[1] != atom_count or not len(values) or not np.isfinite(values).all():
        raise ValueError("missing/nonfinite per-frame local moments")
    flags = [] if np.all(values[:, :45] > 0) else ["NONPOSITIVE_FE_LOCAL_MOMENT_REQUIRES_BRANCH_REVIEW"]
    return {"local_magnetization_muB": values[-1].tolist(), "local_moment_table_count": len(values),
            "Fe_moment_range_muB": [float(values[:, :45].min()), float(values[:, :45].max())],
            "magnetic_review_flags": flags,
            "magnetic_review_level": "NEEDS_MAGNETIC_REVIEW" if flags else "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE",
            "magnetic_global_ground_state_verified": False}


def base_row(receipt, case, sid, structure, step, outcar_hash):
    return {"sample_id": sid, "family_id": receipt["sample_id"].split("_step")[0],
            "source_seed": receipt["sample_id"], "source_job_id": receipt["job_id"],
            "calculation_group": "reico_" + receipt["sample_id"].split("_step")[0],
            "composition": case["composition"], "partition": "train", "split": "train",
            "ionic_step": step, "source_OUTCAR_sha256": outcar_hash,
            "structure_path": str(structure.relative_to(OUTPUT)), "structure_sha256": sha256_file(structure),
            "accepted_endpoint": False, "reportable_final_energy": False, "training_authorized": False}


def geometry(atoms, initial, rules):
    if atoms.get_chemical_symbols() != initial.get_chemical_symbols() or not np.allclose(atoms.cell, initial.cell, atol=1e-10, rtol=0):
        raise ValueError("atom order or cell changed")
    _, moves = find_mic(atoms.positions - initial.positions, atoms.cell, pbc=[True, True, False])
    if max(moves[:18]) > 1e-7:
        raise ValueError("fixed layer moved")
    distances = atoms.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    if distances.min() < rules["contact_validation"]["hard_contact_distance_angstrom"]:
        raise ValueError("hard atomic overlap")
    return {"minimum_pair_distance_A": float(distances.min()), "fixed_max_displacement_A": float(max(moves[:18])),
            **chemical_environment(atoms, rules["connectivity"])}


def check_collection(receipt):
    directory = OUTPUT / "collection" / receipt["sample_id"]
    collected = load_json_object(directory / "collection.json")
    case = load_json_object(INPUT / receipt["role"] / receipt["sample_id"] / "prepared_case.json")
    if case["partition"] != "train" or collected["job_id"] != receipt["job_id"]:
        raise ValueError("scope/partition changed")
    names = list(FILES) + (["XDATCAR"] if receipt["role"] == "optimizations" else [])
    for name in names:
        if sha256_file(directory / name) != collected["remote"]["files"][name]["sha256"]:
            raise ValueError("raw collection changed " + name)
    for name in ("INCAR", "POSCAR", "KPOINTS"):
        if sha256_file(directory / name) != case["input_hashes"][name]:
            raise ValueError("source input differs from submission")
    return directory, case, collected


def review_static(receipt, rules):
    directory, case, collected = check_collection(receipt)
    atoms = read(directory / "POSCAR", format="vasp")
    atoms.pbc = [True, True, False]
    row = base_row(receipt, case, receipt["sample_id"], directory / "POSCAR", 1,
                   collected["remote"]["files"]["OUTCAR"]["sha256"])
    row.update(origin="new_static", symbols=atoms.get_chemical_symbols(), fixed_atom_indices_0based=list(range(18)))
    try:
        label = validate_static(directory, atoms.get_chemical_symbols())
        row.update(label)
        moments = magnetic_status([label["local_magnetization_muB"]], len(atoms))
        row.update(moments, **geometry(atoms, atoms, rules))
        row.update(energy_eV_force_label_only=label["toten_eV_force_label_only"], electronic_converged=True,
                   movable_fmax_eV_A=float(np.linalg.norm(np.asarray(label["forces_eV_per_A"])[18:], axis=1).max()),
                   data_qc_status="MAGNETIC_REVIEW_REQUIRED" if moments["magnetic_review_flags"] else "PASS")
    except ValueError as exc:
        row.update(data_qc_status="REJECTED_OR_INCOMPLETE", reason=str(exc))
    return [row], {"normal_completion": parse_outcar(directory / "OUTCAR")["normal_completion"]}


def review_trajectory(receipt, rules):
    directory, case, collected = check_collection(receipt)
    initial = read(directory / "POSCAR", format="vasp")
    values = read_incar_values(directory / "INCAR")
    out = parse_outcar(directory / "OUTCAR")
    osz = parse_oszicar(directory / "OSZICAR")
    if not out["normal_completion"] or out["fatal_keywords"] or out["run_index"] != 1:
        raise ValueError("not a single normally closed VASP run")
    raw = raw_frames(directory / "OUTCAR", len(initial))
    trajectory = read(directory / "XDATCAR", format="vasp-xdatcar", index=":")
    independent = read(directory / "OUTCAR", format="vasp-out", index=":")
    if not len(raw) == len(trajectory) == len(independent) == osz["ionic_steps"] == 80:
        raise ValueError("OUTCAR/ASE/XDATCAR/OSZICAR frame counts differ")
    cycles = {c["ionic_step"]: c for c in osz["electronic_cycles"]}
    if [c["ionic_step"] for c in osz["electronic_cycles"]] != list(range(1, 81)):
        raise ValueError("OSZICAR cycle identity not contiguous")
    if len(osz["magnetization_history_muB"]) != 80:
        raise ValueError("per-frame total magnetization missing")
    out_hash = collected["remote"]["files"]["OUTCAR"]["sha256"]
    rows = []
    for frame, atoms, cross in zip(raw, trajectory, independent, strict=True):
        step = frame["ionic_step"]
        sid = receipt["sample_id"] + f"_opt{step:03d}"
        restore_input_lattice(atoms, initial, directory / "XDATCAR")
        atoms.set_constraint(initial.constraints)
        atoms.pbc = [True, True, False]
        if step == 1:
            _, first_move = find_mic(atoms.positions-initial.positions, initial.cell, pbc=[True, True, False])
            if max(first_move) > 2e-7:
                raise ValueError("initial optimization frame differs from submitted/previously labelled structure")
        structure = OUTPUT / "structures" / (sid + ".vasp")
        structure.parent.mkdir(exist_ok=True)
        if not structure.exists():
            write(structure, atoms, format="vasp", direct=True, vasp5=True)
        row = base_row(receipt, case, sid, structure, step, out_hash)
        row.update(origin="expanded_closed_trajectory", source_total_steps=80,
                   source_XDATCAR_sha256=sha256_file(directory / "XDATCAR"),
                   symbols=atoms.get_chemical_symbols(), fixed_atom_indices_0based=list(range(18)))
        try:
            scf = scf_for_frame(frame, cycles.get(step), values)
            forces = verify_frame(atoms, frame)
            if cross.get_chemical_symbols() != initial.get_chemical_symbols() or not np.array_equal(forces, cross.get_forces(apply_constraint=False)):
                raise ValueError("independent ASE raw-force/atom order mismatch")
            if not np.allclose(cross.positions, frame["positions_A"], atol=1e-10, rtol=0):
                raise ValueError("independent ASE force-coordinate mismatch")
            if abs(frame["toten_eV"] - osz["energies"][step-1]) > 1e-4 or abs(frame["toten_eV"] - cross.get_potential_energy(force_consistent=True)) > 1e-8:
                raise ValueError("per-frame TOTEN/OSZICAR/ASE mismatch")
            moments = magnetic_status(frame["local_moment_tables"], len(atoms))
            table = OUTPUT / "force_tables" / (sid + ".txt")
            table.parent.mkdir(exist_ok=True)
            if table.exists():
                if table.read_bytes() != frame["raw_force_table"]:
                    raise ValueError("force-table evidence changed")
            else:
                table.write_bytes(frame["raw_force_table"])
            fmax = float(np.linalg.norm(forces[18:], axis=1).max())
            row.update(**moments, **geometry(atoms, initial, rules), SCF=scf,
                forces_eV_per_A=forces.tolist(), energy_eV_force_label_only=frame["toten_eV"],
                toten_eV_force_label_only=frame["toten_eV"], electronic_converged=True, geometry_review_pass=True,
                total_magnetization_muB=osz["magnetization_history_muB"][step-1],
                source_force_table_sha256=sha256_file(table), source_force_byte_range=frame["source_byte_range"],
                movable_fmax_eV_A=fmax, adsorbate_fmax_eV_A=float(np.linalg.norm(forces[45:], axis=1).max()),
                data_qc_status="MAGNETIC_REVIEW_REQUIRED" if moments["magnetic_review_flags"] else "PASS",
                parent_ionic_converged=out["reached_required_accuracy"])
        except ValueError as exc:
            row.update(data_qc_status="REJECTED_OR_INCOMPLETE", reason=str(exc))
        rows.append(row)
    return rows, {"normal_completion": out["normal_completion"], "ionic_converged": out["reached_required_accuracy"],
                  "ionic_steps": 80, "frame_qc_counts": dict(Counter(r["data_qc_status"] for r in rows)),
                  "last_total_magnetization_muB": osz["magnetization_history_muB"][-1]}


def shortlist(rows, maximum=8):
    """Small deterministic proposal, preserving chemistry/force strata first."""
    chosen = []
    edges = np.array([0, .05, .10, .50, 1, 2, 5, 10])
    groups = {}
    for row in rows:
        key = (row["graph_signature"], int(np.searchsorted(edges, row["movable_fmax_eV_A"], side="right") - 1))
        groups.setdefault(key, []).append(row)
    for key in sorted(groups):
        chosen.append(min(groups[key], key=lambda r: (r["movable_fmax_eV_A"], r["sample_id"])))
    if len(chosen) > maximum:
        raise ValueError("more chemistry/force strata than shortlist budget;review explicitly")
    remaining = [r for r in rows if r not in chosen]
    while remaining and len(chosen) < maximum:
        row = max(remaining, key=lambda r: (min(abs(r["ionic_step"]-c["ionic_step"]) for c in chosen), r["ionic_step"]))
        chosen.append(row)
        remaining.remove(row)
    return sorted(chosen, key=lambda r: r["sample_id"])


def run():
    receipts = scope()
    collection = load_json_object(OUTPUT / "collection_summary.json")
    if collection["failures"] or len(collection["collected"]) != 14:
        raise ValueError("complete14 collections required")
    if not source_file_manifest_valid(load_json_object(OUTPUT / "collection_binding.json")):
        raise ValueError("collection code/source binding stale")
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    cfg_path = ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json"
    cfg = load_json_object(cfg_path)
    prior_path = ROOT / cfg["prior_manifest"]
    reserved = reserved_geometries(load_json_object(ROOT / cfg["inventory"]), load_json_object(prior_path),
                                  prior_path.parent, cfg["reserved_geometry_catalogs"])
    protected_jobs = {str(r.get("source_job_id")) for r, _ in reserved}
    protected_families = {r.get("family_id") for r, _ in reserved}
    for receipt in receipts:
        if receipt["job_id"] in protected_jobs or receipt["sample_id"].split("_step")[0] in protected_families:
            raise ValueError("whole-job/family reserved overlap")
    dependencies = [Path(__file__), Path(__file__).with_name("collect.py"), RULES, FROZEN, AUDIT, cfg_path,
        ROOT / "configs/fe110_reico_pilot/force_qc_v1.json",
        ROOT / cfg["inventory"], prior_path, OUTPUT / "collection_binding.json", OUTPUT / "collection_summary.json",
        OUTPUT / "remote_metadata.json", OUTPUT / "scheduler_evidence.json",
        ROOT / "scripts/adsorption/reico_probe_review.py", ROOT / "scripts/neb_agent/utils_vasp.py",
        ROOT / "scripts/vasp_result_gate.py", ROOT / "scripts/adsorption/force_finetune.py",
        ROOT / "archive/fe110_10b_lowforce_20261023/legacy_helpers.py",
        ROOT / "archive/fe110_10b_lowforce_20261023/review.py",
        ROOT / "archive/fe110_combined_force_package_20261023/prepare.py",
        ROOT / "scripts/adsorption/reico_selection.py", ROOT / "scripts/adsorption/reico_dataset_audit.py",
        *[ROOT / p for p in cfg["reserved_geometry_catalogs"]],
        *sorted({Path(r["structure_path"]) for r, _ in reserved})]
    for receipt in receipts:
        directory, _, _ = check_collection(receipt)
        dependencies.extend([directory / "collection.json", *[directory / n for n in FILES]])
        if receipt["role"] == "optimizations":
            dependencies.append(directory / "XDATCAR")
    save_once(OUTPUT / "review_binding.json", {"source_files": source_file_manifest(dependencies)})
    rows, cases = [], []
    for receipt in receipts:
        case_path = OUTPUT / "case_qc" / (receipt["sample_id"] + ".json")
        if case_path.exists():
            saved = load_json_object(case_path)
            extra, details = saved["samples"], saved["details"]
        else:
            extra, details = (review_static if receipt["role"] == "single_points" else review_trajectory)(receipt, rules)
            save_once(case_path, {"samples": extra, "details": details})
        rows.extend(extra)
        cases.append({"sample_id": receipt["sample_id"], "job_id": receipt["job_id"], **details})
        print("QC " + receipt["sample_id"] + " " + str(Counter(r["data_qc_status"] for r in extra)), flush=True)
    save_once(OUTPUT / "all_frame_qc_local_only.json", {"samples": rows, "cases": cases})
    passed = [r for r in rows if r["data_qc_status"] == "PASS"]
    slab_path = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    eligible, isolation = isolate(passed, OUTPUT, reserved, read_poscar(slab_path), .20)
    save_once(OUTPUT / "training_isolation.json", isolation)
    # Initial optimization coordinates already have reviewed single-point labels.
    duplicate_starts = [r["sample_id"] for r in eligible if r["origin"] == "expanded_closed_trajectory" and r["ionic_step"] == 1]
    eligible = [r for r in eligible if r["sample_id"] not in duplicate_starts]
    atoms = {r["sample_id"]: read(OUTPUT / r["structure_path"], format="vasp") for r in eligible}
    kept, redundant = collapse_redundant(sorted(eligible, key=lambda r: (r["source_job_id"], -r["ionic_step"])),
        lambda a, b: frame_distance(atoms[a["sample_id"]], atoms[b["sample_id"]]))
    save_once(OUTPUT / "candidate_labels.json", {"samples": kept})
    for row in kept:
        row["label_source"] = {"path": "candidate_labels.json", "sha256": sha256_file(OUTPUT / "candidate_labels.json"), "sample_id": row["sample_id"]}
        validate_label_row(OUTPUT, row)
    save_once(OUTPUT / "eligible_training_candidates.json", {"samples": kept, "is_training_package": False,
        "merged_into_existing_manifest": False, "training_authorized": False})
    selected = [r for r in kept if r["origin"] == "new_static"]
    for job in sorted({r["source_job_id"] for r in kept if r["origin"] == "expanded_closed_trajectory"}):
        selected.extend(shortlist([r for r in kept if r["source_job_id"] == job]))
    save_once(OUTPUT / "recommended_small_supplement.json", {"samples": selected, "training_authorized": False,
        "selection": "all qualified targeted statics;at most8per trajectory,graph/force strata then ionic-step spread",
        "is_training_package": False})
    summary = {"jobs_recovered": 14, "frames_reviewed": len(rows), "qc_counts": dict(Counter(r["data_qc_status"] for r in rows)),
        "isolation": isolation, "duplicate_initial_frames_excluded": duplicate_starts,
        "same_job_near_geometry_and_force_redundant": redundant, "eligible_candidates": len(kept),
        "recommended_candidates": len(selected), "recommended_by_composition": dict(Counter(r["composition"] for r in selected)),
        "by_composition": {c: {"eligible": sum(r["composition"] == c for r in kept),
            "minimum_movable_fmax_eV_A": min(r["movable_fmax_eV_A"] for r in kept if r["composition"] == c),
            "low_force_le_0p05": sum(r["composition"] == c and r["movable_fmax_eV_A"] <= .05 for r in kept)} for c in sorted({r["composition"] for r in kept})},
        "magnetic_ground_state_verified": False, "original366package_changed": False, "original485audit_changed": False,
        "new_DFT_GPU_training_or_continuation": False,
        "source_files": source_file_manifest([OUTPUT / "review_binding.json", OUTPUT / "all_frame_qc_local_only.json",
            OUTPUT / "training_isolation.json", OUTPUT / "candidate_labels.json", OUTPUT / "recommended_small_supplement.json"])}
    save_once(OUTPUT / "summary.json", summary)
    print({k: v for k, v in summary.items() if k not in {"source_files", "isolation", "same_job_near_geometry_and_force_redundant"}}, flush=True)


if __name__ == "__main__":
    run()
