"""Separate lineage, isolation and selection review of the data-only candidates."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from ase.io import read

from scripts.artifact_io import sha256_file, source_file_manifest
from .prepare import BASE, FROZEN, OUTPUT, ROOT, frozen_hashes, load, save_bytes, save_json


def check_lineage(collection, plan, submission):
    if collection["job_id"] != "9924387" or submission["receipt"]["job_id"] != "9924387":
        raise ValueError("wrong source job")
    if str(plan["source_job_id"]) != "9922624":
        raise ValueError("wrong parent job")
    if collection["files"]["POSCAR"]["sha256"] != plan["source_CONTCAR_sha256"]:
        raise ValueError("parent-CONTCAR/source-POSCAR binding differs")
    if plan["bundle_sha256"] != submission["receipt"]["bundle_sha256"]:
        raise ValueError("submitted bundle identity differs")


def replay_isolation(output, rows):
    from archive.fe110_10b_lowforce_20261023.legacy_helpers import pose_distance, pose_variants
    from scripts.adsorption.build_fe110_adsorption import read_poscar
    from scripts.adsorption.build_fe110_care_isomers import surface_pose_symmetries
    from scripts.adsorption.reico_dataset_audit import reserved_geometries

    config_path = ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json"
    config = load(config_path)
    prior = ROOT / config["prior_manifest"]
    inventory_path = ROOT / config["inventory"]
    catalogs = [ROOT / p for p in config["reserved_geometry_catalogs"]]
    reserved = reserved_geometries(load(inventory_path), load(prior), prior.parent, catalogs)
    clean = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    dependencies = [config_path, prior, inventory_path, clean, FROZEN / "training_manifest.json", *catalogs]
    catalog, variants = [], []
    operations = surface_pose_symmetries(read_poscar(clean))
    for reference, atoms in reserved:
        path = Path(reference["structure_path"])
        if sha256_file(path) != reference["structure_sha256"]:
            raise ValueError("reserved source geometry changed")
        dependencies.append(path)
        catalog.append({"sample_id": reference["sample_id"], "structure_path": str(path),
                        "structure_sha256": reference["structure_sha256"], "use": "isolation_only"})
        if Counter(atoms.get_chemical_symbols()) == Counter(rows[0]["symbols"]):
            variants.append(pose_variants(read_poscar(path), operations))
    if len(reserved) != 513 or len(variants) != 210:
        raise ValueError("reserved review scope changed")
    for row in rows:
        pose = read_poscar(output / row["structure_path"])
        distance = min(pose_distance(pose, candidate) for candidate in variants)
        if distance <= .20 or abs(distance - row["reserved_min_RMSD_A"]) > 1e-12:
            raise ValueError("independent isolation replay differs")
    save_json(output / "reserved_geometry_binding.json", {"geometries": catalog,
        "reserved_forces_or_energies_included": False, "source_files": source_file_manifest(dependencies)})
    return len(rows) * len(variants)


def replay_selection(output, rows):
    from archive.fe110_10b_lowforce_20261023.legacy_helpers import collapse_redundant, restore_input_lattice
    from archive.fe110_grouped_qc_20261026.review import raw_frames
    from scripts.adsorption.reico_selection import frame_distance

    initial = read(output / "source/POSCAR", format="vasp")
    atoms = read(output / "source/XDATCAR", format="vasp-xdatcar", index=":")
    frames = raw_frames(output / "source/OUTCAR", 51)
    cases = load(output / "all_frame_qc.json")["frames"]
    for case, frame, geometry in zip(cases, frames, atoms, strict=True):
        restore_input_lattice(geometry, initial, output / "source/XDATCAR")
        case["forces_eV_per_A"] = frame["forces_eV_per_A"]
        if case["ionic_step"] != frame["ionic_step"]:
            raise ValueError("raw frame identity differs")
        measured = float(np.linalg.norm(np.asarray(frame["forces_eV_per_A"])[18:], axis=1).max())
        if abs(case["movable_fmax_eV_A"] - measured) > 1e-12:
            raise ValueError("cached source force magnitude differs")
        case["movable_fmax_eV_A"] = measured
    for row in rows:
        if abs(row["movable_fmax_eV_A"] - cases[row["ionic_step"] - 1]["movable_fmax_eV_A"]) > 1e-12:
            raise ValueError("candidate force magnitude differs from raw source")
    kept, redundant = collapse_redundant(sorted(cases, key=lambda r: -r["ionic_step"]),
        lambda a, b: frame_distance(atoms[a["ionic_step"] - 1], atoms[b["ionic_step"] - 1]))
    selected = sorted(r["ionic_step"] for r in kept if r["movable_fmax_eV_A"] <= .05)
    if selected != [r["ionic_step"] for r in rows]:
        raise ValueError("independent deduplication/low-force selection differs")
    return len(redundant)


def run(output=OUTPUT):
    output = Path(output).resolve()
    verification = load(output / "independent_verification.json")
    manifest = load(output / "candidate_manifest.json")
    if verification["candidate_manifest_sha256"] != sha256_file(output / "candidate_manifest.json"):
        raise ValueError("candidate differs from independent force replay")
    inputs = {"source_plan.json": BASE / "c3_continuation_20261027_v1/plan.json",
              "submission_summary.json": BASE / "c3_submission_20261027_v1/submission_summary.json",
              "submitted_scheduler_PEND.json": BASE / "c3_submission_20261027_v1/scheduler_evidence.json"}
    collection = load(output / "source_collection.json")
    check_lineage(collection, load(inputs["source_plan.json"]), load(inputs["submission_summary.json"]))
    for name, path in inputs.items():
        save_bytes(output / "provenance" / name, path.read_bytes())
    comparisons = replay_isolation(output, manifest["samples"])
    redundant = replay_selection(output, manifest["samples"])
    if frozen_hashes() != load(output / "request.json")["frozen512_before"]:
        raise ValueError("frozen512 inputs changed")
    result = {"status": "PASS_SEPARATE_CANDIDATE_PACKAGE_REVIEW_NOT_ADMITTED", "candidate_frames": 24,
        "parent_job_id": "9922624", "source_job_id": "9924387", "independent_isolation_comparisons": comparisons,
        "independent_same_job_redundant_frames": redundant, "frozen512_unchanged": True,
        "terminal_scheduler_status": None, "training_authorized": False, "merged_into_existing_manifest": False,
        "accepted_endpoint": False, "reportable_final_energy": False, "registry_written": False,
        "remaining_step": "separate decision on future dataset admission;no training authorized",
        "source_files": source_file_manifest([Path(__file__), output / "candidate_manifest.json",
            output / "independent_verification.json", output / "reserved_geometry_binding.json", *inputs.values()])}
    save_json(output / "candidate_review.json", result)
    return {k: v for k, v in result.items() if k != "source_files"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    print(__import__("json").dumps(run(parser.parse_args().output)))
