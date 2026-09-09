"""Reviewed-input retrieval application; ranking PASS never accepts science."""
from datetime import datetime, timezone
from pathlib import Path
from scripts.scientific_validation import finite_number
from .records import DEFAULT_SOURCES, load_jsonl, load_source_config, validate_records
from .ranking import record_text, semantic_scores, rank_records


def search_records(records: Path, *, query: str, sources: Path = DEFAULT_SOURCES,
                   model: str = "sentence-transformers/all-MiniLM-L6-v2", query_vector: Path | None = None,
                   top_k: int = 5, bm25_weight: float = 0.45, semantic_weight: float = 0.55,
                   lexical_only: bool = False) -> dict:
    bm25_weight = finite_number(bm25_weight, "bm25 weight", nonnegative=True)
    semantic_weight = finite_number(semantic_weight, "semantic weight", nonnegative=True)
    finite_number(bm25_weight + semantic_weight, "ranking weight sum", positive=True)
    if not 1 <= top_k <= 5:
        raise SystemExit("--top-k must be between 1 and 5")
    if bm25_weight < 0 or semantic_weight < 0 or bm25_weight + semantic_weight <= 0:
        raise SystemExit("retrieval weights must be non-negative with a positive sum")
    records = load_jsonl(records)
    if not records:
        raise SystemExit("no records to search")
    config = load_source_config(sources)
    failures = validate_records(records, config)
    if failures:
        return {"status": "STOP", "validation_failures": failures}

    documents = [record_text(record) for record in records]
    if lexical_only:
        semantic = None
        backend = "disabled-by-explicit-diagnostic-flag"
        production_ready = False
    else:
        semantic, backend = semantic_scores(records, documents, query, model, query_vector)
        production_ready = True
    results = rank_records(records, query, semantic, bm25_weight, semantic_weight, top_k)
    payload = {
        "status": "PASS" if production_ready else "DIAGNOSTIC_ONLY",
        "query": query,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "semantic_backend": backend,
        "weights": {"bm25": bm25_weight, "semantic": semantic_weight},
        "whitelist_valid": True,
        "production_ready": production_ready,
        "status_scope": "retrieval_ranking_only",
        "scientific_acceptance": False,
        "result_count": len(results),
        "results": results,
    }
    return payload
