from __future__ import annotations

import argparse
from pathlib import Path


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workdir", type=Path, default=Path("neb_project"))
    parser.add_argument("--is", dest="initial", type=Path)
    parser.add_argument("--fs", dest="final", type=Path)
    parser.add_argument("--images", type=int, default=5)
    parser.add_argument("--reaction-atoms", default="")
    parser.add_argument(
        "--surface-family",
        choices=("metal_fe", "iron_carbide", "iron_oxide", "unknown"),
        default="unknown",
    )
    parser.add_argument("--material", default="unknown")
    parser.add_argument("--fixed-indices", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")


def comma_tokens(value: str) -> list[str]:
    return [token.strip() for token in value.split(",") if token.strip()]


def require_paths(args: argparse.Namespace, *names: str) -> None:
    for name in names:
        value = getattr(args, name)
        if value is None:
            raise SystemExit(f"--{name.replace('_', '-')} is required")
        if not value.exists():
            raise SystemExit(f"File not found: {value}")
