from __future__ import annotations

import argparse
from pathlib import Path

from .adsmind_common import compact_table, write_jsonl
from .relaxed_analysis import analyze_relaxed_tree


ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect site slip, dissociation, and review gates in relaxed adsorption structures.")
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--relaxed-root", type=Path, required=True)
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analysis-rules", type=Path, default=ROOT / "configs" / "adsmind_lite" / "analysis_rules.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = analyze_relaxed_tree(args.candidate_root, args.relaxed_root, args.sites, args.analysis_rules)
    write_jsonl(args.output, records)
    print(compact_table(records[:40]))
    print(
        f"analyzed={len(records)} slip={sum(record['chemical_slip'] for record in records)} "
        f"dissociated={sum(record['dissociated'] for record in records)} "
        f"needs_review={sum(record['needs_review'] for record in records)}"
    )


if __name__ == "__main__":
    main()
