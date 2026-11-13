"""Assemble the separately approved 536-frame package; never train or submit."""
from __future__ import annotations

import copy
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from archive.fe110_c3_lowforce_candidates_20261109.assess_admission import eligibility
from archive.fe110_combined_force_package_20261023 import prepare as owner
from scripts.adsorption.force_finetune import load_manifest, local_path
from scripts.artifact_io import load_json_object as load
from scripts.artifact_io import sha256_file, source_file_manifest, source_file_manifest_valid

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/fe110_reico_pilot/combined_force_package_20261113_v1.json"
COUNTS = {"train": 536, "development": 78, "heldout": 53}
COLLECTION = "c3_lowforce24_job9924387_20261109"


def inventory_entries(root):
    """Check the complete declared tree, including files outside the manifest."""
    inventory = root / "package_inventory.json"
    entries = load(inventory)["files"]
    names = [e["path"] for e in entries]
    if len(names) != len(set(names)):
        raise ValueError("duplicate inventory path")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(names) | {inventory.name}:
        raise ValueError("package inventory membership changed")
    for entry in entries:
        path = local_path(root, entry["path"])
        if path.stat().st_size != entry["bytes"] or sha256_file(path) != entry["sha256"]:
            raise ValueError("package inventory bytes changed: " + entry["path"])
    return entries + [{"path": inventory.name, "sha256": sha256_file(inventory), "bytes": inventory.stat().st_size}]


def require_admission(decision, candidate_digest, rows):
    if (decision.get("dataset_admission_approved") is not True
            or decision.get("decision") != "include_all_24_in_next_training_partition"
            or decision.get("approved_candidate_manifest_sha256") != candidate_digest
            or decision.get("training_authorized") is not False
            or decision.get("formal_adsorption_acceptance") is not False):
        raise ValueError("separate admission decision or scope changed")
    if (decision["approved_sample_ids"] != [r["sample_id"] for r in rows]
            or decision["approved_ionic_steps"] != [r["ionic_step"] for r in rows]
            or decision["prospective_counts"] != {**COUNTS, "observed_heldout_quarantined": 16}):
        raise ValueError("approved membership/order/counts changed")
    eligibility(rows)


def scope():
    config = load(CONFIG)
    if config["expected_split_counts"] != COUNTS or config["training_authorized"] is not False:
        raise ValueError("data-only assembly scope changed")
    paths = {key: ROOT / item["path"] for key, item in config["inputs"].items()}
    for key, path in paths.items():
        if sha256_file(path) != config["inputs"][key]["sha256"]:
            raise ValueError("frozen input changed: " + key)
    prior, candidates = paths["prior_manifest"].parent, paths["candidate_manifest"].parent
    inventories = {"prior": inventory_entries(prior), "candidates": inventory_entries(candidates)}
    for path in (paths["admission_decision"], paths["admission_evidence"], candidates / "candidate_review.json",
                 candidates / "implementation_binding.json"):
        if not source_file_manifest_valid(load(path)):
            raise ValueError("source evidence binding stale: " + str(path))
    decision, rows = load(paths["admission_decision"]), load(paths["candidate_manifest"])["samples"]
    if load(paths["admission_verification"])["decision_sha256"] != sha256_file(paths["admission_decision"]):
        raise ValueError("decision verification binding changed")
    require_admission(decision, sha256_file(paths["candidate_manifest"]), rows)
    return config, paths, inventories, ROOT / config["output"]


def all_rows(manifest):
    return [r for rows in manifest["splits"].values() for r in rows] + manifest["quarantined_observed_heldout"]


def check_preserved(row, original):
    """Only relocate files and renormalize the unchanged uniform frame sampler."""
    allowed = {"structure_path", "label_source"}
    if original["split"] == "train":
        allowed.add("proposed_source_stage_sampling_probability")
        if row["proposed_source_stage_sampling_probability"] != 1 / 536:
            raise ValueError("training probability differs from uniform536")
    for key in set(row) | set(original):
        if key not in allowed and row.get(key) != original.get(key):
            raise ValueError("preserved source field changed: " + key)


def dependencies(paths):
    return [CONFIG, *paths.values(), Path(__file__), Path(__file__).with_name("verify.py"),
            ROOT / "docs/reviews/fe110_force_package_20261113/README.md",
            ROOT / "archive/fe110_combined_force_package_20261023/prepare.py",
            ROOT / "archive/fe110_combined_force_package_20261023/verify.py",
            ROOT / "archive/fe110_combined_force_package_20261023/role_helpers.py",
            ROOT / "archive/fe110_force_package_20261027/verify.py",
            ROOT / "archive/fe110_c3_lowforce_candidates_20261109/assess_admission.py",
            ROOT / "archive/fe110_c3_lowforce_candidates_20261109/verify.py",
            ROOT / "scripts/artifact_io.py", ROOT / "scripts/adsorption/force_finetune.py",
            ROOT / "scripts/adsorption/force_role_data.py"]


