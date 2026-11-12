from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.adsmind_lite.prescreen import load_prescreen_rules, plan_batch


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "configs" / "adsmind_lite" / "prescreen_rules.yaml"


def candidate(motif_id: str, site: str = "top", **fields) -> dict:
    return {
        "motif_id": motif_id,
        "configuration_id": motif_id,
        "site_pattern": site,
        "binding_mode": "monodentate",
        "binding_atoms": ["O"],
        "build_ready": True,
        **fields,
    }


def plan(candidates: list[dict], *, decision: str = "READY", **fields) -> dict:
    # Synthetic reviewed inputs exercise planning identity, not motif chemistry.
    return {
        "species": "synthetic_reviewed_species",
        "surface": "Fe110",
        "decision": decision,
        "candidate_count": len(candidates),
        "candidates": candidates,
        **fields,
    }


def review(source: dict, *, surface_name: str = "Fe110") -> dict:
    from scripts.adsmind_lite.prescreen import review_initial_motif_coverage

    return review_initial_motif_coverage(
        source, load_prescreen_rules(str(RULES_PATH)), surface_name=surface_name
    )


def test_orientation_height_and_configuration_variants_are_one_initial_mode() -> None:
    source = plan([
        candidate("top_a", orientation_degrees=0.0, height_angstrom=1.9),
        candidate("top_b", orientation_degrees=90.0, height_angstrom=2.1),
        candidate("top_c", orientation="tilted", relaxed_site="hollow"),
    ])
    original = deepcopy(source)

    reviewed = review(source)

    assert reviewed["decision"] == "NEEDS_REVIEW"
    assert reviewed["evidence_decision"] == "READY"
    assert reviewed["candidate_count"] == 3
    coverage = reviewed["initial_motif_coverage"]
    assert coverage["required_count"] == 3
    assert coverage["distinct_count"] == 1
    assert coverage["shortfall_count"] == 2
    assert coverage["status"] == "NEEDS_REVIEW"
    assert set(coverage["groups"][0]["motif_ids"]) == {"top_a", "top_b", "top_c"}
    assert reviewed["candidates"] == original["candidates"]
    assert source == original


def test_three_initial_modes_do_not_require_three_final_minima() -> None:
    source = plan([
        candidate("start_top", "top", relaxed_site="top"),
        candidate("start_short", "short_bridge", relaxed_site="top"),
        candidate("start_long", "long_bridge", relaxed_site="top"),
    ], evidence={"global_minimum_claim": False})

    reviewed = review(source)

    assert reviewed["decision"] == "READY"
    assert reviewed["initial_motif_coverage"]["status"] == "PASS"
    assert reviewed["initial_motif_coverage"]["distinct_count"] == 3
    assert reviewed["initial_motif_coverage"]["shortfall_count"] == 0
    assert reviewed["final_stable_minima_count"] is None
    assert reviewed["evidence"]["global_minimum_claim"] is False


def test_binding_atoms_can_distinguish_initial_modes() -> None:
    reviewed = review(plan([
        candidate("C_top", binding_atoms=["C"]),
        candidate("O_top", binding_atoms=["O"]),
        candidate("CO_top", binding_mode="bidentate", binding_atoms=["C", "O"]),
    ]))

    assert reviewed["decision"] == "READY"
    assert reviewed["initial_motif_coverage"]["distinct_count"] == 3


def test_explicit_pi_and_di_sigma_binding_modes_remain_distinct() -> None:
    reviewed = review(plan([
        candidate("CC_pi", "top", binding_mode="pi_complex", binding_atoms=["C1", "C2"]),
        candidate("CC_sigma", "top", binding_mode="di_sigma", binding_atoms=["C1", "C2"]),
    ]))

    assert reviewed["initial_motif_coverage"]["distinct_count"] == 2
    assert reviewed["decision"] == "NEEDS_REVIEW"


