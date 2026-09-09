"""Legacy skill CLI/import facade for scripts.catalysis_retrieval.records."""
import argparse
import json
from pathlib import Path
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("records", type=Path)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    args = parser.parse_args()
    records = load_jsonl(args.records)
    failures = validate_records(records, load_source_config(args.sources))
    print(json.dumps({"records": len(records), "valid": not failures, "failures": failures}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
