#!/usr/bin/env python3
"""Dependency-light checks for whitelist rejection and hybrid ranking."""

from __future__ import annotations

import argparse

import numpy as np

from hybrid_search import rank_records, record_text, semantic_scores
from validate_records import load_source_config, source_map, validate_record, DEFAULT_SOURCES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-model", action="store_true")
    args = parser.parse_args()
    config = load_source_config(DEFAULT_SOURCES)
    sources = source_map(config)
    base = {
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
    }
    assert validate_record(base, sources) == []
    invalid = dict(base, source_url="https://example.com/not-allowed")
    assert "source_url_not_allowed" in validate_record(invalid, sources)
    other = dict(
        base,
        id="pt-co",
        title="CO adsorption on Pt(111)",
        summary="molecular adsorption",
        material="Pt",
        surface="111",
        reaction="CO adsorption",
    )
    records = [base, other]
    semantic = np.array([0.95, 0.10])
    ranked = rank_records(records, "Fe(110) CO dissociation path", semantic, 0.45, 0.55, 2)
    assert ranked[0]["record"]["id"] == "fe-co-path"
    assert len(ranked) == 2
    if args.with_model:
        scores, backend = semantic_scores(
            records,
            [record_text(record) for record in records],
            "Fe(110) CO dissociation transition path",
            "sentence-transformers/all-MiniLM-L6-v2",
            None,
        )
        model_ranked = rank_records(records, "Fe(110) CO dissociation transition path", scores, 0.45, 0.55, 2)
        assert backend.startswith("sentence-transformers:")
        assert model_ranked[0]["record"]["id"] == "fe-co-path"
    print("PASS")


if __name__ == "__main__":
    main()
