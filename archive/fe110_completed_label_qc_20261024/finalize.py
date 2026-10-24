"""Preserve cumulative QC, check train isolation and plan status/file registration."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from archive.fe110_combined_force_package_20261023.prepare import isolate
from archive.fe110_reico_sampling93_20261022.submission_review import file_row
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.collect_completed_batch import FILES
from scripts.adsorption.reico_dataset_audit import reserved_geometries
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, source_file_manifest_valid
from scripts.registry_connection import open_registry
from scripts.registry_write import plan_registry_batch
from .run import CONFIG, ROOT, save_once, scope


def training_candidates(rows):
    return [{**r, "split": "train", "movable_fmax_eV_A": float(np.linalg.norm(
        np.asarray(r["forces_eV_per_A"])[18:], axis=1).max())} for r in rows
        if r["partition"] == "train" and r["data_qc_status"] == "PASS"]


def summarize():
    config, paths, _, previous, _ = scope()
    output = ROOT / config["output"]
    source = load_json_object(output / "new_label_qc_local_only.json")
    if (not source_file_manifest_valid(source)
            or not source_file_manifest_valid(load_json_object(output / "collection_binding.json"))):
        raise ValueError("new QC source binding changed")
    labels = source["samples"]
    if {r["sample_id"] for r in labels} & {r["sample_id"] for r in previous}:
        raise ValueError("new QC overlaps previous label review")
    for row in labels:
        directory = Path(row["structure_path"]).parent
        if any(sha256_file(directory / name) != row["input_output_hashes"][name] for name in FILES):
            raise ValueError("reviewed raw evidence changed")
    save_once(output / "all_selected_label_qc_local_only.json", {"samples": previous + labels,
        "source_files": source_file_manifest([paths["previous_labels"], output / "new_label_qc_local_only.json"])})
    cfg_path = ROOT / "configs/fe110_reico_pilot/coverage_audit_v1.json"
    cfg = load_json_object(cfg_path)
    prior_path = ROOT / cfg["prior_manifest"]
    inventory = ROOT / cfg["inventory"]
    reserved = reserved_geometries(load_json_object(inventory), load_json_object(prior_path),
                                  prior_path.parent, cfg["reserved_geometry_catalogs"])
    slab_path = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    bindings = source_file_manifest([CONFIG, cfg_path, inventory, prior_path, slab_path, Path(__file__),
        ROOT / "archive/fe110_combined_force_package_20261023/prepare.py",
        ROOT / "archive/fe110_10b_lowforce_20261023/legacy_helpers.py",
        ROOT / "scripts/adsorption/reico_dataset_audit.py",
        *[ROOT / path for path in cfg["reserved_geometry_catalogs"]],
        *sorted({Path(row["structure_path"]) for row, _ in reserved})])
    save_once(output / "isolation_binding.json", {"source_files": bindings, "threshold_A": 0.20})
    candidates = training_candidates(labels)
    eligible, isolation = isolate(candidates, output, reserved, read_poscar(slab_path), .20)
    save_once(output / "new_training_isolation.json", isolation)
    save_once(output / "eligible_training_labels_local_only.json", {"samples": eligible, "is_training_package": False,
        "source_files": source_file_manifest([output / "new_training_isolation.json", output / "isolation_binding.json",
                                              output / "new_label_qc_local_only.json"])})
    force_counts = {}
    for composition in sorted({r["composition"] for r in eligible}):
        rows = [r for r in eligible if r["composition"] == composition]
        force_counts[composition] = {"frames": len(rows), "movable_fmax_min_eV_A": min(r["movable_fmax_eV_A"] for r in rows),
            "movable_fmax_max_eV_A": max(r["movable_fmax_eV_A"] for r in rows),
            "movable_fmax_le_0_05": sum(r["movable_fmax_eV_A"] <= .05 for r in rows)}
    summary = load_json_object(output / "qc_summary.json")
    result = {"checked_at": summary["checked_at"], "new_labels_reviewed": len(labels),
        "new_qc_counts": summary["qc_counts"], "new_partitions": summary["partition_counts"],
        "all_selected_labels_reviewed": len(previous) + len(labels),
        "all_selected_qc_counts": dict(Counter(r["data_qc_status"] for r in previous + labels)),
        "all_selected_pass_partitions": dict(Counter(r["partition"] for r in previous + labels if r["data_qc_status"] == "PASS")),
        "new_isolated_train_eligible": len(eligible), "geometry_isolation": isolation,
        "new_train_force_by_composition": force_counts,
        "new_training_source_families": len({r["family_id"] for r in eligible}),
        "remaining_snapshot_jobs_not_DONE": sum(v for k, v in summary["scheduler_counts"].items() if k != "DONE"),
        "collection_failures": summary["failures"], "new_DFT_GPU_or_training": False,
        "frozen_training_package_366_changed": False, "previous_audit_view_378_changed": False,
        "joint_SOAP_coverage_recomputed": False, "magnetic_global_ground_state_verified": False,
        "source_files": source_file_manifest([CONFIG, output / "qc_summary.json", output / "new_training_isolation.json",
                                              output / "all_selected_label_qc_local_only.json", paths["frozen_manifest"], paths["previous_audit"]])}
    save_once(output / "batch_processing_summary.json", result)
    print({k: v for k, v in result.items() if k not in {"source_files", "geometry_isolation"}}, flush=True)


def registry_plan():
    config, _, _, _, _ = scope()
    output = ROOT / config["output"]
    summary = load_json_object(output / "batch_processing_summary.json")
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
                artifact["file_id"] = "file_" + calc + "_completed_qc20261024_" + path.name.replace(".", "_")
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
                changes.append({"status_change_id": "completed_qc20261024_" + calc,
                    "calculation_id": calc, "expected_workflow_status": job["workflow_status"],
                    "new_workflow_status": "done", "changed_at": snapshot["checked_at"], "reviewer": "Codex",
                    "reason": "Exact scheduler DONE;fixed-geometry force-label QC separately recorded;no endpoint acceptance"})
    if not labels:
        raise ValueError("no collected labels to register")
    for path in [CONFIG, output / "scheduler_snapshot.json", output / "collection_binding.json",
                 output / "new_label_qc_local_only.json", output / "qc_summary.json", output / "batch_processing_summary.json",
                 output / "new_training_isolation.json", output / "all_selected_label_qc_local_only.json",
                 output / "eligible_training_labels_local_only.json"]:
        artifact = file_row(path, calc, jid, remote, "batch_static_label_qc_provenance")
        artifact["file_id"] = "file_" + calc + "_batch_qc20261024_" + path.name.replace(".", "_")
        rows["files"].append(artifact)
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
        "batch_id": "fe110_completed_label_qc_20261024_v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": "Codex", "reason": "User-authorized completed static batch collection and QC;no reportable energies or training",
        "rows": rows, "workflow_status_changes": changes}
    save_once(output / "registry_batch.json", batch)
    plan = plan_registry_batch(ROOT / "data/project_registry.sqlite3", batch)
    save_once(output / "registry_plan.json", plan)
    print({k: plan[k] for k in ("plan_sha256", "scope", "insert_count", "update_count", "unchanged_count")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("summarize", "registry-plan"))
    args = parser.parse_args()
    summarize() if args.action == "summarize" else registry_plan()
