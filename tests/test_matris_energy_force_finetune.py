from __future__ import annotations

import pytest

from scripts.matris_energy_force_finetune import (
    RETENTION_METRIC_KEYS,
    _checkpoint_selection_policy,
    energy_anchor_ids,
    retention_gate_verdict,
    retention_non_regression,
    update_checkpoint_selection,
)


def test_energy_anchor_ids_are_deterministic_and_ignore_force_only_replay() -> None:
    samples = [
        {"sample_id": "z", "energy_group_id": "reaction"},
        {"sample_id": "a", "energy_group_id": "reaction"},
        {"sample_id": "adsorption", "energy_group_id": None},
    ]

    assert energy_anchor_ids(samples) == {"reaction": "a"}


def test_retention_non_regression_rejects_vector_max_rebound() -> None:
    baseline = {
        "component_rmse_eV_per_A": 0.05,
        "vector_rmse_eV_per_A": 0.08,
        "vector_p95_eV_per_A": 0.14,
        "vector_max_eV_per_A": 0.25,
    }
    candidate = dict(baseline)
    candidate["component_rmse_eV_per_A"] = 0.04
    candidate["vector_rmse_eV_per_A"] = 0.07
    candidate["vector_p95_eV_per_A"] = 0.12
    candidate["vector_max_eV_per_A"] = 0.26

    passed, checks = retention_non_regression(baseline, candidate)

    assert passed is False
    assert checks["vector_max_eV_per_A"] is False
    assert all(checks[key] for key in RETENTION_METRIC_KEYS[:-1])


def test_retention_non_regression_accepts_all_metric_improvement() -> None:
    baseline = {key: 0.2 for key in RETENTION_METRIC_KEYS}
    candidate = {key: 0.19 for key in RETENTION_METRIC_KEYS}

    assert retention_non_regression(baseline, candidate)[0] is True


def test_tiered_retention_gate_classifies_small_vector_max_rebound_as_warning() -> None:
    baseline = {
        "component_rmse_eV_per_A": 0.046773176204923,
        "vector_rmse_eV_per_A": 0.0810135176182983,
        "vector_p95_eV_per_A": 0.145147553602879,
        "vector_max_eV_per_A": 0.25591623542318,
    }
    candidate = {
        "component_rmse_eV_per_A": 0.0412391996776766,
        "vector_rmse_eV_per_A": 0.071428389105214,
        "vector_p95_eV_per_A": 0.129897613540234,
        "vector_max_eV_per_A": 0.256582592513674,
    }
    policy = {
        "kind": "adsorption_retention_tiered_early_stopping",
        "hard_metric_absolute_tolerance_eV_per_A": 0.0,
        "vector_max_pass_absolute_tolerance_eV_per_A": 0.0,
        "vector_max_soft_warning_maximum_absolute_regression_eV_per_A": 0.005,
        "vector_max_soft_warning_maximum_relative_regression_fraction": 0.02,
    }

    verdict = retention_gate_verdict(baseline, candidate, policy)

    assert verdict["status"] == "soft_warning"
    assert verdict["candidate_eligible"] is True


def test_tiered_retention_gate_rejects_warning_band_excess() -> None:
    baseline = {key: 0.2 for key in RETENTION_METRIC_KEYS}
    candidate = {key: 0.19 for key in RETENTION_METRIC_KEYS}
    candidate["vector_max_eV_per_A"] = 0.206
    policy = {
        "kind": "adsorption_retention_tiered_early_stopping",
        "hard_metric_absolute_tolerance_eV_per_A": 0.0,
        "vector_max_pass_absolute_tolerance_eV_per_A": 0.0,
        "vector_max_soft_warning_maximum_absolute_regression_eV_per_A": 0.005,
        "vector_max_soft_warning_maximum_relative_regression_fraction": 0.02,
    }

    assert retention_gate_verdict(baseline, candidate, policy)["status"] == "fail"


def test_retention_policy_keeps_frozen_ts_heldout_final_only() -> None:
    policy = _checkpoint_selection_policy(
        {
            "checkpoint_selection_policy": {
                "kind": "adsorption_retention_strict_early_stopping",
                "selection_dataset_role": "adsorption_retention_validation",
                "required_non_regression_metrics": list(RETENTION_METRIC_KEYS),
                "absolute_tolerance_eV_per_A": 0.0,
                "patience_epochs": 3,
                "training_objective_min_delta": 1.0e-8,
                "frozen_ts_heldout_usage": "final_evaluation_only",
            }
        }
    )

    assert policy["frozen_ts_heldout_usage"] == "final_evaluation_only"
    assert policy["epoch_zero_is_candidate"] is False


def test_tiered_retention_policy_is_normalized() -> None:
    policy = _checkpoint_selection_policy(
        {
            "checkpoint_selection_policy": {
                "kind": "adsorption_retention_tiered_early_stopping",
                "selection_dataset_role": "adsorption_retention_validation",
                "hard_non_regression_metrics": list(RETENTION_METRIC_KEYS[:-1]),
                "hard_metric_absolute_tolerance_eV_per_A": 0.0,
                "vector_max_pass_absolute_tolerance_eV_per_A": 0.0,
                "vector_max_soft_warning_maximum_absolute_regression_eV_per_A": 0.005,
                "vector_max_soft_warning_maximum_relative_regression_fraction": 0.02,
                "patience_epochs": 3,
                "training_objective_min_delta": 1.0e-8,
                "frozen_ts_heldout_usage": "final_evaluation_only",
            }
        }
    )

    assert policy["kind"] == "adsorption_retention_tiered_early_stopping"
    assert policy["vector_max_soft_warning_maximum_absolute_regression_eV_per_A"] == 0.005


def test_retention_policy_rejects_heldout_epoch_selection() -> None:
    with pytest.raises(ValueError, match="final-evaluation only"):
        _checkpoint_selection_policy(
            {
                "checkpoint_selection_policy": {
                    "kind": "adsorption_retention_strict_early_stopping",
                    "selection_dataset_role": "adsorption_retention_validation",
                    "required_non_regression_metrics": list(RETENTION_METRIC_KEYS),
                    "absolute_tolerance_eV_per_A": 0.0,
                    "patience_epochs": 3,
                    "training_objective_min_delta": 1.0e-8,
                    "frozen_ts_heldout_usage": "epoch_selection",
                }
            }
        )


def test_checkpoint_selection_keeps_eligible_earlier_epoch_on_rebound(tmp_path) -> None:
    policy = {
        "kind": "adsorption_retention_strict_early_stopping",
        "training_objective_min_delta": 1.0e-8,
        "patience_epochs": 3,
    }
    first = tmp_path / "epoch_001.pth.tar"
    state = update_checkpoint_selection(
        policy=policy,
        epoch=1,
        checkpoint_path=first,
        training_objective=0.004,
        retention_pass=True,
        selected_epoch=None,
        selected_checkpoint_path=None,
        selected_training_objective=float("inf"),
        epochs_without_eligible_improvement=0,
    )
    selected_epoch, selected_path, objective, wait, stopped = state
    state = update_checkpoint_selection(
        policy=policy,
        epoch=2,
        checkpoint_path=tmp_path / "epoch_002.pth.tar",
        training_objective=0.003,
        retention_pass=False,
        selected_epoch=selected_epoch,
        selected_checkpoint_path=selected_path,
        selected_training_objective=objective,
        epochs_without_eligible_improvement=wait,
    )

    assert state == (1, first, 0.004, 1, False)
    assert stopped is False
