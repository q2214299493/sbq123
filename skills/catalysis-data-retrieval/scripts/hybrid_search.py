#!/usr/bin/env python3
"""Rank whitelist-valid catalysis records with BM25 and semantic embeddings."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from validate_records import DEFAULT_SOURCES, load_jsonl, load_source_config, validate_records


TOKEN_PATTERN = re.compile(r"[A-Za-z]+(?:[-_/][A-Za-z0-9]+)*|\d+(?:\.\d+)?|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def record_text(record: dict) -> str:
    fields = [
        record.get("title", ""),
        record.get("summary", ""),
        record.get("material", ""),
        record.get("surface", ""),
        record.get("reaction", ""),
        " ".join(map(str, record.get("adsorbates", []))),
        " ".join(map(str, record.get("data_types", []))),
        " ".join(map(str, record.get("keywords", []))),
    ]
    return " ".join(str(value) for value in fields if value)


def bm25_scores(query: str, documents: list[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
    tokenized = [tokenize(document) for document in documents]
    query_tokens = tokenize(query)
    lengths = np.array([len(tokens) for tokens in tokenized], dtype=float)
    average_length = float(lengths.mean()) if len(lengths) and lengths.mean() else 1.0
    document_frequency = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))
    scores = np.zeros(len(documents), dtype=float)
    total = len(documents)
    for index, tokens in enumerate(tokenized):
        frequencies = Counter(tokens)
        for token in query_tokens:
            frequency = frequencies[token]
            if not frequency:
                continue
            df = document_frequency[token]
            idf = math.log(1.0 + (total - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1.0 - b + b * lengths[index] / average_length)
            scores[index] += idf * frequency * (k1 + 1.0) / denominator
    return scores


def cosine_scores(query_vector: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    query_norm = np.linalg.norm(query_vector)
    vector_norms = np.linalg.norm(vectors, axis=1)
    if query_norm == 0 or np.any(vector_norms == 0):
        raise ValueError("semantic vectors must have non-zero norm")
    return vectors @ query_vector / (vector_norms * query_norm)


def load_query_vector(path: Path) -> np.ndarray:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("embedding")
    if not isinstance(payload, list) or not payload:
        raise ValueError("query vector must be a non-empty JSON array or an object with embedding")
    return np.asarray(payload, dtype=float)


def semantic_scores(
    records: list[dict], documents: list[str], query: str, model_name: str, query_vector_path: Path | None
) -> tuple[np.ndarray, str]:
    if query_vector_path:
        query_vector = load_query_vector(query_vector_path)
        if any("embedding" not in record for record in records):
            raise ValueError("every record needs an embedding when --query-vector is used")
        vectors = np.asarray([record["embedding"] for record in records], dtype=float)
        if vectors.ndim != 2 or vectors.shape[1] != query_vector.shape[0]:
            raise ValueError("record and query embedding dimensions do not match")
        return cosine_scores(query_vector, vectors), "precomputed-reviewed"
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required for production hybrid search; install it or provide reviewed precomputed embeddings"
        ) from exc
    model = SentenceTransformer(model_name)
    encoded = model.encode([query, *documents], normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(encoded[1:]) @ np.asarray(encoded[0]), f"sentence-transformers:{model_name}"


def ranks_descending(scores: np.ndarray) -> np.ndarray:
    order = np.argsort(-scores, kind="stable")
    ranks = np.empty(len(scores), dtype=int)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks


def rank_records(
    records: list[dict],
    query: str,
    semantic: np.ndarray | None,
    bm25_weight: float,
    semantic_weight: float,
    top_k: int,
) -> list[dict]:
    documents = [record_text(record) for record in records]
    lexical = bm25_scores(query, documents)
    lexical_ranks = ranks_descending(lexical)
    if semantic is None:
        hybrid = lexical
        semantic_ranks = np.zeros(len(records), dtype=int)
    else:
        semantic_ranks = ranks_descending(semantic)
        hybrid = bm25_weight / (60.0 + lexical_ranks) + semantic_weight / (60.0 + semantic_ranks)
    order = np.argsort(-hybrid, kind="stable")[:top_k]
    results = []
    for rank, index in enumerate(order, start=1):
        record = records[int(index)]
        results.append(
            {
                "rank": rank,
                "hybrid_score": float(hybrid[index]),
                "bm25_score": float(lexical[index]),
                "semantic_score": None if semantic is None else float(semantic[index]),
                "record": {key: value for key, value in record.items() if key != "embedding"},
            }
        )
    return results


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

    if not 1 <= args.top_k <= 5:
        raise SystemExit("--top-k must be between 1 and 5")
    if args.bm25_weight < 0 or args.semantic_weight < 0 or args.bm25_weight + args.semantic_weight <= 0:
        raise SystemExit("retrieval weights must be non-negative with a positive sum")
    records = load_jsonl(args.records)
    if not records:
        raise SystemExit("no records to search")
    config = load_source_config(args.sources)
    failures = validate_records(records, config)
    if failures:
        print(json.dumps({"status": "STOP", "validation_failures": failures}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    documents = [record_text(record) for record in records]
    if args.lexical_only:
        semantic = None
        backend = "disabled-by-explicit-diagnostic-flag"
        production_ready = False
    else:
        semantic, backend = semantic_scores(records, documents, args.query, args.model, args.query_vector)
        production_ready = True
    results = rank_records(records, args.query, semantic, args.bm25_weight, args.semantic_weight, args.top_k)
    payload = {
        "status": "PASS" if production_ready else "DIAGNOSTIC_ONLY",
        "query": args.query,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "semantic_backend": backend,
        "weights": {"bm25": args.bm25_weight, "semantic": args.semantic_weight},
        "whitelist_valid": True,
        "production_ready": production_ready,
        "result_count": len(results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