def test_binding_atom_list_order_is_not_a_new_mode() -> None:
    reviewed = review(plan([
        candidate("CO_a", "h-lb-h", binding_mode="bidentate", binding_atoms=["C", "O"]),
        candidate("CO_b", "h-lb-h", binding_mode="bidentate", binding_atoms=["O", "C"]),
    ]))

    assert reviewed["initial_motif_coverage"]["distinct_count"] == 1
    assert reviewed["decision"] == "NEEDS_REVIEW"


@pytest.mark.parametrize("mode,anchor", [
    ("O_centered", "O"),
    ("C_centered", "C"),
    ("terminal_C_centered", "C_terminal"),
])
def test_equivalent_single_anchor_mode_names_are_one_mode(mode: str, anchor: str) -> None:
    reviewed = review(plan([
        candidate("generic", binding_atoms=[anchor]),
        candidate("named", binding_mode=mode, binding_atoms=[anchor]),
    ]))

    assert reviewed["initial_motif_coverage"]["distinct_count"] == 1
    assert reviewed["decision"] == "NEEDS_REVIEW"


@pytest.mark.parametrize("sites", [
    ("top", "top_Fe"),
    ("short_bridge", "bridge_FeFe_short"),
    ("long_bridge", "bridge_FeFe_long"),
    ("hollow", "hollow_FeFeFe"),
])
def test_generator_site_aliases_do_not_inflate_mode_count(sites: tuple[str, str]) -> None:
    reviewed = review(plan([candidate("a", sites[0]), candidate("b", sites[1])]))

    assert reviewed["initial_motif_coverage"]["distinct_count"] == 1
    assert reviewed["decision"] == "NEEDS_REVIEW"


def test_site_alias_case_does_not_create_independent_initial_modes() -> None:
    reviewed = review(plan([
        candidate(f"top_{index}", site)
        for index, site in enumerate(("top", "TOP", "top_Fe", "TOP_FE"))
    ]))

    assert reviewed["candidate_count"] == 4
    assert reviewed["initial_motif_coverage"]["distinct_count"] == 1
    assert reviewed["decision"] == "NEEDS_REVIEW"


def test_actual_generator_site_class_prevents_claimed_site_coverage() -> None:
    reviewed = review(plan([
        candidate("claimed_top", "top", generator_site_class="top_Fe"),
        candidate("claimed_short", "short_bridge", generator_site_class="top_Fe"),
        candidate("claimed_long", "long_bridge", generator_site_class="top_Fe"),
    ]))

    assert reviewed["decision"] == "NEEDS_REVIEW"
    assert reviewed["initial_motif_coverage"]["distinct_count"] == 1


@pytest.mark.parametrize("missing_field", ["site_pattern", "binding_mode", "binding_atoms"])
def test_missing_identity_is_reported_without_guessing_from_motif_name(missing_field: str) -> None:
    unknown = candidate("O_long_bridge_monodentate", "long_bridge")
    del unknown[missing_field]
    reviewed = review(plan([
        candidate("top", "top"), candidate("short", "short_bridge"), unknown,
    ]))

    coverage = reviewed["initial_motif_coverage"]
    assert coverage["distinct_count"] == 2
    assert coverage["missing_identity_motif_ids"] == ["O_long_bridge_monodentate"]
    assert coverage["status"] == "NEEDS_REVIEW"
    assert reviewed["decision"] == "NEEDS_REVIEW"
    assert reviewed["candidate_count"] == 3


@pytest.mark.parametrize("field,invalid_value", [
    ("site_pattern", 0),
    ("site_pattern", []),
    ("binding_mode", True),
    ("binding_mode", []),
    ("binding_atoms", "O"),
    ("binding_atoms", [None]),
    ("binding_atoms", [1]),
    ("binding_atoms", []),
])
def test_invalid_identity_types_require_review(field: str, invalid_value) -> None:
    invalid = candidate("invalid", "long_bridge", **{field: invalid_value})
    reviewed = review(plan([
        candidate("top", "top"), candidate("short", "short_bridge"), invalid,
    ]))

    assert reviewed["decision"] == "NEEDS_REVIEW"
    assert reviewed["initial_motif_coverage"]["distinct_count"] == 2
    assert reviewed["initial_motif_coverage"]["missing_identity_motif_ids"] == ["invalid"]


