#!/usr/bin/env python3
"""Run authorized MatRIS inference on a frozen, disjoint TS held-out set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic
from scripts.matris_energy_force_finetune import (
    _force_metrics,
    _prediction_record,
    _relative_energy_metrics,
    validate_review_package,
)
from scripts.matris_finetune_speed_benchmark import load_model


AUTHORIZATION_KIND = "matris_frozen_ts_heldout_validation_authorization"


def _verify_bound(reference: dict[str, Any], *, name: str) -> Path:
    path = Path(str(reference.get("path", ""))).resolve()
    expected = str(reference.get("sha256", ""))
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{name} binding failed")
    return path


def run(args: argparse.Namespace) -> dict[str, Any]:
    import torch

    authorization_path = args.authorization.resolve()
    authorization = load_json_object(authorization_path)
    if authorization.get("document_kind") != AUTHORIZATION_KIND:
        raise ValueError("invalid held-out validation authorization")
    if authorization.get("execution_authorized") is not True:
        raise ValueError("held-out validation is not authorized")
    if authorization.get("training_authorized") is not False:
        raise ValueError("held-out validation authorization must forbid training")
    if authorization.get("checkpoint_promotion_authorized") is not False:
        raise ValueError("held-out validation authorization must forbid promotion")
    review_path = _verify_bound(
        authorization.get("review_request", {}), name="fine-tune review request"
    )
    reclassification_path = _verify_bound(
        authorization.get("reclassification_review", {}),
        name="tiered-gate reclassification review",
    )
    candidate_path = _verify_bound(
        authorization.get("candidate_checkpoint", {}), name="candidate checkpoint"
    )
    base_path = _verify_bound(
        authorization.get("base_checkpoint", {}), name="base checkpoint"
    )
    if sha256_file(candidate_path) == sha256_file(base_path):
        raise ValueError("candidate checkpoint is identical to the base checkpoint")

    context = validate_review_package(review_path)
    primary = [
        sample
        for sample in context["heldout_validation_samples"]
        if sample.get("primary_metric_eligible") is True
    ]
    diagnostic = [
        sample
        for sample in context["heldout_validation_samples"]
        if sample.get("primary_metric_eligible") is not True
    ]
    expected = authorization.get("expected_counts", {})
    if len(primary) != int(expected.get("primary", -1)):
        raise ValueError("primary held-out count mismatch")
    if len(diagnostic) != int(expected.get("diagnostic", -1)):
        raise ValueError("diagnostic held-out count mismatch")

    base_model, _, _ = load_model(base_path, args.device)
    base_primary = [_prediction_record(base_model, sample, args.device) for sample in primary]
    base_diagnostic = [
        _prediction_record(base_model, sample, args.device) for sample in diagnostic
    ]
    del base_model
    if args.device.startswith("cuda"):
        torch.cuda.empty_cache()

    candidate_model, _, _ = load_model(candidate_path, args.device)
    parameters = list(candidate_model.parameters())
    all_parameters_finite = all(bool(torch.isfinite(value).all()) for value in parameters)
    if not all_parameters_finite:
        raise RuntimeError("candidate checkpoint contains non-finite parameters")
    candidate_primary = [
        _prediction_record(candidate_model, sample, args.device) for sample in primary
    ]
    candidate_diagnostic = [
        _prediction_record(candidate_model, sample, args.device) for sample in diagnostic
    ]

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "document_kind": "matris_frozen_ts_heldout_validation_result",
        "status": "completed_needs_work_review_no_promotion",
        "authorization": {
            "path": str(authorization_path),
            "sha256": sha256_file(authorization_path),
        },
        "review_request": {
            "path": str(review_path),
            "sha256": sha256_file(review_path),
        },
        "reclassification_review": {
            "path": str(reclassification_path),
            "sha256": sha256_file(reclassification_path),
        },
        "base_checkpoint_sha256": sha256_file(base_path),
        "candidate_checkpoint": {
            "path": str(candidate_path),
            "sha256": sha256_file(candidate_path),
            "strict_reload_passed": True,
            "parameter_count": sum(value.numel() for value in parameters),
            "all_parameters_finite": all_parameters_finite,
        },
        "frozen_ts_heldout": {
            "primary_sample_count": len(primary),
            "diagnostic_sample_count": len(diagnostic),
            "base_force": _force_metrics(base_primary),
            "candidate_force": _force_metrics(candidate_primary),
            "base_relative_energy": _relative_energy_metrics(base_primary),
            "candidate_relative_energy": _relative_energy_metrics(candidate_primary),
            "diagnostic_base_force": _force_metrics(base_diagnostic),
            "diagnostic_candidate_force": _force_metrics(candidate_diagnostic),
            "base_primary_predictions": base_primary,
            "candidate_primary_predictions": candidate_primary,
            "base_diagnostic_predictions": base_diagnostic,
            "candidate_diagnostic_predictions": candidate_diagnostic,
        },
        "training_performed": False,
        "checkpoint_modified": False,
        "checkpoint_promotion_authorized": False,
        "complete_path_rerun_authorized": False,
    }
    write_json_atomic(output / "result.json", result, ensure_ascii=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    result = run(args)
    summary = {
        "status": result["status"],
        "candidate_checkpoint_sha256": result["candidate_checkpoint"]["sha256"],
        "primary_sample_count": result["frozen_ts_heldout"]["primary_sample_count"],
        "base_vector_rmse_eV_per_A": result["frozen_ts_heldout"]["base_force"][
            "vector_rmse_eV_per_A"
        ],
        "candidate_vector_rmse_eV_per_A": result["frozen_ts_heldout"][
            "candidate_force"
        ]["vector_rmse_eV_per_A"],
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
