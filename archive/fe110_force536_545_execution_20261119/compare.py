"""Read the two returned native candidates and record the shared-development comparison."""

from __future__ import annotations

from scripts.artifact_io import load_json_object as load, sha256_file as sha, write_json_exclusive as save
from .control import BATCH, MODEL, MODEL_SHA, OUT, STAGE, guard_hashes


def main():
    arms = {arm: load(OUT / f"{arm}_report.json") for arm in ("control536", "increment545")}
    control, increment = arms["control536"], arms["increment545"]
    dev = sha(STAGE / "development.db")
    assert control["dev_input_sha256"] == increment["dev_input_sha256"] == dev
    assert sha(MODEL) == MODEL_SHA and guard_hashes() == load(BATCH / "final_submission_list.json")["frozen_hashes"]
    names = (
        "forces_role_vector_mae",
        "forces_adsorbate_C_vector_mae",
        "forces_adsorbate_O_vector_mae",
        "forces_adsorbate_H_vector_mae",
        "forces_near_Fe_vector_mae",
        "forces_other_Fe_vector_mae",
    )
    metrics = {}
    for name in names:
        first, second = (arm["development_metrics"][name] for arm in arms.values())
        assert first["numel"] == second["numel"] and first["metric"] > 0
        absolute = second["metric"] - first["metric"]
        metrics[name] = {
            "control536": first["metric"],
            "increment545": second["metric"],
            "increment_minus_control_eV_A": absolute,
            "percent_relative_difference": 100 * absolute / first["metric"],
            "metric_sample_count": first["numel"],
        }
    assert metrics[names[0]]["metric_sample_count"] == 78
    assert all(len(ids) == 9 for ids in increment["new_samples_with_update_by_epoch"].values())
    output = {
        "status": "BOTH_ARMS_COMPLETE_SAME_78_DEVELOPMENT_FRAMES",
        "initialization_sha256": MODEL_SHA,
        "shared_development_db_sha256": dev,
        "development_frames": 78,
        "both_best_selected_by": names[0],
        "arms": arms,
        "metrics": metrics,
        "nominal_step_difference": 18,
        "producer_wall_seconds_total": sum(a["producer_wall_seconds"] for a in arms.values()),
        "protected_packages_unchanged": True,
        "heldout_opened_for_evaluation": False,
        "new_dft": False,
        "promoted": False,
    }
    save(OUT / "comparison_summary.json", output)
    print(metrics[names[0]])


if __name__ == "__main__":
    main()
