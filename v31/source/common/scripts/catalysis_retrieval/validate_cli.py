"""Installed retrieval CLI; delegates to the existing evidence/ranking owners."""
import argparse
import json
from pathlib import Path
from .records import DEFAULT_SOURCES, load_jsonl, load_source_config, validate_records


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
