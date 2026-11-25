from __future__ import annotations

import argparse
from pathlib import Path

from scripts.artifact_io import load_json_object, write_json

from .execution_evidence import load_bound_evidence
from .execution_gate import decide_execution


def build_decision(request_path: Path, output: Path) -> dict:
    request = load_json_object(request_path)
    required = (
        "geometry_file",
        "analysis_file",
        "thresholds_file",
        "climb",
        "path_reviewed",
    )
    missing = [field for field in required if field not in request]
    if missing:
        raise ValueError("gate request missing: " + ", ".join(missing))
    if any(name in request for name in ("geometry", "analysis", "thresholds")):
        raise ValueError("core gate evidence must be loaded from bound source files")

    source_bindings: dict[str, dict[str, str]] = {}

    decision = decide_execution(
        load_bound_evidence(request_path, request, "geometry", source_bindings, required=True),
        load_bound_evidence(request_path, request, "analysis", source_bindings, required=True),
        load_bound_evidence(request_path, request, "thresholds", source_bindings, required=True),
        climb=request["climb"],
        path_reviewed=request["path_reviewed"],
        path_quality=load_bound_evidence(request_path, request, "path_quality", source_bindings),
        preflight=load_bound_evidence(request_path, request, "preflight", source_bindings),
        validation=load_bound_evidence(request_path, request, "validation", source_bindings),
        scheduler=load_bound_evidence(request_path, request, "scheduler", source_bindings),
        authorization=load_bound_evidence(request_path, request, "authorization", source_bindings),
        source_bindings=source_bindings,
    )
    write_json(output, decision)
    return decision


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one authoritative NEB execution decision.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build_decision(args.request, args.output)["DECISION"])


if __name__ == "__main__":
    main()
