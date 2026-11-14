"""List already labelled training-side backups before proposing duplicate DFT."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from .collect import BASE, OUT
from .network import export_csv


def run():
    side = BASE / "energy_reaction_sidecar_20261113_v1"
    catalog_path = side / "energy_reuse_catalog_v2.json"
    labels_path = side / "energy_label_sidecar_final_v2.json"
    coverage_path = OUT / "reico536_coverage_v3.json"
    catalog = load_json_object(catalog_path)["records"]
    labels = load_json_object(labels_path)["records"]
    by_key = {r["physical_label_key"]: r for r in labels if r.get("energy_force_evidence_ready_for_review")}
    gaps = {(r["composition"], r["joint_signature"]): r for r in load_json_object(coverage_path)["groups"]}
    backups = [r for r in catalog if r["future_energy_reuse_review_candidate"] and not any(
        a["pool"] == "frozen536" and a["partition"] == "train" for a in r["aliases"])]
    records = []
    bound = {Path(__file__), catalog_path, labels_path, coverage_path}
    for row in backups:
        label = by_key[row["physical_label_key"]]
        path = Path(label["structure_path"])
        record = {"candidate_id": label["sample_id"], "physical_label_key": row["physical_label_key"],
                  "composition": row["composition"], "structure_path": str(path), "structure_sha256": sha256_file(path),
                  "source_OUTCAR_path": label["source_OUTCAR_path"], "source_OUTCAR_sha256": row["source_OUTCAR_sha256"],
                  "DFT_ionic_step": row["DFT_ionic_step"], "source_byte_range": label["source_byte_range"],
                  "source_job_id": label["source_job_id"], "family_id": label["family_id"],
                  "aliases": row["aliases"], "coordinate_force_match": label["coordinate_force_match"],
                  "raw_positive_Fe_local_moments": label["raw_positive_Fe_local_moments"], "compatibility": label["compatibility"],
                  "original_magnetic_grade_preserved": label["original_magnetic_grade_preserved"],
                  "flags_preserved": label["flags"], "joint_signature_at_default_scale": label["graph"]["joint_signature"],
                  "covers_missing536_joint_type_at_default_scale": (row["composition"], label["graph"]["joint_signature"]) in gaps,
                  "permitted_use": "TRAINING_SIDE_REUSE_REVIEW_NOT_INDEPENDENT_VALIDATION_OR_AUTOMATIC_ADMISSION",
                  "absolute_AQ_energy_target_ready": False, "new_DFT_for_same_compatible_label": "NOT_NEEDED",
                  "existing_packages_changed": False}
        records.append(record)
        bound.add(path)
    result = {"records": records, "unique_existing_labels": len(catalog), "ready_E_F_localmag_labels": sum(r["raw_E_F_local_magnetic_evidence_ready"] for r in catalog),
              "training_side_future_reuse_review": sum(r["future_energy_reuse_review_candidate"] for r in catalog),
              "outside536_backups": len(backups), "backup_compositions": dict(Counter(r["composition"] for r in backups)),
              "backup_covered_missing_joint_types": len({(r["composition"], r["joint_signature_at_default_scale"]) for r in records if r["covers_missing536_joint_type_at_default_scale"]}),
              "new_training_admission_or_DFT": False, "source_files": source_file_manifest(sorted(bound))}
    write_json_exclusive(OUT / "compatible_backup_reuse.json", result)
    export_csv(OUT / "compatible_backup_reuse.csv", records, ["candidate_id", "composition", "physical_label_key", "source_job_id", "family_id",
               "structure_path", "structure_sha256", "source_OUTCAR_path", "source_OUTCAR_sha256", "DFT_ionic_step", "coordinate_force_match",
               "raw_positive_Fe_local_moments", "original_magnetic_grade_preserved", "covers_missing536_joint_type_at_default_scale",
               "permitted_use", "new_DFT_for_same_compatible_label"])
    print({k: result[k] for k in ("unique_existing_labels", "ready_E_F_localmag_labels", "outside536_backups", "backup_compositions", "backup_covered_missing_joint_types")}, flush=True)


if __name__ == "__main__":
    run()
