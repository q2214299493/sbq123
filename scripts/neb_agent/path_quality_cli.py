from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.artifact_io import write_json
from scripts.neb_agent.path_quality_service import (
    PathQualityRequest,
    build_path_quality_report,
    read_configured_nelm,
)


ROOT = Path(__file__).resolve().parents[2]


def _pair(value: str) -> tuple[int, int]:
    values = tuple(int(item) for item in value.split(":"))
    if len(values) != 2:
        raise argparse.ArgumentTypeError("reaction pair must be INDEX:INDEX")
    return values


def _interval(value: str) -> tuple[float, float]:
    values = tuple(float(item) for item in value.split(":"))
    if len(values) != 2 or values[0] >= values[1]:
        raise argparse.ArgumentTypeError("important interval must be LOW:HIGH")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NEB path-quality evidence; this CLI cannot authorize actions.")
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--reaction-pair", type=_pair, required=True)
    parser.add_argument("--important-interval", type=_interval, required=True)
    parser.add_argument("--monitor-evidence", type=Path)
    parser.add_argument("--thresholds", type=Path, default=ROOT / "configs" / "neb_path_quality_control_v2.yaml")
    parser.add_argument(
        "--geometry-thresholds",
        type=Path,
        default=ROOT / "configs" / "neb_agent" / "default_thresholds.yaml",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = build_path_quality_report(
            PathQualityRequest(
                workdir=args.workdir,
                reaction_pair=args.reaction_pair,
                important_interval=args.important_interval,
                quality_thresholds=args.thresholds,
                geometry_thresholds=args.geometry_thresholds,
                monitor_evidence=args.monitor_evidence,
            )
        )
        write_json(args.output or args.workdir / "neb_path_quality.json", report)
    except (KeyError, OSError, ValueError) as exc:
        print(f"path-quality error: {exc}", file=sys.stderr)
        return 1
    print(report["PATH_QUALITY_STATUS"])
    return 0


def _incar_nelm(path: Path) -> int:
    return read_configured_nelm(path)


if __name__ == "__main__":
    raise SystemExit(main())
