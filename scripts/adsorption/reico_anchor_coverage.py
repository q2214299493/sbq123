"""Compare audited low-force anchors against the frozen random training subset."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.metadata
import json
from pathlib import Path

from scripts.adsorption.reico_environment_audit import describe, frame_scores, nearest, read_geometry, stack
from scripts.artifact_io import sha256_json, source_file_manifest, source_file_manifest_valid, write_json_exclusive


def run(root: Path) -> dict:
    from dscribe.descriptors import SOAP

    summary = json.loads((root / "audit_summary.json").read_text(encoding="utf-8"))
    if not source_file_manifest_valid(summary):
        raise ValueError("source-bound audit is stale")
    config = summary["config"]
    plan = json.loads((root / "supplement_plan.json").read_text(encoding="utf-8"))
    coverage = json.loads((root / "coverage.json").read_text(encoding="utf-8"))
    selection = json.loads(Path(config["selection"]).read_text(encoding="utf-8"))["selected"]
    selected = [row for row in selection if row["partition"] == "train"]
    soap = SOAP(**config["soap"])
    binding = {"soap": config["soap"], "near_Fe_A": config["near_Fe_A"], "dscribe": importlib.metadata.version("dscribe")}
    cache = root / "descriptor_cache" / sha256_json(binding)
    reference = [describe(row, read_geometry(row), soap, cache, config["near_Fe_A"]) for row in selected]
    anchors = [{**row, "family_id": row["calculation_group"], "composition": row["formula"]}
               for row in plan["low_force_anchor_candidates"]]
    descriptions = [describe(row, read_geometry(row), soap, cache, config["near_Fe_A"]) for row in anchors]
    scores = []
    if descriptions:
        pool = stack(descriptions)
        scores = frame_scores(descriptions, pool, nearest(pool, stack(reference)), coverage["thresholds"])
    origins = Counter("random_initial_without_ML" if row["step"] == 0 else "ML_trajectory" for row in selected)
    result = {"document_kind": "anchor_coverage_and_sampling_origin_diagnostic", "anchors": scores,
              "anchors_above_random_pool_internal_threshold": sum(row["exceeds_internal_threshold"] for row in scores),
              "selected_training_sampling_origins": dict(origins),
              "interpretation": "Anchor distance is geometry only. Low DFT force comes from the separate audited training labels; no model precision or stability proof.",
              "source_files": source_file_manifest([root / "audit_summary.json", root / "supplement_plan.json",
                                                     root / "coverage.json", Path(__file__)]),
              "reserved_forces_or_energies_used": False, "new_DFT_or_GPU": False}
    write_json_exclusive(root / "anchor_coverage.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.audit)
    print(json.dumps({"anchors": len(result["anchors"]), "above_internal_threshold": result["anchors_above_random_pool_internal_threshold"],
                      "sampling_origins": result["selected_training_sampling_origins"]}))
