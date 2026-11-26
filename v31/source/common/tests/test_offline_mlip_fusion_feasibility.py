from __future__ import annotations

import math

import numpy as np
from ase import Atoms

from scripts.offline_mlip_fusion_feasibility import (
    bootstrap_relative_improvement,
    exact_sign_flip_pvalue,
    pair_rbf_energy_force_features,
    promotion_assessment,
)


def test_pair_rbf_force_is_negative_energy_gradient() -> None:
    atoms = Atoms("CH", positions=[[0.0, 0.0, 0.0], [1.25, 0.0, 0.0]], pbc=False)
    pair_types = (("C", "H"),)
    coefficients = np.asarray([0.7, -0.2, 0.4, 0.1, -0.3, 0.2])
    energy_features, force_features = pair_rbf_energy_force_features(
        atoms,
        (),
        pair_types,
        cutoff_A=4.0,
        radial_basis_count=6,
        center_min_A=0.8,
    )
    analytic_force = float(np.dot(force_features[1, 0, :], coefficients))
    step = 1.0e-6
    displaced_plus = atoms.copy()
    displaced_minus = atoms.copy()
    displaced_plus.positions[1, 0] += step
    displaced_minus.positions[1, 0] -= step
    plus_features, _ = pair_rbf_energy_force_features(
        displaced_plus,
        (),
        pair_types,
        cutoff_A=4.0,
        radial_basis_count=6,
        center_min_A=0.8,
    )
    minus_features, _ = pair_rbf_energy_force_features(
        displaced_minus,
        (),
        pair_types,
        cutoff_A=4.0,
        radial_basis_count=6,
        center_min_A=0.8,
    )
    finite_difference_force = -float(
        (np.dot(plus_features, coefficients) - np.dot(minus_features, coefficients))
        / (2.0 * step)
    )
    assert math.isclose(analytic_force, finite_difference_force, rel_tol=1.0e-6, abs_tol=1.0e-7)
    assert math.isclose(
        float(np.dot(energy_features, coefficients)),
        0.24791878749339624,
        rel_tol=1.0e-12,
    )


def test_exact_sign_flip_has_expected_five_pair_resolution() -> None:
    assert exact_sign_flip_pvalue([1.0, 1.0, 1.0, 1.0, 1.0]) == 1.0 / 32.0
    assert exact_sign_flip_pvalue([-1.0, -1.0, -1.0]) == 1.0


def test_bootstrap_relative_improvement_is_deterministic() -> None:
    first = bootstrap_relative_improvement(
        [2.0, 4.0, 6.0], [1.0, 2.0, 3.0], resamples=1000, seed=17
    )
    second = bootstrap_relative_improvement(
        [2.0, 4.0, 6.0], [1.0, 2.0, 3.0], resamples=1000, seed=17
    )
    assert first == second
    assert first["estimate"] == 0.5
    assert first["ci95_low"] == 0.5
    assert first["ci95_high"] == 0.5


def test_promotion_gate_rejects_nonuniform_improvement() -> None:
    rows = []
    reactions = [f"r{index}" for index in range(5)]
    for reaction_index, reaction in enumerate(reactions):
        matris_force = 1.0
        meta_force = 0.8 if reaction_index < 4 else 1.1
        matris_energy = 1.0
        meta_energy = 0.8
        for model in ("matris", "aqcat25", "linear_fusion", "conservative_meta"):
            rows.append(
                {
                    "reaction_id": reaction,
                    "model": model,
                    "force_vector_rmse_eV_per_A": (
                        meta_force if model == "conservative_meta" else matris_force
                    ),
                    "force_vector_max_eV_per_A": (
                        meta_force if model == "conservative_meta" else matris_force
                    ),
                    "relative_energy_rmse_eV": (
                        meta_energy if model == "conservative_meta" else matris_energy
                    ),
                }
            )
    config = {
        "promotion_gate": {
            "minimum_macro_relative_improvement": 0.10,
            "one_sided_exact_sign_flip_alpha": 0.05,
            "require_force_win_on_every_reaction": True,
            "require_energy_win_on_every_eligible_reaction": True,
            "maximum_allowed_force_vector_max_regression_fraction": 0.10,
            "bootstrap_resamples": 1000,
            "random_seed": 5,
            "pass_action": "pass",
            "fail_action": "fail",
        }
    }
    assessment = promotion_assessment(rows, config)
    assert assessment["promotion_gate_passed"] is False
    assert assessment["decision"] == "fail"
    assert assessment["checks"]["force_every_reaction_win"] is False
