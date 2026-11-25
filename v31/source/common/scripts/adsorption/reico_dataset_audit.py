"""Audit existing REICO training geometry/labels and write bounded proposals only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from scripts.adsorption.force_finetune import local_path, validate_label_row
from scripts.adsorption.reico_environment_audit import (
    calibrate, coverage_summary, describe, frame_scores, nearest, propose_additions,
    read_geometry, source_counts, stack, train_inventory,
)
from scripts.adsorption.reico_selection import frame_distance
from scripts.artifact_io import sha256_json, source_file_manifest, write_json


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def absolute_row(root: Path, row: dict) -> dict:
    return {**row, "structure_path": str(local_path(root, row["structure_path"]))}


def reserved_geometries(inventory: dict, manifest: dict, root: Path, catalogs=()) -> list[tuple[dict, object]]:
    """Read reserved structures for isolation only; never inspect their labels."""
    rows = [r for r in inventory["frames"] if r["partition"] != "train" and not r["geometry_guard_failures"]]
    for split in ("development", "heldout"):
        rows.extend(absolute_row(root, r) for r in manifest["splits"][split])
    rows.extend(absolute_row(root, r) for r in manifest.get("quarantined_observed_heldout", []))
    alternatives = {}
    for path in map(Path, catalogs):
        for group in load(path)["splits"].values():
            for row in group:
                alternatives[row["structure_sha256"]] = local_path(path.parent, row["structure_path"])
    for row in rows:
        if not Path(row["structure_path"]).is_file() and row["structure_sha256"] in alternatives:
            row["structure_path"] = str(alternatives[row["structure_sha256"]])
    return [(r, read_geometry(r)) for r in rows]


def overlaps(atoms, others, threshold: float) -> list[str]:
    return [row["sample_id"] for row, other in others if frame_distance(atoms, other) < threshold]


def audit_labels(path: Path, reserved: list, config: dict) -> tuple[dict, list[dict]]:
    manifest = load(path)
    records, failures, reusable = [], [], []
    groups = {r["calculation_group"] for split in ("development", "heldout") for r in manifest["splits"][split]}
    groups.update(r["calculation_group"] for r in manifest.get("quarantined_observed_heldout", []))
    for row in manifest["splits"]["train"]:
        try:
            validate_label_row(path.parent, row)
            if row["calculation_group"] in groups:
                raise ValueError("reserved whole-job overlap")
            atoms = read_geometry(absolute_row(path.parent, row))
            force_max = float(np.max(np.linalg.norm(np.asarray(row["forces_eV_per_A"])[18:], axis=1)))
            declared = row.get("movable_fmax_eV_A")
            if declared is not None and not np.isclose(force_max, declared, atol=1e-10, rtol=0):
                raise ValueError("raw force norm differs from manifest")
            record = {key: row.get(key) for key in (
                "sample_id", "source_name", "source_job_id", "calculation_group", "stage", "original_graph_preserved",
                "parent_ionic_converged", "source_OUTCAR_sha256", "total_magnetization_muB", "accepted_endpoint")}
            record.update(structure_path=str(local_path(path.parent, row["structure_path"])),
                          structure_sha256=row["structure_sha256"], formula=atoms[45:].get_chemical_formula(),
                          movable_fmax_eV_A=force_max, raw_label_binding_verified=True,
                          label_source=row["label_source"], source_partition="train")
            record["reserved_geometry_overlaps"] = overlaps(atoms, reserved, config["reserved_geometry_isolation_A"])
            record["reuse_status"] = "QUARANTINE_GEOMETRY_OVERLAP" if record["reserved_geometry_overlaps"] else "LABEL_REUSE_CANDIDATE"
            records.append(record)
            if record["reuse_status"] == "LABEL_REUSE_CANDIDATE":
                reusable.append({**record, "atoms": atoms})
        except (ValueError, KeyError, OSError) as error:
            failures.append({"sample_id": row["sample_id"], "error": str(error)})
    near = [r for r in records if r["movable_fmax_eV_A"] <= config["near_equilibrium_force_diagnostic_eV_A"]]
    return {"source_training_rows": len(manifest["splits"]["train"]), "verified_rows": len(records),
            "failures": failures, "records": records,
            "verified_formula_counts": dict(Counter(r["formula"] for r in records)),
            "near_equilibrium_rows": len(near), "near_equilibrium_formula_counts": dict(Counter(r["formula"] for r in near)),
            "magnetic_scope": "Approved input-branch provenance only; neither local moments nor global magnetic minima revalidated.",
            "compatibility_scope": "Canonical label, geometry, force and metadata bindings rechecked; DFT method compatibility uses bound prior reviews."}, reusable


def choose_anchors(reusable: list[dict], config: dict) -> list[dict]:
    """Deduplicate low-force candidates from converged training-parent jobs."""
    candidates = [r for r in reusable if r["parent_ionic_converged"] is True
                  and r["movable_fmax_eV_A"] <= config["anchor_force_candidate_eV_A"]]
    candidates.sort(key=lambda r: (r["movable_fmax_eV_A"], r["sample_id"]))
    chosen, groups = [], set()
    for row in candidates:
        if row["calculation_group"] in groups or any(frame_distance(row["atoms"], old["atoms"]) < config["geometry_duplicate_A"]
                                                   for old in chosen):
            continue
        chosen.append(row)
        groups.add(row["calculation_group"])
    return [{key: value for key, value in row.items() if key != "atoms"} for row in chosen]


def run_coverage(train: list, selected: list, reserved: list, config: dict, output: Path) -> tuple[dict, list[dict], dict]:
    from dscribe.descriptors import SOAP

    soap = SOAP(**config["soap"])
    binding = {"soap": config["soap"], "near_Fe_A": config["near_Fe_A"], "dscribe": importlib.metadata.version("dscribe")}
    cache = output / "descriptor_cache" / sha256_json(binding)
    records, geometries = [], {}
    for index, row in enumerate(train):
        atoms = read_geometry(row)
        geometries[row["sample_id"]] = atoms
        records.append(describe(row, atoms, soap, cache, config["near_Fe_A"]))
        if (index + 1) % 200 == 0:
            print(f"SOAP {index + 1}/{len(train)} training frames", flush=True)
    selected_ids = {r["sample_id"] for r in selected}
    reference = stack([r for r in records if r["sample_id"] in selected_ids])
    pool = stack(records)
    thresholds, sensitivity = calibrate(reference, config["leave_family_out_quantile"])
    distances = nearest(pool, reference)
    selected_geometry = [(r, geometries[r["sample_id"]]) for r in selected]
    eligible_cache = {}

    def eligible(row, proposed):
        sid = row["sample_id"]
        if sid not in eligible_cache:
            eligible_cache[sid] = (not overlaps(geometries[sid], selected_geometry, config["geometry_duplicate_A"])
                                   and not overlaps(geometries[sid], reserved, config["reserved_geometry_isolation_A"]))
        added = [(r, geometries[r["sample_id"]]) for r in proposed]
        return eligible_cache[sid] and not overlaps(geometries[sid], added, config["geometry_duplicate_A"])

    proposals, after = propose_additions(records, selected_ids, pool, distances, thresholds,
                                        config["maximum_random_addition_proposals"], eligible=eligible)
    rows = frame_scores(records, pool, distances, thresholds)
    report = {"training_pool": source_counts(train), "existing_selected_training": source_counts(selected),
              "descriptor": binding, "descriptor_features": soap.get_number_of_features(),
              "calibration": "Per-element p95 nearest cosine distance, excluding the query trajectory family from references.",
              "thresholds": thresholds, "calibration_quantile_sensitivity": sensitivity,
              "before": coverage_summary(pool, distances, thresholds), "after_proposed_additions": coverage_summary(pool, after, thresholds),
              "before_frame_gap_count": sum(r["exceeds_internal_threshold"] for r in rows),
              "after_frame_gap_count": sum(r["exceeds_internal_threshold"] for r in frame_scores(records, pool, after, thresholds)),
              "proposal_count": len(proposals), "proposal_scope": "At most one addition per training family; no selections or jobs modified.",
              "interpretation": "Relative geometric coverage diagnostic, not force accuracy, chemical completeness or a global minimum data budget."}
    return report, proposals, {"frame_scores": rows}


def run(config_path: Path, output: Path) -> dict:
    config = load(config_path)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "audit_summary.json").exists():
        raise ValueError("completed output already exists; choose a new directory")
    inventory_path, selection_path, prior_path = (Path(config[key]).resolve() for key in ("inventory", "selection", "prior_manifest"))
    inventory, selection, prior = load(inventory_path), load(selection_path), load(prior_path)
    train, selected = train_inventory(inventory, selection)
    reserved = reserved_geometries(inventory, prior, prior_path.parent, config.get("reserved_geometry_catalogs", []))
    write_json(output / "run_status.json", {"status": "RUNNING", "phase": "SOAP", "training_frames": len(train)})
    coverage, proposals, scores = run_coverage(train, selected, reserved, config, output)
    write_json(output / "coverage.json", coverage)
    write_json(output / "frame_scores.json", scores)
    write_json(output / "run_status.json", {"status": "RUNNING", "phase": "REUSABLE_LABELS"})
    labels, reusable = audit_labels(prior_path, reserved, config)
    anchors = choose_anchors(reusable, config)
    record_map = {r["sample_id"]: r for r in train}
    proposals = [{**row, "source": record_map[row["sample_id"]], "action": "PROPOSE_DFT_SINGLE_POINT_ONLY_NOT_SUBMITTED"}
                 for row in proposals]
    plan = {"random_training_additions": proposals, "low_force_anchor_candidates": anchors,
            "anchor_perturbation_recipe_not_generated": [
                {"kind": "adsorbate_rigid_height", "delta_z_A": -.10},
                {"kind": "adsorbate_rigid_height", "delta_z_A": .10},
                {"kind": "adsorbate_random_displacement", "rms_A": .03, "seed": 42},
                {"kind": "adsorbate_random_displacement", "rms_A": .06, "seed": 43}],
            "perturbation_count_upper_bound_before_guards": 4 * len(anchors),
            "C3_anchor_scope": "No C3 labels in the audited prior training package; other project sources still require a separate bounded audit.",
            "next_gate": "Review source/fixed-mask/chemistry/magnetism, generate guarded model-independent candidates, then authorize exact new single points.",
            "training_authorized": False, "DFT_submitted": False, "new_geometries_generated": False}
    write_json(output / "reusable_labels.json", labels)
    write_json(output / "supplement_plan.json", plan)
    sources = [config_path, inventory_path, selection_path, prior_path, Path(__file__),
               Path("scripts/adsorption/reico_environment_audit.py"), Path("scripts/adsorption/force_finetune.py"),
               Path("scripts/adsorption/reico_selection.py"), *map(Path, config["compatibility_evidence"]),
               *map(Path, config.get("reserved_geometry_catalogs", []))]
    summary = {"document_kind": "fe110_reico_training_coverage_audit", "completed_utc": datetime.now(timezone.utc).isoformat(),
               "status": "AUDIT_COMPLETE" if not labels["failures"] else "AUDIT_COMPLETE_WITH_LABEL_FAILURES",
               "source_files": source_file_manifest(sources), "config": config,
               "versions": {name: importlib.metadata.version(name) for name in ("dscribe", "sparse", "ase", "numpy", "scipy")},
               "training_frames_audited": len(train), "selected_training_frames": len(selected),
               "reserved_geometry_only_records": len(reserved), "reserved_forces_or_energies_used": False,
               "reusable_training_label_rows": sum(r["reuse_status"] == "LABEL_REUSE_CANDIDATE" for r in labels["records"]),
               "low_force_anchor_candidates": len(anchors), "random_addition_proposals": len(proposals),
               "original_selection_changed": False, "GPU_or_DFT_execution": False, "training_performed": False,
               "model_accuracy_or_speedup_established": False}
    write_json(output / "audit_summary.json", summary)
    write_json(output / "run_status.json", {"status": summary["status"]})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.config, args.output)
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        name = "failure_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
        write_json(args.output / name, {"error_type": type(error).__name__, "error": str(error)})
        raise
    print(json.dumps({key: result[key] for key in ("status", "training_frames_audited", "reusable_training_label_rows",
                                                 "low_force_anchor_candidates", "random_addition_proposals")}))


if __name__ == "__main__":
    main()
