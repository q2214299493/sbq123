from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .cli_common import add_common_arguments
from .utils_report import write_json
from .utils_structure import numbered_image_dirs, preferred_image_structure


def main() -> None:
    parser = argparse.ArgumentParser(description="Crop a reviewed contiguous image range into a new NEB endpoint set.")
    add_common_arguments(parser)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit("Destination already exists.")
    selected = [path for path in numbered_image_dirs(args.source) if args.start <= int(path.name) <= args.end]
    if len(selected) < 2:
        raise SystemExit("The selected range must contain at least two images.")
    manifest = []
    for new_index, directory in enumerate(selected):
        source = preferred_image_structure(directory)
        destination = args.destination / f"{new_index:02d}" / "POSCAR"
        manifest.append({"old_image": directory.name, "new_image": f"{new_index:02d}", "source": str(source)})
        if not args.dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    if not args.dry_run:
        write_json(args.destination / "crop_manifest.json", {"source": str(args.source), "images": manifest})
    print(f"DRY_RUN {len(selected)} images" if args.dry_run else args.destination)


if __name__ == "__main__":
    main()
