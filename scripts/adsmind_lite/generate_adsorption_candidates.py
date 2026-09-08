from __future__ import annotations

import argparse
from pathlib import Path

from .candidate_generation import generate_candidates


ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate capped anchor-based adsorption candidates.")
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument("--adsorbates", required=True, help="Comma-separated adsorbate names.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True, help="Evidence-gated candidate plan JSON.")
    parser.add_argument("--backend", choices=("no_relax", "ase_mlff_relax", "vasp_low_cost_relax"), default="no_relax")
    parser.add_argument(
        "--adsorbate-rules",
        type=Path,
        default=ROOT / "configs" / "adsmind_lite" / "adsorbate_rules.yaml",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    names = [value.strip() for value in args.adsorbates.split(",") if value.strip()]
    records = generate_candidates(args.surface, args.sites, names, args.adsorbate_rules, args.output, args.plan, args.backend)
    failed = sum(not record.get("initial_structure") for record in records)
    print(f"requested={len(names)} generated={len(records) - failed} failed={failed} backend={args.backend} submitted=0")


if __name__ == "__main__":
    main()
