from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .cli_common import add_common_arguments
from .utils_report import write_json
from .utils_structure import numbered_image_dirs


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare two endpoint pairs around a scientifically reviewed intermediate image.")
    add_common_arguments(parser)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--intermediate", type=int, required=True)
    args = parser.parse_args()
    images = numbered_image_dirs(args.source)
    by_index = {int(path.name): path for path in images}
    first, last = min(by_index), max(by_index)
    if args.intermediate not in by_index or args.intermediate in {first, last}:
        raise SystemExit("Intermediate must be an existing internal image.")
    if args.destination.exists():
        raise SystemExit("Destination already exists.")
    pairs = {"segment_1": [first, args.intermediate], "segment_2": [args.intermediate, last]}
    manifest = {"source": str(args.source), "review_required": True, "segments": {}}
    for segment, pair in pairs.items():
        manifest["segments"][segment] = pair
        for new_index, old_index in enumerate(pair):
            source = by_index[old_index] / "CONTCAR"
            if not source.is_file() or source.stat().st_size == 0:
                source = by_index[old_index] / "POSCAR"
            destination = args.destination / segment / f"{new_index:02d}" / "POSCAR"
            if not args.dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    if not args.dry_run:
        write_json(args.destination / "split_manifest.json", manifest)
    print("DRY_RUN" if args.dry_run else args.destination)


if __name__ == "__main__":
    main()
