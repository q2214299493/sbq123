from __future__ import annotations

import argparse
from pathlib import Path

from .cli_common import add_common_arguments
from .utils_report import write_json
from .utils_retrieval import find_retrieval_file, read_retrieval_source


def normalize_retrieval_prior(source: dict, path: Path | None, surface_family: str, material: str) -> tuple[dict, dict]:
    results = source.get("results", []) if source else []
    best = results[0].get("record", {}) if results else {}
    confidence = str(best.get("match_confidence", "none")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "none"
    available = bool(path and results and source.get("whitelist_valid"))
    production_ready = bool(source.get("production_ready")) if source else False
    source_access_verified = bool(best.get("source_access_verified"))
    use = available and production_ready and source_access_verified and confidence in {"high", "medium"}
    method = "segmented_idpp" if confidence == "high" else "constrained_idpp" if confidence == "medium" else "idpp"
    prior = {
        "available": available,
        "source_path": str(path) if path else None,
        "whitelist_valid": bool(source.get("whitelist_valid")) if source else False,
        "production_ready": production_ready,
        "best_source_access_verified": source_access_verified,
        "semantic_backend": source.get("semantic_backend") if source else None,
        "target_system": {"surface_family": surface_family, "material": material},
        "overall_confidence": confidence,
        "matched_records": [
            {
                "rank": item.get("rank"),
                "id": item.get("record", {}).get("id"),
                "source_id": item.get("record", {}).get("source_id"),
                "source_url": item.get("record", {}).get("source_url"),
                "hybrid_score": item.get("hybrid_score"),
            }
            for item in results
        ],
        "warnings": [] if use else ["No high/medium, access-verified, production-ready whitelist match was accepted as a path constraint."],
    }
    constraints = {
        "use_retrieval_prior": use,
        "confidence": confidence,
        "recommended_path_method": method,
        "reaction_coordinate": best.get("reaction_coordinate", {}),
        "suggested_midpoints": best.get("suggested_midpoints", []),
        "likely_intermediate": best.get("likely_intermediate", {"exists": "Needs confirmation"}),
        "expected_barrier_range_eV": best.get("expected_barrier_range_eV"),
        "do_not_do": list(best.get("do_not_do", [])),
        "retrieval_record_id": best.get("id"),
        "retrieval_source_url": best.get("source_url"),
        "requires_scientific_review": True,
        "review_status": "needs_review",
    }
    return prior, constraints


def main() -> None:
    parser = argparse.ArgumentParser(description="Adapt whitelist Top-5 retrieval output into reviewable NEB path constraints.")
    add_common_arguments(parser)
    parser.add_argument("--retrieval-file", type=Path)
    args = parser.parse_args()
    source_path = args.retrieval_file or find_retrieval_file(args.workdir)
    if source_path is not None and not source_path.is_file():
        raise SystemExit(f"retrieval file not found: {source_path}")
    source = read_retrieval_source(source_path) if source_path else {}
    prior, constraints = normalize_retrieval_prior(source, source_path, args.surface_family, args.material)
    write_json(args.workdir / "retrieval_prior.json", prior)
    write_json(args.workdir / "retrieval_path_constraints.json", constraints)
    print(args.workdir / "retrieval_prior.json")


if __name__ == "__main__":
    main()
