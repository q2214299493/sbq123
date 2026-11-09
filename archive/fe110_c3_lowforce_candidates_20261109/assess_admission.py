"""Generate evidence for a separate data-admission decision; never merge/train."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
from ase.io import read

from scripts.adsorption.force_finetune import validate_label_row
from scripts.adsorption.reico_selection import frame_distance
from scripts.artifact_io import sha256_file, source_file_manifest, source_file_manifest_valid
from .prepare import BASE, FROZEN, OUTPUT, frozen_hashes, load, save_json

ASSESSMENT = BASE / "c3_lowforce_admission_20261109_v1"


def eligibility(rows):
    """Reject physical/data-isolation failures; no scheduler-state substitution."""
    if len(rows) != 24 or len({r["sample_id"] for r in rows}) != 24:
        raise ValueError("reviewed24 membership is not unique")
    for row in rows:
        if row["split"] != "train" or row["partition"] != "train" or row["calculation_group"] != "reico_family_0099":
            raise ValueError("candidate split/family identity differs")
        if not row["electronic_converged"] or not row["geometry_review_pass"] or row["magnetic_review_flags"]:
            raise ValueError("candidate physical QC failed")
        if row["magnetic_review_level"] != "LOCAL_MOMENTS_REVIEWED_POSITIVE_FE":
            raise ValueError("candidate magnetic review scope differs")
        forces = np.asarray(row["forces_eV_per_A"], dtype=float)
        if forces.shape != (51, 3) or not np.isfinite(forces).all():
            raise ValueError("invalid candidate raw forces")
        measured = float(np.linalg.norm(forces[18:], axis=1).max())
        if measured > .05 or abs(measured - row["movable_fmax_eV_A"]) > 1e-12:
            raise ValueError("low-force eligibility differs from raw forces")


def run():
    manifest = load(OUTPUT / "candidate_manifest.json")
    rows = manifest["samples"]
    eligibility(rows)
    request = load(OUTPUT / "request.json")
    if frozen_hashes() != request["frozen512_before"]:
        raise ValueError("frozen512 inputs changed")
    if not source_file_manifest_valid(load(OUTPUT / "candidate_review.json")):
        raise ValueError("separate candidate review binding stale")
    if not all(sha256_file(OUTPUT / e["path"]) == e["sha256"] for e in load(OUTPUT / "package_inventory.json")["files"]):
        raise ValueError("candidate package inventory differs")
    original = load(FROZEN / "training_manifest.json")
    old = [r for r in original["splits"]["train"] if r.get("composition", r.get("formula_without_slab")) == "C3H2O"]
    old_ids = {r["sample_id"] for values in original["splits"].values() for r in values}
    if old_ids & {r["sample_id"] for r in rows}:
        raise ValueError("sample identifier collision")
    references = [(r, read(FROZEN / r["structure_path"], format="vasp")) for r in old]
    diagnostics = []
    for row in rows:
        validate_label_row(OUTPUT, row)
        atoms = read(OUTPUT / row["structure_path"], format="vasp")
        distance, nearest = min(((frame_distance(atoms, geometry), ref) for ref, geometry in references), key=lambda x: x[0])
        delta = float(np.linalg.norm(np.asarray(row["forces_eV_per_A"])[18:] - np.asarray(nearest["forces_eV_per_A"])[18:], axis=1).max())
        diagnostics.append({"sample_id": row["sample_id"], "ionic_step": row["ionic_step"],
            "fmax_eV_A": row["movable_fmax_eV_A"], "nearest_existing_id": nearest["sample_id"],
            "nearest_existing_distance_A": distance, "nearest_existing_max_force_delta_eV_A": delta,
            "near_geometry_and_force_duplicate": distance <= .02 and delta <= .02,
            "coordination_signature": row["coordination_signature"],
            "phase_annotation": "early_low_force_process_not_stable_endpoint" if row["ionic_step"] == 15 else "late_low_force_process"})
    if any(r["near_geometry_and_force_duplicate"] for r in diagnostics):
        raise ValueError("candidate duplicates an existing training label")
    old_norms = [float(np.linalg.norm(np.asarray(r["forces_eV_per_A"])[18:], axis=1).max()) for r in old]
    evidence = {"document_kind": "force_candidate_admission_evidence", "decision_made": False,
        "candidate_count": len(rows), "source_family_count": len({r["family_id"] for r in rows}),
        "family_already_present_in_training": all(any(o["calculation_group"] == r["calculation_group"] for o in old) for r in rows),
        "baseline_training_count": len(original["splits"]["train"]), "prospective_training_count": len(original["splits"]["train"]) + len(rows),
        "baseline_C3_count": len(old), "prospective_C3_count": len(old) + len(rows),
        "baseline_C3_lowforce_le0p05": sum(f <= .05 for f in old_norms), "prospective_C3_lowforce_le0p05": sum(f <= .05 for f in old_norms) + len(rows),
        "baseline_C3_min_fmax_eV_A": min(old_norms), "candidate_min_fmax_eV_A": min(r["movable_fmax_eV_A"] for r in rows),
        "candidate_coordination_counts": dict(Counter(r["coordination_signature"] for r in rows)),
        "candidate_uniform_frame_fraction_if_merged": len(rows) / (len(original["splits"]["train"]) + len(rows)),
        "protected_split_counts_unchanged": {k: len(original["splits"][k]) for k in ("development", "heldout")},
        "observed_heldout_quarantine_unchanged": len(original["quarantined_observed_heldout"]),
        "candidate_diagnostics": diagnostics, "training_authorized": False, "merged_into_existing_manifest": False,
        "formal_adsorption_acceptance": False, "source_files": source_file_manifest([
            Path(__file__), OUTPUT / "candidate_manifest.json", OUTPUT / "candidate_review.json", OUTPUT / "package_inventory.json",
            OUTPUT / "independent_verification.json", FROZEN / "training_manifest.json"])}
    save_json(ASSESSMENT / "admission_evidence.json", evidence)
    return {k: v for k, v in evidence.items() if k not in ("candidate_diagnostics", "source_files")}


if __name__ == "__main__":
    print(__import__("json").dumps(run()))
