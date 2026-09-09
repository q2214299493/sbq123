"""Legacy skill CLI/import facade for catalysis_retrieval ranking."""
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


from scripts.catalysis_retrieval.cli import main as installed_main


def main() -> None:
    installed_main()


if __name__ == "__main__":
    main()
