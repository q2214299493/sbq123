"""Independently read final raw forces and validate the source-only plan."""
from __future__ import annotations

import numpy as np
from ase.io import read

from archive.fe110_grouped_qc_20261026.review import raw_frames
from archive.fe110_combined_force_package_20261023.prepare import save_once
from scripts.artifact_io import sha256_file, source_file_manifest, source_file_manifest_valid
from .audit import PACKAGE, frozen_hashes
from .collect import OUTPUT, ROOT, load
from .plan import guard_probes, proposed_role


def run():
    plan, inventory = load(OUTPUT / "source_plan.json"), load(OUTPUT / "physical_inventory.json")
    if not source_file_manifest_valid(plan) or not source_file_manifest_valid(inventory):
        raise ValueError("source plan binding changed")
    if frozen_hashes() != inventory["frozen_hashes_before_after"]:
        raise ValueError("frozen package hash changed")
    sources = []
    for summary in inventory["source_summaries"]:
        if not source_file_manifest_valid(summary):
            raise ValueError("physical source snapshot changed")
        bindings = summary["source_files"]
        outcar = next(r for r in bindings if r["path"].endswith("OUTCAR"))
        from pathlib import Path
        initial = read(Path(outcar["path"]).with_name("POSCAR"), format="vasp")
        final = read(outcar["path"], format="vasp-out", index=-1)
        raw = raw_frames(Path(outcar["path"]), len(initial))[-1]
        if (not np.array_equal(final.get_forces(apply_constraint=False), raw["forces_eV_per_A"])
                or not np.array_equal(final.positions, raw["positions_A"])
                or final.get_chemical_symbols() != initial.get_chemical_symbols()):
            raise ValueError("independent ASE raw force/atom/position mismatch")
        sources.append({"job_id": summary["job_id"], "final_raw_force_components_verified": len(final) * 3,
                        "OUTCAR_sha256": sha256_file(Path(outcar["path"]))})
    rows = plan["near_force_candidate_references"]
    for row in rows:
        if proposed_role(row) != row["proposed_role"]:
            raise ValueError("source role changed")
    external = [r for r in rows if r["proposed_role"] == "external_C2_isomer_force_candidate_not_admitted"]
    if len(external) != 26 or {r["source_job_id"] for r in external} != {"9927794", "9927514"}:
        raise ValueError("external C2 source membership changed")
    if any(r["C_H_counts"] != [0, 3] or r["QC_errors"] or r["adsorbate_component_count"] != 1 for r in external):
        raise ValueError("external isomer/physical QC changed")
    if any(v["within0p20A"] for r in external for v in r["geometry_isolation"].values()):
        raise ValueError("external candidate overlaps frozen partitions")
    manifest = load(PACKAGE / "training_manifest.json")
    if not set(plan["existing_test_low_force_ids"]) <= {r["sample_id"] for r in manifest["splits"]["heldout"]}:
        raise ValueError("locked test identity changed")
    if (plan["new_dataset_or_loader_created"] or plan["existing_partitions_changed"]
            or plan["new_DFT_submitted"] or plan["training_or_model_inference_run"]):
        raise ValueError("source inventory exceeded read-only scope")
    result = {"status": "PASS_INDEPENDENT_SOURCE_PLAN_NO_EXECUTION", "independent_ASE_last_frame_sources": sources,
              "near_force_candidates_reviewed": len(rows), "external_C2_isomer_candidate_frames": len(external),
              "current_C2_near_frame_geometry_comparisons": 93 * 75, "source_role_guard_probes": guard_probes(rows),
              "C3_nontraining_source_frames_in_scope": plan["C3_nontraining_trajectory_scope"]["total_frames"],
              "C3_verified_intact_nearstable_sources": 0, "frozen512_and536_unchanged": True,
              "no_training_newDFT_or_partition_changes": True,
              "source_files": source_file_manifest([OUTPUT / "source_plan.json", OUTPUT / "physical_inventory.json",
                                                    ROOT / "archive/fe110_independent_nearstable_20261113/verify.py"])}
    save_once(OUTPUT / "independent_verification.json", result)
    return result


if __name__ == "__main__":
    result = run()
    print({"status": result["status"], "ASE_sources": len(result["independent_ASE_last_frame_sources"]),
           "external_C2_candidates": result["external_C2_isomer_candidate_frames"]})
