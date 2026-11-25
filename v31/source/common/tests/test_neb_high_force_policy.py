from __future__ import annotations

from scripts.neb_agent.analyze_neb_outputs import classify_high_force_observations


THRESHOLDS = {
    "high_force_warning_threshold_eVA": 1.5,
    "min_ionic_steps_for_force_warning": 5,
    "persistent_high_force_failure_min_ionic_steps": 10,
}


def _row(*, steps: int, force: float, trend: str) -> dict:
    return {
        "image": "01",
        "ionic_steps": steps,
        "final_neb_force_eVA": force,
        "neb_force_trend": trend,
    }


def test_first_step_high_force_does_not_trigger_warning() -> None:
    observations = classify_high_force_observations(
        [_row(steps=1, force=4.6, trend="insufficient_data")],
        THRESHOLDS,
    )

    assert observations == [
        {
            "image": "01",
            "ionic_steps": 1,
            "force_eVA": 4.6,
            "trend": "insufficient_data",
            "warning_eligible": False,
            "warning_triggered": False,
            "failure_eligible": False,
            "failure_triggered": False,
            "classification": "initial_high_force_allowed",
        }
    ]


def test_high_force_after_startup_window_triggers_warning_only() -> None:
    observations = classify_high_force_observations(
        [_row(steps=5, force=1.6, trend="plateau")],
        THRESHOLDS,
    )

    assert observations[0]["warning_eligible"] is True
    assert observations[0]["warning_triggered"] is True
    assert observations[0]["failure_eligible"] is False
    assert observations[0]["failure_triggered"] is False
    assert observations[0]["classification"] == "high_force_warning"


def test_persistent_high_force_at_ten_steps_is_failure() -> None:
    observations = classify_high_force_observations(
        [_row(steps=10, force=1.6, trend="plateau")],
        THRESHOLDS,
    )

    assert observations[0]["warning_eligible"] is True
    assert observations[0]["failure_eligible"] is True
    assert observations[0]["failure_triggered"] is True
    assert observations[0]["classification"] == "persistent_high_force_failure"


def test_decreasing_high_force_after_ten_steps_is_not_failure() -> None:
    observations = classify_high_force_observations(
        [_row(steps=10, force=1.6, trend="decreasing")],
        THRESHOLDS,
    )

    assert observations[0]["warning_triggered"] is False
    assert observations[0]["failure_triggered"] is False
    assert observations[0]["classification"] == "decreasing_high_force_no_warning"
