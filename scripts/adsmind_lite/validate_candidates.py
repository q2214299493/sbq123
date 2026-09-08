from __future__ import annotations

import argparse
from pathlib import Path

from .adsmind_common import compact_table, write_jsonl
from .relaxed_analysis import validate_candidates


ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate adsorption candidates and write compact JSONL.")
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--invalid-output", type=Path)
    parser.add_argument("--surfaces-config", type=Path, default=ROOT / "configs" / "adsmind_lite" / "surfaces.yaml")
    parser.add_argument("--adsorbate-rules", type=Path, default=ROOT / "configs" / "adsmind_lite" / "adsorbate_rules.yaml")
    parser.add_argument("--analysis-rules", type=Path, default=ROOT / "configs" / "adsmind_lite" / "analysis_rules.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = validate_candidates(args.candidate_root, args.surfaces_config, args.adsorbate_rules, args.analysis_rules)
    write_jsonl(args.output, records)
    invalid = [record for record in records if not record["validation_passed"]]
    write_jsonl(args.invalid_output or args.output.with_name("invalid_candidates.jsonl"), invalid)
    print(compact_table(records[:40]))
    print(f"validated={len(records)} passed={len(records) - len(invalid)} invalid={len(invalid)}")


if __name__ == "__main__":
    main()
