from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.adsmind_lite.prescreen import load_prescreen_rules, plan_batch, plan_species


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "configs" / "adsmind_lite" / "prescreen_rules.yaml"
FTS_RULES = ROOT / "configs" / "adsmind_lite" / "iron_fts_prescreen.yaml"
FEATURES = ROOT / "tests" / "fixtures" / "unseen_fts_species_features.yaml"


def test_water_suppresses_redundant_four_site_sweep() -> None:
    rules = load_prescreen_rules(str(RULES))
    plan = plan_species("H2O", rules)

    assert plan["decision"] == "READY"
    assert [candidate["site_pattern"] for candidate in plan["candidates"]] == ["top", "top"]
    suppressed = {pattern for item in plan["suppressed"] for pattern in item["site_patterns"]}
    assert {"short_bridge", "long_bridge", "hollow"} <= suppressed


def test_cho_multidentate_plan_requires_reviewed_template() -> None:
    rules = load_prescreen_rules(str(RULES))
    blocked = plan_species("CHO_formyl", rules)
    ready = plan_species(
        "CHO_formyl",
        rules,
        available_templates={"CHO_eta2_CO_h_lb_h", "CHO_eta2_CO_h_lb_h_symmetry_partner"},
    )

    assert blocked["decision"] == "BLOCKED"
    assert all(candidate["binding_mode"] == "bidentate" for candidate in blocked["candidates"])
    assert ready["decision"] == "READY"


def test_unknown_species_does_not_trigger_blind_candidates() -> None:
    rules = load_prescreen_rules(str(RULES))
    plan = plan_batch(["unknown_C1"], rules)

    assert plan["summary"]["candidate_count"] == 0
    assert plan["species_plans"][0]["decision"] == "NEEDS_WHITELIST"


def test_known_metadata_does_not_bypass_external_evidence_gate() -> None:
    rules = load_prescreen_rules(str(RULES))
    catalog = {
        "HCO": {
            "class": "C1_oxygenate",
            "atom_symbols": ["C", "O", "H"],
            "preferred_binding_atoms": ["C", "O"],
        }
    }
    plan = plan_species("HCO", rules, adsorbate_catalog=catalog)

    assert plan["decision"] == "NEEDS_WHITELIST"
    assert plan["candidate_count"] == 0
    assert plan["search_metadata_available"] is True


def test_reviewed_local_plan_has_priority_over_external_plan() -> None:
    rules = load_prescreen_rules(str(RULES))
    external = {
        "H2O": {
            "species": "H2O",
            "decision": "READY",
            "candidate_count": 1,
            "candidates": [{"motif_id": "external_hollow", "site_pattern": "hollow", "build_ready": True}],
        }
    }

    plan = plan_species("H2O", rules, external_plans=external)

    assert plan["plan_source"] == "reviewed_local_species_rule"
    assert plan["evidence_priority_rank"] == 1
    assert [candidate["motif_id"] for candidate in plan["candidates"]] == [
        "H2O_O_top_orientation_a",
        "H2O_O_top_orientation_b",
    ]


def test_external_plan_is_used_only_after_local_rules_miss() -> None:
    rules = load_prescreen_rules(str(RULES))
    external_plan = {
        "species": "unknown_C1",
        "decision": "READY",
        "candidate_count": 1,
        "candidates": [{"motif_id": "external_top", "site_pattern": "top", "build_ready": True}],
    }

    plan = plan_species("unknown_C1", rules, external_plans={"unknown_C1": external_plan})

    assert plan["plan_source"] == "external_evidence_gate"
    assert plan["evidence_priority_rank"] == 3
    assert plan["candidates"] == external_plan["candidates"]


def test_feature_based_fts_is_exposed_only_as_retrieval_hypotheses() -> None:
    from scripts.adsmind_lite.fts_prescreen import load_fts_rules

    rules = load_prescreen_rules(str(RULES))
    fts_rules = load_fts_rules(str(FTS_RULES))
    features = {
        "unseen_CH2_radical": {
            "carbon_centers": [{"label": "C1", "coordination_demand": 2, "surface_accessible": True}],
            "oxygen_centers": [],
        }
    }

    plan = plan_species(
        "unseen_CH2_radical",
        rules,
        fts_rules=fts_rules,
        species_features=features,
    )

    assert plan["decision"] == "NEEDS_WHITELIST"
    assert plan["plan_source"] == "feature_based_retrieval_hypotheses"
    assert plan["candidate_count"] == 0
    assert plan["candidates"] == []
    assert plan["search_hypothesis_count"] > 0
    assert all(item["build_ready"] is False for item in plan["search_hypotheses"])


def test_feature_based_fts_cli_writes_retrieval_hypotheses_only(tmp_path: Path) -> None:
    output = tmp_path / "plan.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.adsmind_lite.plan_adsorption_candidates",
            "--species",
            "unseen_CH2_radical",
            "--species-features",
            str(FEATURES),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    plan = json.loads(output.read_text(encoding="utf-8"))
    species_plan = plan["species_plans"][0]
    assert "search_hypotheses=" in result.stdout
    assert species_plan["candidate_count"] == 0
    assert species_plan["search_hypothesis_count"] > 0
