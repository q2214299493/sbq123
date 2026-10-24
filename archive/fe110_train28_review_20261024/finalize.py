"""Isolate newly reviewed training labels and quantify their incremental gap contribution without double-counting."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from archive.fe110_completed_label_qc_20261024.finalize import training_candidates
from archive.fe110_combined_force_package_20261023.prepare import isolate
from archive.fe110_reico_sampling93_20261022.submission_review import file_row
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.collect_completed_batch import FILES
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from scripts.registry_connection import open_registry
from scripts.registry_write import plan_registry_batch
from .run import DEFAULT_CONFIG, ROOT, save_once, scope


def gap_contributions(groups, prior_ids, new_ids):
    """Count a joint type once, even when another frame of that type completes."""
    prior = [g for g in groups if set(g["unreviewed_selected_input_ids"]) & prior_ids]
    remaining = [g for g in groups if not set(g["unreviewed_selected_input_ids"]) & prior_ids]
    covered = [g for g in remaining if set(g["unreviewed_selected_input_ids"]) & new_ids]
    missing = [g for g in remaining if not set(g["unreviewed_selected_input_ids"]) & new_ids]
    return covered, missing, prior


def summarize(config_path=DEFAULT_CONFIG):
    config, paths, _, previous, _, groups = scope(config_path)
    output = ROOT / config["output"]
    new = load_json_object(output / "new_label_qc_local_only.json")
    if (not source_file_manifest_valid(new)
            or not source_file_manifest_valid(load_json_object(output / "main_collection_binding.json"))
            or not source_file_manifest_valid(load_json_object(output / "scope_binding.json"))):
        raise ValueError("review source binding changed")
    labels = new["samples"]
    if any(r["partition"] != "train" for r in labels):
        raise ValueError("reserved label entered training-only review")
    if {r["sample_id"] for r in labels} & {r["sample_id"] for r in previous}:
        raise ValueError("previously reviewed label duplicated")
    for row in labels:
        directory = Path(row["structure_path"]).parent
        if any(sha256_file(directory / name) != row["input_output_hashes"][name] for name in FILES):
            raise ValueError("raw collected evidence changed")
    save_once(output / "all_selected_label_qc_local_only.json", {"samples": previous + labels,
        "source_files": source_file_manifest([paths["previous_labels"], output / "new_label_qc_local_only.json"])})
    cfg_path = ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json"
    cfg = load_json_object(cfg_path)
    prior_path = ROOT / cfg["prior_manifest"]
    inventory = ROOT / cfg["inventory"]
    reserved = reserved_geometries(load_json_object(inventory), load_json_object(prior_path),
                                  prior_path.parent, cfg["reserved_geometry_catalogs"])
    slab_path = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    save_once(output / "isolation_binding.json", {"source_files": source_file_manifest([
        config_path, Path(__file__), cfg_path, inventory, prior_path, slab_path,
        ROOT / "archive/fe110_completed_label_qc_20261024/finalize.py",
        ROOT / "scripts/adsorption/reico_dataset_audit.py",
        ROOT / "archive/fe110_combined_force_package_20261023/prepare.py",
        ROOT / "archive/fe110_10b_lowforce_20261023/legacy_helpers.py",
        *[ROOT / path for path in cfg["reserved_geometry_catalogs"]],
        *sorted({Path(r["structure_path"]) for r, _ in reserved})])})
    eligible, isolation = isolate(training_candidates(labels), output, reserved, read_poscar(slab_path), .20)
    save_once(output / "new_training_isolation.json", isolation)
    save_once(output / "eligible_training_labels_local_only.json", {"samples": eligible, "is_training_package": False,
        "source_files": source_file_manifest([output / "isolation_binding.json", output / "new_training_isolation.json",
                                              output / "new_label_qc_local_only.json"])})
    eligible_ids = {r["sample_id"] for r in eligible}
    prior_eligible = []
    for key in ("previous_eligible16", "previous_eligible1"):
        prior_doc = load_json_object(paths[key])
        if not source_file_manifest_valid(prior_doc):
            raise ValueError("prior eligible label binding changed")
        prior_eligible.extend(prior_doc["samples"])
    if any(r["partition"] != "train" or r["data_qc_status"] != "PASS" for r in prior_eligible):
        raise ValueError("prior coverage candidate not PASS train")
    prior_ids = {r["sample_id"] for r in prior_eligible}
    covered, still_missing, previously_covered = gap_contributions(groups, prior_ids, eligible_ids)
    save_once(output / "gap_contribution.json", {"covered_by_new_eligible_labels": covered,
        "previously_covered_groups": previously_covered,
        "remaining_of_original40_groups": still_missing,
        "note": "Incremental contribution excludes types already covered by prior17 candidates;no package or SOAP recomputation"})
    forces = {}
    for composition in sorted({r["composition"] for r in eligible}):
        rows = [r for r in eligible if r["composition"] == composition]
        forces[composition] = {"frames": len(rows), "minimum_movable_fmax_eV_A": min(r["movable_fmax_eV_A"] for r in rows),
            "maximum_movable_fmax_eV_A": max(r["movable_fmax_eV_A"] for r in rows),
            "low_force_le_0p05": sum(r["movable_fmax_eV_A"] <= .05 for r in rows)}
    qc = load_json_object(output / "qc_summary.json")
    result = {"checked_at": qc["checked_at"], "scope": config["expected_remaining"], "scheduler_counts": qc["scheduler_counts"],
        "new_reviewed": len(labels), "new_qc_counts": qc["qc_counts"], "new_train_eligible": len(eligible),
        "scope_not_yet_reviewed": config["expected_remaining"] - len(labels), "collection_failures": qc["failures"],
        "additional_gap_groups": len(covered),
        "covered_of_original40_gap_groups": len(previously_covered) + len(covered), "remaining_of_original40_gap_groups": len(still_missing),
        "joint_gaps_if_new_candidates_admitted": 229 - len(previously_covered) - len(covered),
        "all_selected_labels_reviewed": len(previous) + len(labels),
        "all_selected_qc_counts": dict(Counter(r["data_qc_status"] for r in previous + labels)),
        "all_selected_pass_partitions": dict(Counter(r["partition"] for r in previous + labels if r["data_qc_status"] == "PASS")),
        "force_by_composition": forces, "geometry_isolation": isolation,
        "original366package_changed": False, "current440audit_changed": False, "new_DFT_GPU_or_training": False,
        "source_files": source_file_manifest([config_path, output / "qc_summary.json", output / "new_training_isolation.json",
            output / "all_selected_label_qc_local_only.json", output / "gap_contribution.json",
            paths["previous_audit"], paths["frozen_manifest"], paths["gaps"],
            paths["previous_eligible16"], paths["previous_eligible1"]])}
    save_once(output / "summary.json", result)
    print({k: v for k, v in result.items() if k not in {"source_files", "geometry_isolation"}}, flush=True)


def registry_plan(config_path=DEFAULT_CONFIG):
    config, _, _, _, _, _ = scope(config_path)
    output = ROOT / config["output"]
    summary = load_json_object(output / "summary.json")
    if not source_file_manifest_valid(summary):
        raise ValueError("batch summary source binding changed")
    existing_plan = output / "registry_plan.json"
    if existing_plan.exists():
        plan = load_json_object(existing_plan)
        print({k: plan[k] for k in ("plan_sha256", "scope", "insert_count", "update_count", "unchanged_count")})
        return
    labels = load_json_object(output / "new_label_qc_local_only.json")["samples"]
    snapshot = load_json_object(output / "scheduler_snapshot.json")
    snapshot_jobs = {r["name"]: r for r in snapshot["jobs"]}
    rows = {"files": [], "job_status_history": []}
    changes = []
    with open_registry(ROOT / "data/project_registry.sqlite3") as connection:
        for row in labels:
            job = connection.execute("SELECT j.job_record_id,j.calculation_id,j.remote_directory,c.workflow_status "
                "FROM jobs j JOIN calculations c ON c.calculation_id=j.calculation_id "
                "WHERE j.server_alias=? AND j.scheduler_job_id=?", ("sunboquan-codex", row["source_job_id"])).fetchone()
            if job is None or job["remote_directory"] != snapshot_jobs[row["sample_id"]]["remote_dir"]:
                raise ValueError("exact registered job/target missing")
            calc, jid, remote = job["calculation_id"], job["job_record_id"], job["remote_directory"]
            directory = Path(row["structure_path"]).parent
            evidence_files = [*[directory / name for name in FILES], directory / "collection.json",
                              output / "case_qc" / (row["sample_id"] + ".json")]
            for path in evidence_files:
                artifact = file_row(path, calc, jid, remote, "static_label_qc_evidence")
                artifact["file_id"] = "file_" + calc + "_" + Path(config["output"]).name + "_" + path.name.replace(".", "_")
                if path.name in FILES:
                    artifact["remote_path"] = remote + "/" + path.name
                rows["files"].append(artifact)
            source_text = "\n".join(line for line in snapshot["stdout"].splitlines()
                if line.split() and line.split()[0] in {"JOBID", row["source_job_id"]}) + "\n"
            rows["job_status_history"].append({"job_record_id": jid, "scheduler_status": "DONE",
                "scientific_status": "STATIC_FORCE_LABEL_QC_" + row["data_qc_status"] + ";not an accepted adsorption endpoint",
                "checked_at": snapshot["checked_at"], "source_command": " ".join(snapshot["command"]),
                "source_text": source_text, "reviewer": "Codex",
                "notes": "Exact frozen geometry/raw-force/magnetic label only;partition=" + row["partition"] + ";QCsha=" + sha256_file(evidence_files[-1])})
            if job["workflow_status"] != "done":
                changes.append({"status_change_id": Path(config["output"]).name + "_" + calc,
                    "calculation_id": calc, "expected_workflow_status": job["workflow_status"],
                    "new_workflow_status": "done", "changed_at": snapshot["checked_at"], "reviewer": "Codex",
                    "reason": "Exact scheduler DONE;fixed-geometry force-label QC separately recorded;no endpoint acceptance"})
    if not labels:
        raise ValueError("no collected labels to register")
    for path in [config_path, output / "scheduler_snapshot.json", output / "main_collection_binding.json",
                 output / "new_label_qc_local_only.json", output / "qc_summary.json", output / "summary.json",
                 output / "new_training_isolation.json", output / "all_selected_label_qc_local_only.json",
                 output / "eligible_training_labels_local_only.json"]:
        artifact = file_row(path, calc, jid, remote, "batch_static_label_qc_provenance")
        artifact["file_id"] = "file_" + calc + "_" + Path(config["output"]).name + "_batch_" + path.name.replace(".", "_")
        rows["files"].append(artifact)
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_" + Path(config["output"]).name, "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": "Codex", "reason": "User-authorized remaining original training input review;no reportable energies or training",
        "rows": rows, "workflow_status_changes": changes}
    save_once(output / "registry_batch.json", batch)
    plan = plan_registry_batch(ROOT / "data/project_registry.sqlite3", batch)
    save_once(output / "registry_plan.json", plan)
    print({k: plan[k] for k in ("plan_sha256", "scope", "insert_count", "update_count", "unchanged_count")})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("summarize", "registry-plan"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    summarize(args.config) if args.action == "summarize" else registry_plan(args.config)
