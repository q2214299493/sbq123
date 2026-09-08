from __future__ import annotations

from scripts.neb_agent.path_quality_control import evaluate_quality


THRESHOLDS = {
    "persistence": {
        "monitoring_cycles_min": 5,
        "underresolved_independent_family_count_min": 2,
    },
    "geometry": {
        "image_jump_warning_A": 1.0,
        "abnormal_gap_ratio_to_median_min": 2.0,
        "gap_non_decrease_fraction": 0.98,
        "reactant_basin_span_max_A": 0.05,
    },
    "electronic": {"consecutive_nelm_exhaustion_hard_min": 3},
    "energy": {"sharp_corner_threshold_eV": 0.20},
    "readiness": {
        "pre_ci_projected_force_eV_per_A_max": 0.10,
        "recent_coordinate_drift_A_max": 0.05,
    },
}


def evidence() -> dict:
    return {
        "image_names": ["00", "01", "02", "03", "04", "05", "06"],
        "important_interval_A": [1.5, 2.1],
        "coordinate_history_A": [
            [1.176, 1.181, 1.218, 1.299, value, 2.768, 3.237]
            for value in [2.270, 2.281, 2.294, 2.305, 2.317]
        ],
        "adjacent_pair_metrics": [
            {"max_displacement_A": 0.84, "rms_displacement_A": 0.1, "largest_moves": []},
            {"max_displacement_A": 0.92, "rms_displacement_A": 0.1, "largest_moves": []},
            {"max_displacement_A": 0.88, "rms_displacement_A": 0.1, "largest_moves": []},
            {"max_displacement_A": 0.93, "rms_displacement_A": 0.1, "largest_moves": []},
            {"max_displacement_A": 0.87, "rms_displacement_A": 0.1, "largest_moves": []},
            {"max_displacement_A": 1.02, "rms_displacement_A": 0.1, "largest_moves": []},
        ],
        "scf_iterations": {"02": [200, 200, 200, 200, 200]},
        "configured_nelm": 200,
        "projected_force_history_eV_per_A": {
            "04": [0.270, 0.263, 0.257, 0.247, 0.241]
        },
        "highest_image_history": ["04"] * 5,
        "image_ordering_valid": True,
        "mixed_elementary_steps": False,
        "invalid_endpoints": False,
    }


def test_underresolved_path_stops_before_ci_or_dimer() -> None:
    report = evaluate_quality(evidence(), THRESHOLDS)
    assert report["PATH_QUALITY_STATUS"] == "UNDERRESOLVED_REACTION_COORDINATE"
    assert "DECISION" not in report and "NEXT_ACTION" not in report
    assert report["NEXT_REQUIRED_EVIDENCE_CHECK"] == "REVIEW_DENSIFIED_FULL_IS_FS_PATH_REQUIREMENT"
    assert report["execution_authority"].endswith("decide_execution")
    assert "B_large_reaction_coordinate_gap" in report["REASON_CODES"]
    assert "C_gap_persistent_or_increasing" in report["REASON_CODES"]
    assert "ELECTRONIC_CONVERGENCE_FAILURE" in report["REASON_CODES"]


def test_valid_smooth_path_can_continue_no_climb() -> None:
    sample = evidence()
    sample["coordinate_history_A"] = [
        [1.18, 1.38, 1.58, 1.78, 1.98, 2.18, 2.38] for _ in range(5)
    ]
    sample["adjacent_pair_metrics"] = [
        {"max_displacement_A": 0.4, "rms_displacement_A": 0.1, "largest_moves": []}
        for _ in range(6)
    ]
    sample["scf_iterations"] = {"02": [20, 18, 19, 17, 16]}
    sample["projected_force_history_eV_per_A"] = {}
    report = evaluate_quality(sample, THRESHOLDS)
    assert report["PATH_QUALITY_STATUS"] == "ORDINARY_NEB_PROGRESS_EVIDENCE"
    assert report["NEXT_REQUIRED_EVIDENCE_CHECK"] == "REVIEW_NEXT_MONITORING_CHECKPOINT"


def test_ci_readiness_respects_optional_stable_highest_policy() -> None:
    sample = evidence()
    sample["coordinate_history_A"] = [
        [1.18, 1.38, 1.58, 1.78, 1.98, 2.18, 2.38] for _ in range(5)
    ]
    sample["adjacent_pair_metrics"] = [
        {"max_displacement_A": 0.4, "rms_displacement_A": 0.1, "largest_moves": []}
        for _ in range(6)
    ]
    sample["scf_iterations"] = {"02": [20, 18, 19, 17, 16]}
    sample["projected_force_history_eV_per_A"] = {
        f"{index:02d}": [0.08] for index in range(1, 6)
    }
    sample["highest_image_history"] = ["02", "03", "02", "03", "02"]
    thresholds = {
        **THRESHOLDS,
        "readiness": {
            **THRESHOLDS["readiness"],
            "require_stable_highest_image": False,
        },
    }
    report = evaluate_quality(sample, thresholds)
    assert report["PATH_QUALITY_STATUS"] == "CI_NEB_READINESS_EVIDENCE"


def test_one_gap_pattern_is_not_counted_as_multiple_independent_reasons() -> None:
    sample = evidence()
    sample["image_names"] = ["00", "01", "02", "03"]
    sample["highest_image_history"] = ["02"] * 5
    sample["coordinate_history_A"] = [
        [1.2, 1.4, right, 2.5]
        for right in [2.50, 2.35, 2.25, 2.18, 2.12]
    ]
    sample["adjacent_pair_metrics"] = [
        {"max_displacement_A": 0.3, "rms_displacement_A": 0.1, "largest_moves": []}
        for _ in range(3)
    ]
    sample["scf_iterations"] = {"02": [200, 20, 18, 17, 16]}
    sample["projected_force_history_eV_per_A"] = {}
    report = evaluate_quality(sample, THRESHOLDS)
    assert report["PATH_QUALITY_STATUS"] == "ORDINARY_NEB_PROGRESS_EVIDENCE"
    assert report["EVIDENCE"]["independent_evidence_families"] == ["discontinuity"]
    assert "ELECTRONIC_CONVERGENCE_FAILURE" not in report["REASON_CODES"]


def test_unverified_monitor_flags_cannot_create_hard_stop() -> None:
    sample = evidence()
    sample["coordinate_history_A"] = [
        [1.18, 1.38, 1.58, 1.78, 1.98, 2.18, 2.38] for _ in range(5)
    ]
    sample["adjacent_pair_metrics"] = [
        {"max_displacement_A": 0.4, "rms_displacement_A": 0.1, "largest_moves": []}
        for _ in range(6)
    ]
    sample["scf_iterations"] = {"02": [20, 18, 19, 17, 16]}
    sample["projected_force_history_eV_per_A"] = {}
    sample["mixed_elementary_steps"] = True
    sample["invalid_endpoints"] = True
    report = evaluate_quality(sample, THRESHOLDS)
    assert report["PATH_QUALITY_STATUS"] == "ORDINARY_NEB_PROGRESS_EVIDENCE"
    assert "UNVERIFIED_INVALID_ENDPOINT_FLAG" in report["REASON_CODES"]
    assert "UNVERIFIED_MIXED_ELEMENTARY_STEPS_FLAG" in report["REASON_CODES"]
