from __future__ import annotations

import argparse
from pathlib import Path

from .adsmind_common import compact_table, load_yaml, read_jsonl, write_jsonl
from .state_deduplication import deduplicate_records


ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mark duplicate relaxed adsorption states using compact fingerprints and RMSD.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analysis-rules", type=Path, default=ROOT / "configs" / "adsmind_lite" / "analysis_rules.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = deduplicate_records(read_jsonl(args.input), load_yaml(args.analysis_rules))
    write_jsonl(args.output, records)
    print(compact_table(records[:40]))
    print(f"records={len(records)} duplicates={sum(record['duplicate'] for record in records)}")


if __name__ == "__main__":
    main()
