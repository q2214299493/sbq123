from __future__ import annotations

import argparse
from pathlib import Path

from .adsmind_common import write_json
from .site_detection import detect_surface_sites


ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect compact standardized adsorption sites without running calculations.")
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--surface-name", required=True)
    parser.add_argument("--surface-family", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-manifest", "--explicit-sites", dest="site_manifest", type=Path)
    parser.add_argument("--surfaces-config", type=Path, default=ROOT / "configs" / "adsmind_lite" / "surfaces.yaml")
    parser.add_argument("--site-rules", type=Path, default=ROOT / "configs" / "adsmind_lite" / "site_rules.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = detect_surface_sites(
        args.surface,
        args.surface_name,
        args.surface_family,
        args.surfaces_config,
        args.site_rules,
        args.site_manifest,
    )
    write_json(args.output, payload)
    print(
        f"surface={payload['surface_name']} family={payload['surface_family']} "
        f"status={payload['status']} sites={len(payload['sites'])} needs_review={payload['needs_review']}"
    )


if __name__ == "__main__":
    main()
