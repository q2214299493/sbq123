#!/usr/bin/env python3
"""Compatibility launcher for the repository-owned, evidence-gated CO builder."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delegate CO candidate generation to an explicitly selected catalysis repository; no standalone site sweep.",
    )
    parser.add_argument("slab_poscar", type=Path, help="Clean slab POSCAR.")
    parser.add_argument("--repo-root", type=Path, required=True, help="Project containing the canonical AdsMind modules and routing config.")
    parser.add_argument("--sites", type=Path, required=True, help="Repository-generated site JSON, not a comma-separated site list.")
    parser.add_argument("--plan", type=Path, required=True, help="Reviewed, evidence-gated candidate plan JSON.")
    parser.add_argument("--outdir", type=Path, required=True, help="Explicit candidate output directory.")
    args = parser.parse_args()

    repository = args.repo_root.resolve()
    for relative in (
        "configs/skill_routing.yaml",
        "modules/adsmind_lite/README.md",
        "scripts/adsmind_lite/generate_adsorption_candidates.py",
    ):
        if not (repository / relative).is_file():
            parser.error(f"Missing canonical repository file: {repository / relative}")
    # Resolve caller paths before changing cwd for the repository module.
    surface, sites, plan = (path.resolve() for path in (args.slab_poscar, args.sites, args.plan))
    for label, path in (("surface", surface), ("sites JSON", sites), ("reviewed plan", plan)):
        if not path.is_file():
            parser.error(f"Missing {label} file: {path}")
    command = [
        sys.executable, "-m", "scripts.adsmind_lite.generate_adsorption_candidates",
        "--surface", str(surface), "--sites", str(sites), "--plan", str(plan),
        "--adsorbates", "CO", "--output", str(args.outdir.resolve()),
    ]
    try:
        return subprocess.run(command, cwd=repository, check=False).returncode
    except OSError as exc:
        parser.exit(2, f"Could not start the repository builder: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