def run():
    _, paths, inventories, output = scope()
    if (output / "package_summary.json").exists():
        inventory_entries(output)
        if not source_file_manifest_valid(load(output / "assembly_request.json")):
            raise ValueError("completed assembly source binding stale")
        return load(output / "package_summary.json")
    prior, candidates = paths["prior_manifest"].parent, paths["candidate_manifest"].parent
    old = load_manifest(paths["prior_manifest"])
    additions = load(paths["candidate_manifest"])["samples"]
    original_rows = all_rows(old)
    if len(original_rows) != 659 or len({r["sample_id"] for r in original_rows + additions}) != 683:
        raise ValueError("original/additional sample identity collision")
    output.mkdir(parents=True, exist_ok=True)
    owner.save_once(output / "assembly_request.json", {
        "document_kind": "data_only_force_package_assembly", "source_files": source_file_manifest(dependencies(paths)),
        "source_inventory_sha256": {key: sha256_file(paths[key + "_inventory"])
                                    for key in ("prior", "candidate")},
        "training_authorized": False, "new_compute": False, "expected_split_counts": COUNTS})
    documentation = ROOT / "docs/reviews/fe110_force_package_20261113/README.md"
    owner.copy_checked(documentation, output / "README.md", sha256_file(documentation))
    # Preserve raw candidate evidence and the separate admission decision as exact byte snapshots.
    for entry in inventories["candidates"]:
        owner.copy_checked(candidates / entry["path"], output / "provenance/c3_candidates" / entry["path"], entry["sha256"])
    for key, path in paths.items():
        owner.copy_checked(path, output / "provenance/inputs" / (key + ".json"), sha256_file(path))
    for path in sorted((prior / "source_archives").glob("*.json")):
        owner.copy_checked(path, output / "source_archives" / path.name, sha256_file(path))
    sources = [(copy.deepcopy(r), prior, r["label_source"], None) for r in original_rows]
    for original in additions:
        row = copy.deepcopy(original)
        row.update(source_collection=COLLECTION,
                   stage="early_lowforce_process" if row["ionic_step"] == 15 else "late_lowforce_process",
                   optimization_phase_annotation="early_process_not_stable_endpoint" if row["ionic_step"] == 15 else "late_lowforce_process")
        sources.append((row, candidates, original["label_source"], None))
    rows = owner.materialize(sources, output, [])
    owner.assert_group_isolation(rows)
    splits = {s: [r for r in rows if r["split"] == s] for s in COUNTS}
    if {s: len(v) for s, v in splits.items()} != COUNTS:
        raise ValueError("new package partition counts differ")
    owner.set_uniform_sampling(splits["train"])
    by_id = {r["sample_id"]: r for r in rows}
    for original in original_rows:
        check_preserved(by_id[original["sample_id"]], original)
    for original in additions:
        row = by_id[original["sample_id"]]
        row["raw_force_table_path"] = "provenance/c3_candidates/" + original["raw_force_table_path"]
        row["source_OUTCAR_path"] = "provenance/c3_candidates/source/OUTCAR"
    isolation = {"method": "reuse immutable reviewed geometry-isolation evidence; exact structure bytes preserved",
                 "prior_isolation": load(prior / "isolation_review.json"),
                 "additional_isolation": load(candidates / "isolation_review.json"),
                 "reserved_geometries": 513, "geometry_conflicts": [], "quarantined_sample_ids": [],
                 "reserved_forces_or_energies_used": False, "new_geometry_comparisons": 0,
                 "source_files": source_file_manifest([prior / "isolation_review.json", candidates / "isolation_review.json",
                                                       candidates / "candidate_review.json", paths["admission_evidence"]])}
    owner.save_once(output / "isolation_review.json", isolation)
    manifest = {k: copy.deepcopy(v) for k, v in old.items()
                if k not in ("splits", "quarantined_observed_heldout", "source_files")}
    manifest.update(splits=splits, quarantined_observed_heldout=[r for r in rows if r["split"] == "observed_heldout"],
                    source_files=source_file_manifest(dependencies(paths)),
                    prior_manifest_sha256=sha256_file(paths["prior_manifest"]), package_version="20261113_v1",
                    admission_decision_sha256=sha256_file(paths["admission_decision"]),
                    sampling_policy="uniform_frames_like_existing_control;renormalized over536training rows",
                    training_authorized=False, new_VASP=False, model_promoted=False)
    owner.save_once(output / "training_manifest.json", manifest)
    load_manifest(output / "training_manifest.json")
    receipt = owner.database("train", output, splits["train"])
    # Development content, row order, metadata, and actual SQLite bytes stay frozen.
    for name in ("development.db", "development_metadata.npz", "development_build_receipt.json"):
        owner.copy_checked(prior / name, output / name, sha256_file(prior / name))
    summary = {"status": "LOCAL_FORCE536_PACKAGE_PREPARED_NO_TRAINING", "split_counts": COUNTS,
               "source_rows": len(rows), "observed_heldout_quarantined": 16, "added_training_frames": 24,
               "training_source_counts": dict(Counter(r["source_collection"] for r in splits["train"])),
               "training_composition_counts": dict(Counter(r["composition"] for r in splits["train"])),
               "magnetic_levels_train": dict(Counter(r["magnetic_review_level"] for r in splits["train"])),
               "manifest_sha256": sha256_file(output / "training_manifest.json"), "train_database": receipt,
               "terminal_scheduler_status": None, "training_authorized": False, "training_executed": False,
               "new_DFT": False, "model_promoted": False, "formal_adsorption_acceptance": False,
               "source_files": source_file_manifest([output / "assembly_request.json", output / "training_manifest.json",
                                                     output / "isolation_review.json"])}
    # Recheck the original full inventories after all materialization writes.
    if inventories != {"prior": inventory_entries(prior), "candidates": inventory_entries(candidates)}:
        raise ValueError("original frozen packages changed during assembly")
    owner.save_once(output / "package_summary.json", summary)
    return summary


if __name__ == "__main__":
    try:
        result = run()
        print({k: result[k] for k in ("status", "split_counts", "source_rows")})
    except Exception as exc:
        output = ROOT / load(CONFIG)["output"]
        output.mkdir(parents=True, exist_ok=True)
        owner.save_once(output / ("failure_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"),
                        {"error": str(exc), "training_executed": False})
        raise
