from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.adsmind_lite.evidence_gate import resolve_external_evidence
from scripts.artifact_io import sha256_file
from tests.evidence_fixtures import bound_evidence


ROOT = Path(__file__).resolve().parents[1]
RULES = yaml.safe_load((ROOT / "configs" / "adsmind_lite" / "evidence_gate.yaml").read_text(encoding="utf-8"))
TEMPLATE_PATH = None


@pytest.fixture(autouse=True)
def reviewed_template(tmp_path, monkeypatch):
    path = tmp_path / "template.vasp"
    path.write_text("synthetic C motif\n1\n5 0 0\n0 5 0\n0 0 5\nC\n1\nDirect\n0 0 0\n")
    monkeypatch.setitem(globals(), "TEMPLATE_PATH", path)


def motif(motif_id: str, site: str, stability_rank: int = 1) -> dict:
    return {
        "motif_id": motif_id,
        "site_pattern": site,
        "binding_mode": "monodentate",
        "binding_atoms": ["C"],
        "geometry_summary": f"C bound at {site}",
        "stability_evidence": "compared_relaxed_adsorption_energies",
        "stability_rank": stability_rank,
        "reviewed_structure_template": {"path": str(TEMPLATE_PATH), "sha256": sha256_file(TEMPLATE_PATH)},
    }


def literature_record(record_id: str, motifs: list[dict]) -> dict:
    record = {
        "record_id": record_id,
        "journal": "Journal of the American Chemical Society",
        "doi": f"10.0000/{record_id}",
        "publisher_url": f"https://doi.org/10.0000/{record_id}",
        "journal_authority_review": "accepted",
        "doi_verified": True,
        "article_type": "primary_research",
        "exact_surface_match": True,
        "exact_adsorbate_match": True,
        "stable_motifs": motifs,
    }
    record["evidence"] = bound_evidence(record, compatibility={"species": motifs[0]["motif_id"].split("_")[0], "surface": "Fe110"})
    return record


def whitelist_record(record_id: str, motifs: list[dict], *, exact: bool = True) -> dict:
    record = {
        "id": record_id, "source_id": "catalysis-hub", "source_url": "https://api.catalysis-hub.org/graphql",
        "source_access_verified": True, "retrieved_at": "2026-09-09T00:00:00Z",
        "title": "Synthetic carbon motif", "summary": "Synthetic bound source", "data_types": ["structure"],
        "record_id": record_id,
        "exact_surface_match": exact,
        "exact_adsorbate_match": exact,
        "stable_motifs": motifs,
    }
    record["evidence"] = bound_evidence(record)
    return record


def test_whitelist_match_stops_literature_fallback() -> None:
    payload = {
        "species": "C",
        "surface": "Fe110",
        "whitelist": {"status": "MATCH", "records": [whitelist_record("db-1", [motif("C_hollow", "hollow")])]},
        "literature": {"searched": True, "records": []},
    }
    with pytest.raises(ValueError, match="literature_search_forbidden"):
        resolve_external_evidence(payload, RULES)


def test_whitelist_match_must_be_exact_and_usable() -> None:
    payload = {
        "species": "C",
        "surface": "Fe110",
        "whitelist": {"status": "MATCH", "records": [whitelist_record("db-1", [motif("C_hollow", "hollow")], exact=False)]},
    }
    with pytest.raises(ValueError, match="usable_stable_motif"):
        resolve_external_evidence(payload, RULES)


def test_no_whitelist_match_requires_literature_before_candidates() -> None:
    payload = {
        "species": "C",
        "surface": "Fe110",
        "whitelist": {"status": "NO_WHITELIST_MATCH", "records": []},
        "literature": {"searched": False, "records": []},
    }
    plan = resolve_external_evidence(payload, RULES)
    assert plan["decision"] == "NEEDS_LITERATURE"
    assert plan["candidate_count"] == 0


