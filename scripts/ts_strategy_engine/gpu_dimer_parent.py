"""Validate reviewed GPU paths as Dimer seeds, without claiming DFT validation."""
from __future__ import annotations

from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file
from scripts.dual_model_ml_neb import _load_request
from scripts.ml_candidate_source import load_candidate_path
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.dimer_gate_common import load_policy

PARENT_METHOD = "gpu_ml_neb_reviewed_path"


def _bound(evidence, name):
    binding = evidence[name]
    path = Path(binding["path"])
    if not path.is_file() or sha256_file(path) != binding["sha256"]:
        raise ValueError(f"GPU Dimer source changed: {name}")
    return path


def validate_reviewed_gpu_parent(analysis, *, image_paths=None, policy=None):
    """Re-read the entire source and review; booleans alone never authorize entry."""
    checks = {}
    try:
        rule = (policy or load_policy())["gpu_reviewed_path"]
        evidence = analysis["gpu_reviewed_path_evidence"]
        request_path = _bound(evidence, "request")
        manifest_path = _bound(evidence, "manifest")
        review_path = _bound(evidence, "review")
        contract_path = _bound(evidence, "contract")
        contract = load_contract(contract_path)
        request = _load_request(request_path)
        manifest = load_json_object(manifest_path)
        review = load_json_object(review_path)
        checks["gpu_source_model_reaction_bound"] = bool(
            manifest.get("document_kind") == "dual_model_gpu_ml_neb_path_manifest"
            and manifest.get("source_request", {}).get("sha256") == sha256_file(request_path)
            and manifest.get("models") == request["models"]
            and manifest.get("reaction") == request["reaction"]
        )
        fields = ("contract_sha256", "atom_map_sha256", "compatibility_sha256")
        checks["gpu_contract_bound"] = all(
            analysis.get(key) == request["reaction"].get(key) == contract[key]
            for key in fields
        )
        atoms, rows = load_candidate_path(
            request, manifest, manifest_path, request_path, method="ml_neb", minimum_images=3,
        )
        checks["gpu_complete_path_geometry_valid"] = len(atoms) == len(rows)
        checks["gpu_path_review_accepted"] = bool(
            review.get("document_kind") == rule["review_document_kind"]
            and review.get("status") == rule["accepted_status"]
            and review.get("candidate_manifest_sha256") == sha256_file(manifest_path)
            and review.get("policy_sha256") == analysis.get("dimer_gate_policy_sha256")
            and review.get("reviewer") and review.get("reviewed_at")
            and review.get("target_reaction_event")
            and all(review.get(key) == "accepted" for key in rule["required_reviews"])
            and review.get("reaction_atom_indices_zero_based") == contract["reaction_atoms"]
        )
        # Reviewed numerical/visual artifacts remain immutable dependencies.
        for key in ("geometry", "movie", "dist"):
            _bound(review["evidence"], key)
        peak = str(review["candidate_image"])
        index = next((i for i, row in enumerate(rows) if row["image"] == peak), -1)
        checks["gpu_reviewed_internal_candidate"] = bool(
            0 < index < len(rows) - 1 and analysis.get("maximum_image") == peak
        )
        if not checks["gpu_reviewed_internal_candidate"]:
            raise ValueError("reviewed candidate must have two adjacent path images")
        selected = rows[index - 1:index + 2]
        if image_paths is not None:
            checks["gpu_exact_reviewed_triad"] = bool(
                len(image_paths) == 3 and all(
                    sha256_file(path) == row["sha256"]
                    for path, row in zip(image_paths, selected)
                )
            )
        checks["gpu_live_policy_bound"] = (
            analysis.get("dimer_gate_policy_sha256") == sha256_file(Path(
                analysis["dimer_gate_policy_file"]
            ))
            and load_policy(Path(analysis["dimer_gate_policy_file"])) == (policy or load_policy())
        )
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        return {"passed": False, "checks": checks, "errors": [f"gpu_reviewed_path:{exc}"]}
    return {
        "passed": all(checks.values()), "checks": checks,
        "errors": [key for key, passed in checks.items() if not passed],
        "role": rule["role"], "vasp_triad_required": False,
    }
