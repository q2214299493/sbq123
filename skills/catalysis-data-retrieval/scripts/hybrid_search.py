"""Legacy skill CLI/import facade for catalysis_retrieval ranking."""
import argparse
import json
from pathlib import Path
from scripts.catalysis_retrieval.records import DEFAULT_SOURCES
from scripts.catalysis_retrieval.workflow import search_records
from scripts.catalysis_retrieval.ranking import (
    tokenize as tokenize,
    record_text as record_text,
    bm25_scores as bm25_scores,
    cosine_scores as cosine_scores,
    load_query_vector as load_query_vector,
    semantic_scores as semantic_scores,
    ranks_descending as ranks_descending,
    rank_records as rank_records,
    TOKEN_PATTERN as TOKEN_PATTERN,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("records", type=Path)
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", type=Path, default=Path("retrieval_top5.json"))
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--query-vector", type=Path)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--bm25-weight", type=float, default=0.45)
    parser.add_argument("--semantic-weight", type=float, default=0.55)
    parser.add_argument("--lexical-only", action="store_true", help="Diagnostic only; does not pass the production gate.")
    args = parser.parse_args()

    payload = search_records(args.records, query=args.query, sources=args.sources, model=args.model,
                             query_vector=args.query_vector, top_k=args.top_k, bm25_weight=args.bm25_weight,
                             semantic_weight=args.semantic_weight, lexical_only=args.lexical_only)
    if payload["status"] == "STOP":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
