from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .cli_common import add_common_arguments
from .utils_report import write_json
from .utils_structure import numbered_image_dirs, preferred_image_structure


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a non-destructive NEB restart from image CONTCAR files.")
    add_common_arguments(parser)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit("Destination already exists; restart preparation never overwrites a run.")
    plan = []
    for directory in numbered_image_dirs(args.source):
        source = preferred_image_structure(directory)
        plan.append({"source": str(source), "destination": str(args.destination / directory.name / "POSCAR")})
    if len(plan) < 2:
        raise SystemExit("No complete numbered image set found.")
    if not args.dry_run:
        for item in plan:
            destination = Path(item["destination"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["source"], destination)
        write_json(args.destination / "restart_manifest.json", {"source": str(args.source), "files": plan})
    print(f"DRY_RUN {len(plan)} images" if args.dry_run else args.destination)


if __name__ == "__main__":
    main()
