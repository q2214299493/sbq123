"""Validate existing train/dev labels and bind a prediction scope; never launch."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from scripts.adsorption.force_finetune import validate_label_row
from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_reico_pilot300_20261022"
OUT = BASE / "force_diagnosis536_20261114_v1"
PACKAGE = BASE / "combined_force_package_20261113_v1"


def force_stage(maximum):
    if maximum <= .02:
        return "DFT_fmax_le0p02"
    if maximum <= .05:
        return "DFT_fmax_0p02_to0p05"
    if maximum <= .10:
        return "DFT_fmax_0p05_to0p10"
    if maximum <= .50:
        return "DFT_fmax_0p10_to0p50"
    return "DFT_fmax_gt0p50"


def inspect_row(row, evidence, split):
    validate_label_row(PACKAGE, row)
    if not evidence["coordinate_force_match"] or not evidence["electronic_raw_pass"]:
        raise ValueError("raw coordinate/SCF evidence does not pass")
    forces = np.asarray(row["forces_eV_per_A"], dtype=float)
    free = np.asarray([i for i in range(len(forces)) if i not in row["fixed_atom_indices_0based"]])
    maximum = float(np.linalg.norm(forces[free], axis=1).max())
    strict = evidence["energy_force_evidence_ready_for_review"]
    weights = np.asarray(row["proposed_per_atom_loss_weights"], dtype=float)
    groups = row["force_role_groups"]
    if sorted(i for values in groups.values() for i in values) != free.tolist():
        raise ValueError("role masks do not partition free atoms")
    return {"sample_id": row["sample_id"], "partition": split, "composition": row["composition"],
            "source_job_id": row.get("source_job_id"), "family_id": row.get("family_id", row.get("calculation_group")),
            "structure_path": str(PACKAGE / row["structure_path"]), "structure_sha256": row["structure_sha256"],
            "source_OUTCAR_sha256": row["source_OUTCAR_sha256"], "physical_label_key": evidence.get("physical_label_key"),
            "force_unit": "eV/Angstrom", "qualification_scope": "STRICT_RAW_E_F_LOCALMAG" if strict else "ORIGINAL_APPROVED_FORCE_ONLY_SCOPE_LOCALMAG_MISSING",
            "original_magnetic_grade": evidence["original_magnetic_grade_preserved"], "raw_magnetic_grade": evidence["raw_magnetic_grade"],
            "original_QC_flags_preserved": evidence["flags"], "DFT_movable_fmax_eV_A": maximum, "force_stage": force_stage(maximum),
            "fixed_atom_indices_0based": row["fixed_atom_indices_0based"], "symbols": row["symbols"],
            "force_role_groups": groups, "DFT_forces_eV_per_A": row["forces_eV_per_A"],
            "original_per_atom_weights": row["proposed_per_atom_loss_weights"],
            "per_atom_weights_uniform_over_free_atoms": bool(np.allclose(weights[free], weights[free[0]], atol=1e-12, rtol=0)),
            "original_weight_sums_by_role": {role: float(weights[indices].sum()) for role, indices in groups.items()},
            "new_scientific_admission": False}


def run():
    manifest_path = PACKAGE / "training_manifest.json"
    manifest = load_json_object(manifest_path)
    side_path = BASE / "energy_reaction_sidecar_20261113_v1/energy_label_sidecar_final_v2.json"
    evidence = {(r["partition"], r["sample_id"]): r for r in load_json_object(side_path)["records"] if r["pool"] == "frozen536"}
    records, bound = [], {Path(__file__), manifest_path, side_path, ROOT / "scripts/adsorption/force_finetune.py"}
    for split in ("train", "development"):
        for row in manifest["splits"][split]:
            records.append(inspect_row(row, evidence[(split, row["sample_id"])], split))
            bound.update([PACKAGE / row["structure_path"], PACKAGE / row["label_source"]["path"]])
    if len(records) != 614 or len({r["sample_id"] for r in records}) != 614:
        raise ValueError("expected unique536+78 source scope")
    groups = defaultdict(list)
    for row in records:
        groups[(row["partition"], row["qualification_scope"], row["composition"])].append(row)
    summary = [{"partition": key[0], "qualification_scope": key[1], "composition": key[2], "frames": len(values),
                "force_stage_counts": dict(Counter(r["force_stage"] for r in values)),
                "fmax_min_eV_A": min(r["DFT_movable_fmax_eV_A"] for r in values),
                "fmax_max_eV_A": max(r["DFT_movable_fmax_eV_A"] for r in values)} for key, values in sorted(groups.items())]
    write_json_exclusive(OUT / "qualified_reference_labels.json", {"status": "LABELS_VERIFIED_PREDICTIONS_PENDING", "records": records,
                         "summary": summary, "test_quarantine_or_external_frames_included": False,
                         "source_files": source_file_manifest(sorted(bound))})
    source = load_json_object(OUT / "request_context.json")
    samples = [{"sample_id": r["sample_id"], "partition": r["partition"], "structure_sha256": r["structure_sha256"],
                "remote_existing_structure_path": "/home/sbq/sbq/fe110_force_training536_smoke_20261113_v1/control/" + str(Path(r["structure_path"]).relative_to(PACKAGE)).replace("\\", "/"),
                "local_structure_path": r["structure_path"]} for r in records]
    write_json_exclusive(OUT / "prediction_scope.json", {
        "status": "GPU_UNBOUND_NOT_LAUNCHED", "request_user_quote": source["user_instruction"], "samples": samples,
        "model_sha256": source["model_sha256"], "local_model_path": source["model_path"],
        "remote_existing_model_path": "/home/sbq/sbq/fe110_force_training536_execution_20261113_v4/output/job_14505/candidate.pt",
        "new_output_root_proposed": "/home/sbq/sbq/force_diagnosis536_20261114_v1", "max_GPU_count": 1, "max_GPU_seconds_proposed": 600,
        "required_before_launch": ["fresh successful GPU/Slurm/native environment check", "hash-bound host/GPU UUID and inference execution scope", "native patched_calc physical force normalization and one-frame check"],
        "training_DFT_relaxation_or_heldout_use": False, "backend_policy_modified": False,
        "source_files": source_file_manifest([OUT / "request_context.json", OUT / "qualified_reference_labels.json"])})
    print({"frames": len(records), "strict": sum(r["qualification_scope"] == "STRICT_RAW_E_F_LOCALMAG" for r in records),
           "uniform_atom_weights_by_split": {s: sum(r["per_atom_weights_uniform_over_free_atoms"] for r in records if r["partition"] == s) for s in ("train", "development")}}, flush=True)


if __name__ == "__main__":
    run()
