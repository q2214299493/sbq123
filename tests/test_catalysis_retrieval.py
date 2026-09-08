from __future__ import annotations

from pathlib import Path

import numpy as np

from hybrid_search import rank_records
from scripts.neb_agent.retrieval_prior_adapter import normalize_retrieval_prior
from validate_records import DEFAULT_SOURCES, load_source_config, source_map, validate_record


def record(**overrides: object) -> dict:
    value = {
        "id": "fe-co-path",
        "source_id": "catalysis-hub",
        "source_url": "https://api.catalysis-hub.org/graphql",
        "source_access_verified": True,
        "title": "CO dissociation on Fe(110)",
        "summary": "tilted molecular CO to coadsorbed carbon and oxygen",
        "retrieved_at": "2026-06-24T00:00:00Z",
        "data_types": ["reaction_path", "structure"],
        "material": "Fe",
        "surface": "110",
        "reaction": "CO dissociation",
        "match_confidence": "high",
    }
    value.update(overrides)
    return value


def test_whitelist_rejects_external_url() -> None:
    sources = source_map(load_source_config(DEFAULT_SOURCES))
    assert validate_record(record(), sources) == []
    assert "source_url_not_allowed" in validate_record(record(source_url="https://example.com/data"), sources)


def test_hybrid_rank_is_limited_and_relevant() -> None:
    records = [record()]
    records.extend(
        record(id=f"pt-{index}", title=f"CO adsorption on Pt(111) case {index}", material="Pt", surface="111", reaction="CO adsorption")
        for index in range(7)
    )
    semantic = np.array([0.95, *([0.10] * 7)])
    ranked = rank_records(records, "Fe(110) CO dissociation path", semantic, 0.45, 0.55, 5)
    assert len(ranked) == 5
    assert ranked[0]["record"]["id"] == "fe-co-path"


def test_neb_prior_requires_access_verified_result() -> None:
    source = {
        "whitelist_valid": True,
        "production_ready": True,
        "semantic_backend": "test",
        "results": [{"rank": 1, "hybrid_score": 0.03, "record": record()}],
    }
    _, constraints = normalize_retrieval_prior(source, Path("retrieval_top5.json"), "metal_fe", "Fe110")
    assert constraints["use_retrieval_prior"] is True
    assert constraints["review_status"] == "needs_review"
    source["results"][0]["record"]["source_access_verified"] = False
    _, blocked = normalize_retrieval_prior(source, Path("retrieval_top5.json"), "metal_fe", "Fe110")
    assert blocked["use_retrieval_prior"] is False
