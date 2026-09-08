from __future__ import annotations

import argparse
from pathlib import Path

from .adsmind_common import read_jsonl, write_jsonl
from .candidate_export import export_selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export only recommended adsorption structures; never submit jobs.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--include-medium",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Export selected medium-confidence records (default: enabled).",
    )
    parser.add_argument("--include-low", action="store_true")
    parser.add_argument("--include-needs-review", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exported = export_selected(
        read_jsonl(args.input),
        args.output,
        include_medium=args.include_medium,
        include_low=args.include_low,
        include_needs_review=args.include_needs_review,
    )
    write_jsonl(args.output / "exported.jsonl", exported)
    print(
        f"exported={len(exported)} include_medium={args.include_medium} include_low={args.include_low} "
        f"include_needs_review={args.include_needs_review} submitted=0"
    )


if __name__ == "__main__":
    main()
