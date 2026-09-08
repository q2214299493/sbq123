from __future__ import annotations

from scripts.aqcat25_calibration import calibrate, parse_final_outcar


def test_parse_final_vasp_force_block(tmp_path) -> None:
    outcar = tmp_path / "OUTCAR"
    outcar.write_text(
        """free  energy   TOTEN  =       -10.5000 eV
 TOTAL-FORCE (eV/Angst)
 -------------------------------------------------------------------
 -0.1 0 0  0.10 0.20 0.30
 1 0 0 -0.10 0.00 0.20
 -------------------------------------------------------------------
 reached required accuracy - stopping structural energy minimisation
 General timing and accounting informations for this job:
""",
        encoding="utf-8",
    )
    parsed = parse_final_outcar(outcar)
    assert parsed["forces_eV_per_A"] == [[0.1, 0.2, 0.3], [-0.1, 0.0, 0.2]]
    assert parsed["final_toten_eV"] == -10.5
    assert parsed["ionic_converged"] is True
    assert parsed["normal_completion"] is True


def test_calibration_gate_reports_failed_checkpoint_without_hiding_metrics() -> None:
    labels = {
        "calibration_id": "test",
        "samples": [
            {
                "sample_id": "s1",
                "family": "family",
                "structure_sha256": "0" * 64,
                "symbols": ["Fe", "H"],
                "fixed_atom_indices_1based": [1],
                "forces_eV_per_A": [[0, 0, 0], [0, 0, 0]],
            }
        ],
    }
    predictions = {
        "checkpoint_sha256": "1" * 64,
        "samples": [
            {
                "sample_id": "s1",
                "structure_sha256": "0" * 64,
                "predicted_energy_eV": -1.0,
                "forces_eV_per_A": [[0, 0, 0], [1, 0, 0]],
            }
        ],
    }
    gate = {
        "reference_scope": {
            "required_fe_count": 1,
            "allowed_elements": ["Fe", "H"],
            "adsorbate_atom_count_range": [1, 1],
            "required_families": ["family"],
            "minimum_total_samples": 1,
        },
        "force_acceptance": {
            "component_mae_eV_per_A_max": 0.1,
            "vector_rmse_eV_per_A_max": 0.2,
            "vector_p95_eV_per_A_max": 0.4,
            "vector_max_eV_per_A_max": 0.6,
        },
    }
    result = calibrate(labels, predictions, gate)
    assert result["status"] == "calibration_failed"
    assert result["metrics"]["vector_max_eV_per_A"] == 1.0
    assert result["threshold_checks"]["vector_max"] is False
