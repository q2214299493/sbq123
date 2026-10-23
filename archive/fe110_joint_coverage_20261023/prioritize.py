"""Separate pending selected labels from residual geometry-only candidates."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
from ase.io import read

from scripts.adsorption.reico_joint_coverage import fixed_threshold_soap, missing_environment_groups
from scripts.artifact_io import source_file_manifest, source_file_manifest_valid
from .run import CONFIG, ROOT, load, save_once


def records(rows, cache_map):
    result = []
    for row in rows:
        with np.load(cache_map[row["sample_id"]]["path"], allow_pickle=False) as data:
            symbols = row.get("symbols")
            if symbols is None:
                symbols = read(row["structure_path"], format="vasp").get_chemical_symbols()
            result.append({"sample_id": row["sample_id"], "family_id": row["family_id"],
                           "partition": "train", "composition": row["composition"],
                           "roles": np.array(symbols)[data["centers"]], "vectors": data["vectors"]})
    return result


def prioritize():
    config = load(CONFIG)
    output = ROOT/config["output"]
    summary = load(output/"summary.json")
    if not source_file_manifest_valid(summary):
        raise ValueError("joint audit source binding stale")
    training = load(output/"training_environments.json")["frames"]
    pool = load(output/"pool_environments.json")["frames"]
    selected = {r["sample_id"] for r in load(ROOT/config["inputs"]["selection"]["path"])["selected"] if r["partition"] == "train"}
    current_ids = {r["sample_id"] for r in training}
    not_admitted = [r for r in pool if r["sample_id"] in selected-current_ids]
    if len(not_admitted) != 121:
        raise ValueError("unexpected original selected/unadmitted scope")
    future = training+not_admitted
    inventory = load(output/"descriptor_inventory.json")
    cache_map = {r["sample_id"]: r for r in inventory["files"]}
    soap, scores = fixed_threshold_soap(records(pool, cache_map), records(future, cache_map),
                                        load(ROOT/config["inputs"]["prior_soap"]["path"]))
    score_map = {r["sample_id"]: r for r in scores}
    future_pool = [{**r, **score_map[r["sample_id"]]} for r in pool]
    chemical, missing = missing_environment_groups(future_pool, future, selected)
    breakdown = {}
    for comp in sorted(chemical):
        subset = [r for r in pool if r["composition"] == comp]
        target = {r["joint_signature"] for r in subset}
        original = {r["joint_signature"] for r in subset if r["sample_id"] in selected}
        current = {r["joint_signature"] for r in training if r["composition"] == comp}
        groups = [r for r in missing if r["composition"] == comp]
        breakdown[comp] = {"old_missing_joint_types": len(target-original),
                           "old_missing_types_filled_by_current366": len((target-original) & current),
                           "current_missing_joint_types": len(target-current),
                           "fillable_if_original_selected_labels_pass_review": len((target-current) & original),
                           "residual_joint_types_if_selected_labels_pass": len(target-(current | original)),
                           "residual_groups_with_robust_example": sum(r["robust_missing_frames_all_scales"] > 0 for r in groups),
                           "residual_SOAP_gap_frames": soap[comp]["above_internal_threshold"]}
    residual_ranked = sorted(missing, key=lambda r: (not r["representative_exceeds_SOAP_threshold"],
                                                    not bool(r["robust_missing_frames_all_scales"]),
                                                    -r["pool_families"], -r["pool_frames"], r["representative_id"]))
    examples = []
    for comp in sorted(breakdown):
        examples += [r for r in residual_ranked if r["composition"] == comp][:2]
    result = {"status": "CONDITIONAL_GAP_REVIEW_COMPLETE", "original_selected_train_not_in_package": len(not_admitted),
              "not_admitted_by_composition": dict(Counter(r["composition"] for r in not_admitted)),
              "conditional_reference_frames": len(future),
              "assumption": "All121 original selected training inputs eventually pass source/SCF/magnetic/isolation review; NOT observed completion or admission",
              "breakdown": breakdown, "conditional_SOAP": soap,
              "conditional_SOAP_gap_frames": [r for r in scores if r["exceeds_internal_threshold"]],
              "residual_diagnostic_groups": missing, "priority_geometry_examples": examples,
              "recommendation": "NO_NEW_RANDOM_DFT_NOW; review existing selected labels first; prioritize missing C3 low-force and independent C2H3 low-force source if later authorized",
              "new_DFT_budget_or_submission": False, "source_files": source_file_manifest([Path(__file__), CONFIG,
                  ROOT/"scripts/adsorption/reico_joint_coverage.py", output/"summary.json", output/"pool_environments.json",
                  output/"training_environments.json", output/"descriptor_inventory.json"])}
    save_once(output/"gap_priorities.json", result)
    print({k:v for k,v in result.items() if k not in ("source_files", "residual_diagnostic_groups", "priority_geometry_examples", "conditional_SOAP")})


if __name__ == "__main__":
    prioritize()
