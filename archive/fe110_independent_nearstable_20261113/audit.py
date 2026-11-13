"""Inventory existing labels and geometric isolation; never admit data or run models."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml
from ase.io import read

from archive.fe110_10b_lowforce_20261023.legacy_helpers import (
    pose_distance, pose_variants, restore_input_lattice, verify_frame,
)
from archive.fe110_10b_lowforce_20261023.review import scf_for_frame
from archive.fe110_combined_force_package_20261023.prepare import save_once
from archive.fe110_grouped_qc_20261026.review import geometry, magnetic_status, raw_frames
from scripts.adsorption.build_fe110_adsorption import Poscar, read_poscar
from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
from scripts.adsorption.reico_chemical_environments import chemical_environment
from scripts.artifact_io import load_json_object as load
from scripts.artifact_io import sha256_bytes, sha256_file, source_file_manifest
from scripts.neb_agent.utils_vasp import parse_oszicar
from scripts.vasp_result_gate import read_incar_values
from .collect import BASE, OUTPUT, ROOT

PACKAGE = BASE / "combined_force_package_20261113_v1"
CLEAN = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
RULES = ROOT / "configs/adsmind_lite/analysis_rules.yaml"


def fmax(row):
    fixed = set(row["fixed_atom_indices_0based"])
    free = sorted(set(range(len(row["symbols"]))) - fixed)
    return float(np.linalg.norm(np.asarray(row["forces_eV_per_A"])[free], axis=1).max())


def frozen_hashes():
    names = ("training_manifest.json", "train.db", "development.db", "train_metadata.npz",
             "development_metadata.npz", "package_inventory.json")
    return {str(root.relative_to(BASE) / name): sha256_file(root / name)
            for root in (PACKAGE, BASE / "combined_force_package_20261027_v3") for name in names}


def reference_poses(manifest):
    operations = surface_pose_symmetries(read_poscar(CLEAN))
    references = []
    for split, rows in manifest["splits"].items():
        for row in rows:
            if row["composition"] != "C2H3":
                continue
            path = PACKAGE / row["structure_path"]
            if sha256_file(path) != row["structure_sha256"]:
                raise ValueError("frozen reference geometry changed")
            references.append((split, row["sample_id"], pose_variants(read_poscar(path), operations)))
    if len(references) != 75 or len(operations) != 36:
        raise ValueError("unexpected training/protected geometry reference scope")
    return references


def isolation(atoms, base, references):
    pose = Poscar("", base.cell, base.symbols, base.counts,
                  atoms.get_scaled_positions(wrap=False), base.flags)
    result = {}
    for split in ("train", "development", "heldout"):
        distance, name = min((pose_distance(pose, variants), name)
                             for label, name, variants in references if label == split)
        result[split] = {"nearest_id": name, "adsorbate_RMSD_A": distance, "within0p20A": distance <= .20}
    return result


def H_distribution(atoms, environment):
    symbols = atoms.get_chemical_symbols()[45:]
    values = {i: 0 for i, symbol in enumerate(symbols) if symbol == "C"}
    for first, second in environment["adsorbate_edges_local_0based"]:
        if symbols[first] == "C" and symbols[second] == "H":
            values[first] += 1
        if symbols[second] == "C" and symbols[first] == "H":
            values[second] += 1
    return sorted(values.values())


def selected_frame(source, frame, atoms, initial, cycles, incar, rules, base, references):
    errors = []
    try:
        verify_frame(atoms, frame)
        scf_for_frame(frame, cycles.get(frame["ionic_step"]), incar)
        magnetic = magnetic_status(frame["local_moment_tables"], len(atoms))
        geo = geometry(atoms, initial, rules)
        if magnetic["magnetic_review_flags"]:
            errors.extend(magnetic["magnetic_review_flags"])
    except ValueError as error:
        errors.append(str(error))
        magnetic = {"magnetic_review_level": "Needs confirmation"}
        geo = chemical_environment(atoms, rules["connectivity"])
    formula = atoms[45:].get_chemical_formula()
    record = {"candidate_id": "job" + source["job_id"] + f"_opt{frame['ionic_step']:03d}",
              "source_job_id": source["job_id"], "ionic_step": frame["ionic_step"], "composition": formula,
              "movable_fmax_eV_A": float(np.linalg.norm(np.asarray(frame["forces_eV_per_A"])[18:], axis=1).max()),
              "graph_signature": geo["graph_signature"], "adsorbate_component_count": geo["adsorbate_component_count"],
              "C_H_counts": H_distribution(atoms, geo), "bond_counts": geo["bond_counts"],
              "magnetic_review_level": magnetic["magnetic_review_level"], "QC_errors": errors,
              "raw_force_table_sha256": sha256_bytes(frame["raw_force_table"]),
              "OUTCAR_byte_range": frame["source_byte_range"], "source_OUTCAR": str(source["directory"] / "OUTCAR"),
              "source_OUTCAR_sha256": source["OUTCAR_sha256"], "source_XDATCAR": str(source["XDATCAR"]),
              "source_XDATCAR_sha256": sha256_file(source["XDATCAR"]),
              "coordinate_force_precision_check": not errors, "scientific_acceptance": False,
              "added_to_any_dataset": False}
    if formula == "C2H3":
        record["geometry_isolation"] = isolation(atoms, base, references)
    return record


def scan_source(source, references, rules):
    directory = source["directory"]
    initial = read(directory / "POSCAR", format="vasp")
    trajectory = read(source["XDATCAR"], format="vasp-xdatcar", index=":")
    frames = raw_frames(directory / "OUTCAR", len(initial))
    cycles = {c["ionic_step"]: c for c in parse_oszicar(directory / "OSZICAR")["electronic_cycles"]}
    incar = read_incar_values(directory / "INCAR")
    if len(trajectory) != len(frames):
        raise ValueError("XDATCAR/OUTCAR frame count mismatch")
    base = read_poscar(directory / "POSCAR")
    selected, intact_C3, near_C3, norms = [], 0, 0, []
    for frame, atoms in zip(frames, trajectory, strict=True):
        restore_input_lattice(atoms, initial, source["XDATCAR"])
        atoms.set_constraint(initial.constraints)
        atoms.pbc = [True, True, False]
        value = float(np.linalg.norm(np.asarray(frame["forces_eV_per_A"])[18:], axis=1).max())
        norms.append(value)
        if len(atoms) == 51:
            env = chemical_environment(atoms, rules["connectivity"])
            if env["adsorbate_component_count"] == 1:
                intact_C3 += 1
                near_C3 += value <= .05
        if value <= .05:
            selected.append(selected_frame(source, frame, atoms, initial, cycles, incar, rules, base, references))
    summary = {"job_id": source["job_id"], "source_frames": len(frames), "force_le0p05": len(selected),
               "force_le0p10": sum(v <= .1 for v in norms), "final_fmax_eV_A": norms[-1],
               "intact_C3_frames": intact_C3, "intact_C3_force_le0p05": near_C3,
               "near_frame_QC_pass": sum(not r["QC_errors"] for r in selected),
               "source_files": source_file_manifest([directory / n for n in ("OUTCAR", "POSCAR", "CONTCAR", "INCAR", "OSZICAR", "KPOINTS")] + [source["XDATCAR"]])}
    return summary, selected


def label_pool_inventory(manifest):
    train_families = {r.get("family_id") for r in manifest["splits"]["train"] if r.get("family_id")}
    result = []
    for name in ("final30_qc_20261025_v1/all_selected_label_qc_local_only.json",
                 "grouped_qc_20261026_v2/candidate_labels.json"):
        rows = [r for r in load(BASE / name)["samples"] if r.get("composition") in ("C2H3", "C3H2O")]
        outside = [r for r in rows if r["family_id"] not in train_families]
        result.append({"source": name, "target_frames": len(rows), "outside_training_family": len(outside),
                       "outside_training_family_force_le0p10": [r["sample_id"] for r in outside if fmax(r) <= .1]})
    return result


def run():
    before = frozen_hashes()
    manifest = load(PACKAGE / "training_manifest.json")
    references = reference_poses(manifest)
    collection = load(OUTPUT / "source_collection.json")
    by_job = {r["job_id"]: r for r in collection["sources"]}
    sources = []
    for filename in ("outputs/adsorption_acceptance_20261029_v1/analysis.json",
                     "outputs/fe110_c2_registration_20261102_v1/analysis.json"):
        for row in load(ROOT / filename)["records"]:
            if row["formula"] == "C2H3":
                fresh = by_job[row["job_id"]]
                if not fresh["cached_OUTCAR_hash_matches_remote"] or not all(row["compatibility_checks"].values()):
                    raise ValueError("cached source or compatibility binding changed")
                sources.append({"job_id": row["job_id"], "directory": Path(row["directory"]),
                                "OUTCAR_sha256": fresh["files"]["OUTCAR"]["sha256"],
                                "XDATCAR": OUTPUT / fresh["files"]["XDATCAR"]["saved_path"]})
    for job in ("9925062", "9925065"):
        fresh = by_job[job]
        sources.append({"job_id": job, "directory": OUTPUT / "source_snapshots" / job,
                        "OUTCAR_sha256": fresh["files"]["OUTCAR"]["sha256"],
                        "XDATCAR": OUTPUT / fresh["files"]["XDATCAR"]["saved_path"]})
    summaries, selected = [], []
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    # Each source uses the existing raw-force/SCF/precision/magnetic owners.
    for source in sources:
        summary, rows = scan_source(source, references, rules)
        summaries.append(summary)
        selected.extend(rows)
    reserved = []
    for split in ("development", "heldout"):
        for row in manifest["splits"][split]:
            if row["composition"] in ("C2H3", "C3H2O") and fmax(row) <= .1:
                reserved.append({"sample_id": row["sample_id"], "source_job_id": row["source_job_id"],
                                 "split": split, "composition": row["composition"], "fmax_eV_A": fmax(row),
                                 "magnetic_review_level": row["magnetic_review_level"], "role_unchanged": True})
    after = frozen_hashes()
    if before != after:
        raise ValueError("frozen512/536 package changed during read-only audit")
    result = {"document_kind": "independent_nearstable_source_inventory_not_admission", "status": "READ_ONLY_PHYSICAL_SOURCE_SCAN",
              "near_threshold_eV_A": .05, "support_threshold_eV_A": .1, "source_summaries": summaries,
              "near_force_candidates": selected, "existing_reserved_target_labels": reserved,
              "original_reviewed_label_pools": label_pool_inventory(manifest),
              "train_families_excluded": sorted({r.get("family_id") for r in manifest["splits"]["train"] if r.get("family_id")}),
              "training_reference_C2H3": 51, "protected_reference_C2H3": 24, "surface_symmetries": 36,
              "frozen_hashes_before_after": before, "datasets_modified": False, "new_DFT_or_training": False,
              "source_files": source_file_manifest([Path(__file__), Path(__file__).with_name("collect.py"), PACKAGE / "training_manifest.json",
                                                    CLEAN, RULES, OUTPUT / "source_collection.json",
                                                    BASE / "final30_qc_20261025_v1/all_selected_label_qc_local_only.json",
                                                    BASE / "grouped_qc_20261026_v2/candidate_labels.json"])}
    save_once(OUTPUT / "physical_inventory.json", result)
    return result


if __name__ == "__main__":
    result = run()
    print({"sources": [{k: r[k] for k in ("job_id", "source_frames", "force_le0p05", "near_frame_QC_pass", "intact_C3_force_le0p05")}
                       for r in result["source_summaries"]], "candidate_frames": len(result["near_force_candidates"])})
