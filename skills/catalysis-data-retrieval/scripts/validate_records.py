"""Legacy skill CLI/import facade for scripts.catalysis_retrieval.records."""
from scripts.catalysis_retrieval.records import (
    load_source_config as load_source_config,
    source_map as source_map,
    url_allowed as url_allowed,
    _artifact_url_errors as _artifact_url_errors,
    _embedding_errors as _embedding_errors,
    validate_embedding as validate_embedding,
    validate_record as validate_record,
    load_jsonl as load_jsonl,
    validate_records as validate_records,
    SKILL_ROOT as SKILL_ROOT,
    DEFAULT_SOURCES as DEFAULT_SOURCES,
    REQUIRED_FIELDS as REQUIRED_FIELDS,
)


from scripts.catalysis_retrieval.validate_cli import main as installed_main


def main() -> None:
    installed_main()


if __name__ == "__main__":
    main()
