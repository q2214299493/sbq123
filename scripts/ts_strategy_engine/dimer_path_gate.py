from __future__ import annotations

from pathlib import Path

from typing import Any

from scripts.artifact_io import sha256_file

from scripts.ts_strategy_engine.ml_neb_path import validate_gpu_ml_neb_path_manifest

from .dimer_gate_common import load_policy

from .dimer_gate_common import _at_most, _finite, _sha256

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_POLICY = ROOT / "configs" / "dimer_gate.yaml"

def _evaluate_gpu_ml_neb_parent(
    analysis: dict[str, Any],
    image_names: tuple[str, str, str],
    image_paths: tuple[Path, Path, Path],
    triad_rows: list[dict[str, Any] | None],
    policy: dict[str, Any],
    analysis_root: Path | None,
) -> dict[str, Any]:
    rule = policy["gpu_ml_neb_parent"]
    evidence = analysis.get("gpu_ml_neb_parent_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    manifest: dict[str, Any] = {}
    manifest_path: Path | None = None
    manifest_hash_bound = False
    manifest_ref = evidence.get("path_manifest_file")
    if isinstance(manifest_ref, str) and manifest_ref.strip() and analysis_root is not None:
        candidate = Path(manifest_ref)
        manifest_path = candidate if candidate.is_absolute() else analysis_root / candidate
        try:
            manifest = validate_gpu_ml_neb_path_manifest(manifest_path, require_accepted=True)
            manifest_hash_bound = bool(
                _sha256(evidence.get("path_manifest_sha256"))
                and evidence.get("path_manifest_sha256") == sha256_file(manifest_path)
            )
        except (OSError, ValueError):
            manifest = {}

    images = manifest.get("images")
    images = images if isinstance(images, list) else []
    manifest_rows = {
        str(row.get("image")): row
        for row in images
        if isinstance(row, dict) and row.get("image") is not None
    }
    required_image_scalars = (
        "predicted_energy_eV",
        "predicted_physical_force_max_eVA",
        "projected_neb_force_max_eVA",
        "spring_force_max_eVA",
        "reaction_coordinate_value",
    )
    complete_images = bool(
        len(images) >= 3
        and len(manifest_rows) == len(images)
        and all(
            _sha256(row.get("structure_sha256"))
            and all(_finite(row.get(field)) for field in required_image_scalars)
            for row in manifest_rows.values()
        )
    )
    adjacent_rmsd = manifest.get("adjacent_rmsd_A")
    adjacent_rmsd_complete = bool(
        isinstance(adjacent_rmsd, list)
        and len(adjacent_rmsd) == max(0, len(images) - 1)
        and all(_finite(value) for value in adjacent_rmsd)
    )
    review = manifest.get("path_review")
    review = review if isinstance(review, dict) else {}
    accepted_review = str(rule["accepted_path_review_status"])
    path_reviews_accepted = all(
        review.get(field) == accepted_review
        for field in (
            "geometry_continuity",
            "periodic_mapping",
            "reaction_coordinate_resolution",
            "elementary_step_assignment",
        )
    )
    checkpoint_hash = manifest.get("checkpoint_sha256")
    contract_bound = all(
        _sha256(manifest.get(field)) and manifest.get(field) == analysis.get(field)
        for field in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")
    )
    triad_hashes = [sha256_file(path) for path in image_paths]
    manifest_triad_bound = all(
        manifest_rows.get(name, {}).get("structure_sha256") == digest
        for name, digest in zip(image_names, triad_hashes)
    )
    dft_fingerprints = [
        row.get("dft_fingerprint_sha256") if isinstance(row, dict) else None
        for row in triad_rows
    ]
    exact_vasp_triad = bool(
        all(
            row
            and row.get("structure_sha256") == digest
            and row.get("force_source") == rule["vasp_force_source"]
            and row.get("scheduler_evidence_accepted") is True
            for row, digest in zip(triad_rows, triad_hashes)
        )
    )
    compatible_dft = bool(
        len(dft_fingerprints) == 3
        and all(_sha256(value) for value in dft_fingerprints)
        and len(set(dft_fingerprints)) == 1
    )
    agreement = evidence.get("force_agreement")
    agreement = agreement if isinstance(agreement, dict) else {}
    thresholds = rule["local_force_agreement"]
    agreement_bound = bool(
        _sha256(agreement.get("comparison_sha256"))
        and agreement.get("checkpoint_sha256") == checkpoint_hash
        and agreement.get("structure_sha256") == triad_hashes
    )
    agreement_passed = bool(
        agreement_bound
        and _at_most(agreement.get("component_mae_eV_per_A"), thresholds["component_mae_eV_per_A_max"])
        and _at_most(agreement.get("vector_rmse_eV_per_A"), thresholds["vector_rmse_eV_per_A_max"])
        and _at_most(agreement.get("vector_max_eV_per_A"), thresholds["vector_max_eV_per_A_max"])
    )
    reliability_route = evidence.get("reliability_route")
    calibrated_domain_bound = bool(
        _sha256(evidence.get("ts_domain_validation_sha256"))
        and evidence.get("ts_domain_checkpoint_sha256") == checkpoint_hash
        and evidence.get("ts_domain_gate_passed") is True
    )
    reliability_accepted = bool(
        reliability_route in set(rule["accepted_reliability_routes"])
        and (
            reliability_route == "exact_vasp_triad_force_agreement" and agreement_passed
            or reliability_route == "calibrated_ts_domain" and calibrated_domain_bound
        )
    )
    checks = {
        "gpu_path_manifest_hash_bound": manifest_hash_bound,
        "gpu_path_manifest_complete": bool(
            manifest.get("document_kind") == rule["manifest_document_kind"]
            and manifest.get("status") == rule["accepted_status"]
            and complete_images
            and adjacent_rmsd_complete
        ),
        "gpu_checkpoint_hash_bound": _sha256(checkpoint_hash),
        "gpu_path_contract_bound": contract_bound,
        "gpu_path_reviews_accepted": path_reviews_accepted,
        "gpu_candidate_triad_hash_bound": manifest_triad_bound,
        "gpu_vasp_triad_exact_structure_force_labels": exact_vasp_triad,
        "gpu_vasp_triad_compatible_dft": compatible_dft,
        "gpu_model_reliability_route_accepted": reliability_accepted,
    }
    return {
        "checks": checks,
        "path_manifest_file": str(manifest_path) if manifest_path else None,
        "path_manifest_sha256": evidence.get("path_manifest_sha256"),
        "checkpoint_sha256": checkpoint_hash,
        "reliability_route": reliability_route,
        "local_force_agreement_passed": agreement_passed,
        "local_force_agreement_role": thresholds["role"],
    }

def coarse_neb_peak_stall_evidence(
    analysis: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_policy = policy or load_policy()
    rule = active_policy["coarse_neb_peak_stall"]
    rows = [row for row in analysis.get("images", []) if isinstance(row, dict)]
    maximum_image = str(analysis.get("maximum_image", ""))
    maximum_index = next(
        (index for index, row in enumerate(rows) if str(row.get("image")) == maximum_image),
        None,
    )
    internal_peak = bool(
        maximum_index is not None
        and 0 < maximum_index < len(rows) - 1
        and analysis.get("internal_maximum")
    )
    peak = rows[maximum_index] if maximum_index is not None else {}
    other_internal = [
        row
        for index, row in enumerate(rows[1:-1], start=1)
        if index != maximum_index
    ]
    other_forces = [row.get("final_neb_force_eVA") for row in other_internal]
    other_images_stable = bool(
        other_internal
        and all(
            _finite(value)
            and float(value) <= float(rule["other_internal_image_force_max_eVA"])
            for value in other_forces
        )
    )
    peak_force = peak.get("final_neb_force_eVA")
    peak_stalled = bool(
        _finite(peak_force)
        and float(peak_force) >= float(rule["stalled_peak_force_min_eVA"])
        and int(peak.get("ionic_steps") or 0) >= int(rule["minimum_peak_ionic_steps"])
        and peak.get("neb_force_trend") in set(rule["stalled_force_trends"])
        and not peak.get("reached_required_accuracy")
    )
    checks = {
        "highest_energy_image_is_internal": internal_peak,
        "at_least_one_other_internal_image_is_stable": other_images_stable,
        "highest_energy_image_is_persistently_stalled": peak_stalled,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "maximum_image": maximum_image or None,
        "peak_force_eVA": peak_force,
        "peak_force_trend": peak.get("neb_force_trend"),
        "peak_ionic_steps": peak.get("ionic_steps"),
        "other_internal_forces_eVA": other_forces,
    }
