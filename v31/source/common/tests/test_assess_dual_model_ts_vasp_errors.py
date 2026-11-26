from __future__ import annotations

import pytest

from scripts.assess_dual_model_ts_vasp_errors import _passes, model_metrics


def test_model_metrics_separate_force_and_relative_energy_errors() -> None:
    predictions = [
        {
            "sample_id": "a",
            "primary_energy_eV": 0.0,
            "primary_forces_eV_per_A": [[0, 0, 0], [0.2, 0, 0]],
        },
        {
            "sample_id": "b",
            "primary_energy_eV": 0.8,
            "primary_forces_eV_per_A": [[0, 0, 0], [0.1, 0, 0]],
        },
    ]
    labels = [
        {"sample_id": "a", "vasp_energy_eV": 0.0, "vasp_forces_eV_per_A": [[0, 0, 0], [0, 0, 0]]},
        {"sample_id": "b", "vasp_energy_eV": 1.0, "vasp_forces_eV_per_A": [[0, 0, 0], [0, 0, 0]]},
    ]
    metrics = model_metrics(predictions, labels, model_prefix="primary", fixed_indices=[0])
    assert metrics["component_mae_eV_per_A"] == pytest.approx(0.05)
    assert metrics["vector_max_eV_per_A"] == pytest.approx(0.2)
    assert metrics["relative_energy_rmse_eV"] > 0.1
    passed, failures = _passes(
        metrics,
        {
            "force_component_mae_eV_per_A_max": 0.1,
            "force_vector_rmse_eV_per_A_max": 0.2,
            "force_vector_max_eV_per_A_max": 0.6,
            "relative_energy_rmse_eV_max": 0.1,
        },
    )
    assert not passed
    assert failures == ["relative_energy_rmse"]
