#!/usr/bin/env python3
"""Compatibility launcher for the repository-owned, evidence-gated CO builder."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


REPOSITORY_FILES = (
    "configs/skill_routing.yaml",
    "modules/adsmind_lite/README.md",
    "scripts/adsmind_lite/generate_adsorption_candidates.py",
)


def find_repository(surface: Path, explicit: Path | None = None) -> Path:
    if explicit is not None:
        repository = explicit.resolve()
        for relative in REPOSITORY_FILES:
            if not (repository / relative).is_file():
                raise ValueError(f"Missing canonical repository file: {repository / relative}")
        return repository
    candidates = {
        root
        for start in (Path.cwd().resolve(), surface.resolve().parent)
        for root in (start, *start.parents)
        if all((root / relative).is_file() for relative in REPOSITORY_FILES)
    }
    if len(candidates) != 1:
        detail = ", ".join(str(path) for path in sorted(candidates)) or "none"
        raise ValueError(f"Cannot identify one canonical repository ({detail}); use --repo-root.")
    return candidates.pop()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare missing inputs and delegate CO generation to the current catalysis repository.",
    )
    parser.add_argument("slab_poscar", type=Path, help="Clean slab POSCAR.")
    parser.add_argument("--repo-root", type=Path, help="Defaults to the unique project above cwd or the POSCAR.")
    parser.add_argument("--sites", type=Path, help="Repository site JSON; omitted means detect from this slab.")
    parser.add_argument("--plan", type=Path, help="Plan JSON; omitted means use a sidecar or prepare a draft.")
    parser.add_argument("--outdir", type=Path, help="New output directory; omitted means a fresh project runtime directory.")
    args = parser.parse_args()

    # Resolve caller paths before changing cwd for the repository module.
    surface = args.slab_poscar.resolve()
    for label, path in (("surface", surface), ("sites JSON", args.sites), ("reviewed plan", args.plan)):
        if path is not None and not path.is_file():
            parser.error(f"Missing {label} file: {path}")
    try:
        repository = find_repository(surface, args.repo_root)
    except ValueError as exc:
        parser.error(str(exc))
    command = [
        sys.executable, "-m", "scripts.adsmind_lite.generate_adsorption_candidates",
        "--surface", str(surface), "--adsorbates", "CO", "--prepare-missing",
    ]
    for flag, path in (("--sites", args.sites), ("--plan", args.plan), ("--output", args.outdir)):
        if path is not None:
            command.extend((flag, str(path.resolve())))
    print(f"repository={repository}", flush=True)
    try:
        return subprocess.run(command, cwd=repository, check=False).returncode
    except OSError as exc:
        parser.exit(2, f"Could not start the repository builder: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