def test_literature_candidate_count_equals_unique_supported_stable_motifs() -> None:
    first = motif("C_hollow_bent", "hollow", 1)
    second = motif("C_hollow_tilted", "hollow", 2)
    payload = {
        "species": "C",
        "surface": "Fe110",
        "whitelist": {"status": "NO_WHITELIST_MATCH", "records": []},
        "literature": {
            "searched": True,
            "records": [literature_record("paper-a", [first, second]), literature_record("paper-b", [first])],
        },
    }
    plan = resolve_external_evidence(payload, RULES)
    assert plan["decision"] == "READY"
    assert plan["candidate_count"] == 2
    assert [item["motif_id"] for item in plan["candidates"]] == ["C_hollow_bent", "C_hollow_tilted"]
    assert plan["candidates"][0]["source_ids"] == ["paper-a", "paper-b"]


def test_nonexact_literature_does_not_seed_a_calculation() -> None:
    record = literature_record("paper-a", [motif("C_hollow", "hollow")])
    record["exact_surface_match"] = False
    payload = {
        "species": "C",
        "surface": "Fe110",
        "whitelist": {"status": "NO_WHITELIST_MATCH", "records": []},
        "literature": {"searched": True, "records": [record]},
    }
    plan = resolve_external_evidence(payload, RULES)
    assert plan["decision"] == "NEEDS_REVIEW"
    assert plan["candidate_count"] == 0


def test_four_candidates_are_kept_only_when_four_stable_motifs_are_supported() -> None:
    motifs = [
        motif(f"C_mode_{index}", site, index)
        for index, site in enumerate(("top", "short_bridge", "long_bridge", "hollow"), start=1)
    ]
    payload = {
        "species": "C",
        "surface": "Fe110",
        "whitelist": {"status": "NO_WHITELIST_MATCH", "records": []},
        "literature": {"searched": True, "records": [literature_record("paper-four", motifs)]},
    }
    plan = resolve_external_evidence(payload, RULES)
    assert plan["candidate_count"] == 4


def test_candidates_are_ranked_for_geometry_selection_and_external_energy_is_not_importable() -> None:
    payload = {
        "species": "CHO",
        "surface": "Fe110",
        "whitelist": {"status": "NO_WHITELIST_MATCH", "records": []},
        "literature": {
            "searched": True,
            "records": [
                literature_record(
                    "paper-a",
                    [motif("CHO_t_lb_t", "t-lb-t", 2), motif("CHO_h_lb_h", "h-lb-h", 1)],
                )
            ],
        },
    }
    plan = resolve_external_evidence(payload, RULES)

    assert [candidate["motif_id"] for candidate in plan["candidates"]] == ["CHO_h_lb_h", "CHO_t_lb_t"]
    assert plan["evidence"]["usage_scope"] == "structure_selection_stability_order_and_initial_geometry_only"
    assert plan["evidence"]["external_energy_use"] == "relative_order_reference_only"
    assert plan["evidence"]["energy_import_allowed"] is False


@pytest.mark.parametrize("damage", ["missing_content", "review_flag_only", "wrong_target", "outside_whitelist"])
def test_claimed_match_cannot_replace_bound_source_and_review(damage):
    record = whitelist_record("db-1", [motif("C_top", "top")])
    if damage == "missing_content":
        del record["evidence"]["content"]
    elif damage == "review_flag_only":
        record["evidence"]["review"] = {"reviewed": True}
    elif damage == "wrong_target":
        record["evidence"] = bound_evidence(record, compatibility={"species": "C", "surface": "Pt111"})
    else:
        record["source_url"] = "https://example.org/not-whitelisted"
        record["evidence"] = bound_evidence(record)
    with pytest.raises(ValueError, match="usable_stable_motif"):
        resolve_external_evidence({"species": "C", "surface": "Fe110", "whitelist": {"status": "MATCH", "records": [record]}}, RULES)


def test_changed_template_invalidates_previously_ready_plan():
    from scripts.adsmind_lite.evidence_gate import validate_external_plan

    record = whitelist_record("db-1", [motif("C_top", "top")])
    plan = resolve_external_evidence({"species": "C", "surface": "Fe110", "whitelist": {"status": "MATCH", "records": [record]}}, RULES)
    assert plan["decision"] == "READY"
    TEMPLATE_PATH.write_text("changed template")
    with pytest.raises(ValueError, match="stale"):
        validate_external_plan(plan, species="C", surface="Fe110")