@pytest.mark.parametrize("decision", ["BLOCKED", "PARTIAL", "NEEDS_WHITELIST", "NEEDS_LITERATURE"])
def test_coverage_review_preserves_existing_evidence_and_template_blockers(decision: str) -> None:
    reviewed = review(plan([
        candidate("top", "top"),
        candidate("short", "short_bridge"),
        candidate("long", "long_bridge", build_ready=False),
    ], decision=decision))

    assert reviewed["initial_motif_coverage"]["status"] == "PASS"
    assert reviewed["decision"] == decision
    assert reviewed["evidence_decision"] == decision
    assert reviewed["candidates"][-1]["build_ready"] is False


def test_free_text_history_and_suppression_do_not_prove_initial_coverage_or_add_reruns() -> None:
    source = plan(
        [candidate("retained_top")],
        evidence={"note": "All four historical starts ended in top-like final states."},
        suppressed=[{"site_patterns": ["short_bridge", "long_bridge", "hollow"],
                     "reason_code": "reviewed_duplicate_final_top_state"}],
    )

    reviewed = review(source)

    assert reviewed["decision"] == "NEEDS_REVIEW"
    assert reviewed["initial_motif_coverage"]["distinct_count"] == 1
    assert reviewed["candidates"] == source["candidates"]
    assert reviewed["suppressed"] == source["suppressed"]
    assert reviewed["candidate_count"] == 1


def test_cached_ready_and_cached_counts_cannot_replace_current_candidate_review() -> None:
    cached = review(plan([
        candidate("top", "top"),
        candidate("short", "short_bridge"),
        candidate("long", "long_bridge"),
    ]))
    assert cached["decision"] == "READY"
    # The candidate payload changed while the old PASS/three-mode claim remained.
    cached["candidates"] = [candidate("top"), candidate("top_rotated")]
    cached["candidate_count"] = 2
    cached["initial_motif_coverage"]["required_count"] = 1

    reviewed = review(cached)

    assert reviewed["decision"] == "NEEDS_REVIEW"
    assert reviewed["initial_motif_coverage"]["required_count"] == 3
    assert reviewed["initial_motif_coverage"]["distinct_count"] == 1
    assert reviewed["initial_motif_coverage"]["shortfall_count"] == 2


def test_repeated_review_preserves_original_evidence_decision() -> None:
    first = review(plan([candidate("top")]))

    second = review(first)

    assert second["evidence_decision"] == "READY"
    assert second == first


@pytest.mark.parametrize("surface_name", ["Fe100", "Fe111", "Fe5C2_010", "Fe3O4_001"])
def test_surface_name_does_not_bypass_initial_mode_review(surface_name: str) -> None:
    source = plan([candidate("only_mode")], surface=surface_name)

    reviewed = review(source, surface_name=surface_name)

    assert reviewed["decision"] == "NEEDS_REVIEW"
    assert reviewed["initial_motif_coverage"]["shortfall_count"] == 2


def test_explicit_plan_surface_must_match_requested_surface() -> None:
    source = plan([candidate("only_mode")], surface="Fe100")

    with pytest.raises(ValueError):
        review(source, surface_name="Fe110")


def test_batch_reports_shortfall_without_padding_candidates() -> None:
    reviewed = plan_batch(["H2O"], load_prescreen_rules(str(RULES_PATH)))

    assert reviewed["summary"]["candidate_count"] == 2
    assert reviewed["summary"]["ready_species"] == 0
    assert reviewed["summary"]["needs_review_species"] == 1
    assert reviewed["species_plans"][0]["final_stable_minima_count"] is None
