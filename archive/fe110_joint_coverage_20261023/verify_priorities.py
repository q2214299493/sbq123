"""Direct set-count verification of the conditional gap priorities."""
from __future__ import annotations

from pathlib import Path

from scripts.artifact_io import source_file_manifest, source_file_manifest_valid
from .run import CONFIG, ROOT, load, save_once


def verify():
    config = load(CONFIG)
    output = ROOT/config["output"]
    priorities = load(output/"gap_priorities.json")
    assert source_file_manifest_valid(priorities)
    training = load(output/"training_environments.json")["frames"]
    pool = load(output/"pool_environments.json")["frames"]
    selected = {r["sample_id"] for r in load(ROOT/config["inputs"]["selection"]["path"])["selected"] if r["partition"] == "train"}
    current = {r["sample_id"] for r in training}
    future = training+[r for r in pool if r["sample_id"] in selected-current]
    assert len(future) == 487
    missing_total = robust_total = 0
    for comp, counts in priorities["breakdown"].items():
        queries = [r for r in pool if r["composition"] == comp]
        refs = [r for r in future if r["composition"] == comp]
        by_scale = {s: {r["joint_by_scale"][s] for r in refs} for s in ("1.2", "1.25", "1.3")}
        main_missing = {r["joint_signature"] for r in queries}-{r["joint_signature"] for r in refs}
        robust = {r["joint_signature"] for r in queries if r["joint_signature"] in main_missing
                  and all(r["joint_by_scale"][s] not in by_scale[s] for s in by_scale)}
        assert len(main_missing) == counts["residual_joint_types_if_selected_labels_pass"]
        assert len(robust) == counts["residual_groups_with_robust_example"]
        missing_total += len(main_missing)
        robust_total += len(robust)
    assert missing_total == len(priorities["residual_diagnostic_groups"])
    assert all(r["DFT_force_of_missing_frames"] == "UNKNOWN_NOT_INFERRED_FROM_NEIGHBORS"
               and not r["original_selected_labels_not_in_package"] for r in priorities["residual_diagnostic_groups"])
    report = {"status": "PASS", "conditional_reference_frames": len(future),
              "remaining_joint_strata": missing_total, "strata_with_all_cutoff_missing_example": robust_total,
              "selected_labels_not_assumed_complete_or_accepted": True,
              "source_files": source_file_manifest([Path(__file__), output/"gap_priorities.json"])}
    save_once(output/"priority_verification.json", report)
    print({k:v for k,v in report.items() if k != "source_files"})


if __name__ == "__main__":
    verify()
