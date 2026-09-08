from __future__ import annotations

from pathlib import Path

import pytest

from scripts.adsmind_lite.fts_prescreen import (
    load_fts_rules,
    plan_calibrated_fts_species,
    plan_feature_based_fts_species,
    rank_carbon_sites,
)


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "configs" / "adsmind_lite" / "iron_fts_prescreen.yaml"


def test_coordination_demand_changes_preferred_fe110_coordination() -> None:
    rules = load_fts_rules(str(RULES_PATH))

    assert rank_carbon_sites(3, rules)[:2] == ["long_bridge", "short_bridge"]
    assert rank_carbon_sites(1, rules)[0] == "top"
    assert rank_carbon_sites(0, rules)[-1] == "gas_like"


def test_user_calibrated_oxygenates_are_not_one_generic_co_template() -> None:
    rules = load_fts_rules(str(RULES_PATH))
    expected_first = {
        "CH2O": "CH2O_eta2_CO_side_on",
        "COH": "COH_C_long_bridge",
        "CHOH": "CHOH_C_long_bridge_orientation_a",
        "CH2OH": "CH2OH_C_top",
    }

    for species, motif in expected_first.items():
        plan = plan_calibrated_fts_species(species, rules)
        assert plan is not None
        assert plan["candidates"][0]["motif_id"] == motif


def test_reviewed_profiles_have_an_exact_non_budget_dependent_count() -> None:
    rules = load_fts_rules(str(RULES_PATH))
    plan = plan_calibrated_fts_species("CH2O", rules)

    assert plan is not None
    assert plan["candidate_count"] == 2
    assert {candidate["motif_id"] for candidate in plan["candidates"]} == {
        "CH2O_eta2_CO_side_on",
        "CH2O_O_top_tilted",
    }


def test_hydroxylated_radicals_do_not_default_to_o_only() -> None:
    rules = load_fts_rules(str(RULES_PATH))
    for species in ("COH", "CHOH", "CH2OH"):
        plan = plan_calibrated_fts_species(species, rules)
        assert plan is not None
        assert all(candidate["binding_atoms"] != ["O"] for candidate in plan["candidates"])


def test_unseen_hydroxylated_carbon_uses_coordination_demand_not_formula_only() -> None:
    rules = load_fts_rules(str(RULES_PATH))
    high_demand = plan_feature_based_fts_species(
        "unseen_COH_like",
        {
            "carbon_centers": [{"label": "C1", "coordination_demand": 3, "substituted": True}],
            "oxygen_centers": [{"label": "O1", "role": "hydroxyl"}],
            "eta2_CO_geometry_allowed": True,
        },
        rules,
    )
    low_demand = plan_feature_based_fts_species(
        "unseen_CH2OH_like",
        {
            "carbon_centers": [{"label": "C1", "coordination_demand": 1, "substituted": True}],
            "oxygen_centers": [{"label": "O1", "role": "hydroxyl"}],
            "eta2_CO_geometry_allowed": True,
        },
        rules,
    )

    assert [item["site_pattern"] for item in high_demand["candidates"][:2]] == ["long_bridge", "short_bridge"]
    assert [item["site_pattern"] for item in low_demand["candidates"][:2]] == ["top", "long_bridge"]


def test_unseen_closed_shell_carbonyl_gets_eta2_then_tilted_o_top() -> None:
    rules = load_fts_rules(str(RULES_PATH))
    plan = plan_feature_based_fts_species(
        "unseen_aldehyde",
        {
            "carbon_centers": [{"label": "C1", "coordination_demand": 0, "substituted": True}],
            "oxygen_centers": [{"label": "O1", "role": "carbonyl"}],
            "carbonyl_subtype": "closed_shell_aldehyde",
            "eta2_CO_geometry_allowed": True,
        },
        rules,
    )

    assert [item["motif_id"] for item in plan["candidates"]] == [
        "unseen_aldehyde_eta2_CO_side_on",
        "unseen_aldehyde_O_top_tilted",
    ]


def test_unseen_alkene_gets_two_di_sigma_directions_then_pi_top() -> None:
    rules = load_fts_rules(str(RULES_PATH))
    plan = plan_feature_based_fts_species(
        "unseen_alkene",
        {
            "carbon_centers": [
                {"label": "C1", "coordination_demand": 0, "substituted": True},
                {"label": "C2", "coordination_demand": 0, "substituted": True},
            ],
            "cc_mode": "alkene",
            "cc_atoms": ["C1", "C2"],
            "flexible_c2plus": True,
        },
        rules,
    )

    assert [item["motif_id"] for item in plan["candidates"]] == [
        "unseen_alkene_di_sigma_long",
        "unseen_alkene_di_sigma_short",
        "unseen_alkene_pi_top",
    ]


def test_unseen_vinyl_uses_radical_carbon_then_cc_multicenter() -> None:
    rules = load_fts_rules(str(RULES_PATH))
    plan = plan_feature_based_fts_species(
        "unseen_vinyl",
        {
            "carbon_centers": [
                {"label": "C_rad", "coordination_demand": 1, "substituted": True},
                {"label": "C_CH2", "coordination_demand": 0, "substituted": True},
            ],
            "cc_mode": "vinyl_radical",
            "cc_atoms": ["C_rad", "C_CH2"],
            "radical_carbon": "C_rad",
            "flexible_c2plus": True,
        },
        rules,
    )

    assert [item["motif_id"] for item in plan["candidates"]] == [
        "unseen_vinyl_C_rad_top",
        "unseen_vinyl_eta2_CC_side_on",
        "unseen_vinyl_C_rad_long_bridge",
    ]


def test_unseen_neutral_c2_alcohol_uses_orientation_not_site_sweep() -> None:
    rules = load_fts_rules(str(RULES_PATH))
    plan = plan_feature_based_fts_species(
        "unseen_c2_alcohol",
        {
            "carbon_centers": [
                {"label": "C1", "coordination_demand": 0, "substituted": True},
                {"label": "C2", "coordination_demand": 0, "substituted": True},
            ],
            "oxygen_centers": [{"label": "O1", "role": "water_or_alcohol_donor"}],
            "flexible_c2plus": True,
        },
        rules,
    )

    assert [item["site_pattern"] for item in plan["candidates"]] == ["top_chain_along_row", "top_chain_across_row"]


@pytest.mark.parametrize("surface_name", ["Fe100", "Fe111", "Fe5C2_010", "Fe3O4_001"])
def test_fts_rules_reject_every_non_fe110_surface(surface_name: str) -> None:
    rules = load_fts_rules(str(RULES_PATH))
    with pytest.raises(ValueError, match="fe110_only_rule_not_transferable"):
        plan_calibrated_fts_species("C2H4", rules, surface_name=surface_name)
