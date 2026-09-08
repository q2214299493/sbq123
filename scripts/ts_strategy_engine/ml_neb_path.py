from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file, write_json_atomic


REVIEW_FIELDS = (
    "geometry_continuity",
    "periodic_mapping",
    "reaction_coordinate_resolution",
    "elementary_step_assignment",
)


def validate_gpu_ml_neb_path_manifest(
    manifest_path: Path,
    *,
    require_accepted: bool = False,
) -> dict[str, Any]:
    manifest = load_json_object(manifest_path)
    errors: list[str] = []
    if manifest.get("document_kind") != "gpu_ml_neb_path_manifest":
        errors.append("document_kind")
    allowed_status = {"needs_work_review", "accepted_for_vasp_validated_dimer_parent"}
    if manifest.get("status") not in allowed_status:
        errors.append("status")
    if require_accepted and manifest.get("status") != "accepted_for_vasp_validated_dimer_parent":
        errors.append("accepted_status")
    _validate_bindings(manifest, manifest_path, errors)
    _validate_images(manifest, manifest_path, errors)
    restrictions = manifest.get("restrictions")
    if not isinstance(restrictions, dict) or not (
        restrictions.get("predicted_candidate_only") is True
        and restrictions.get("reportable_dft") is False
        and restrictions.get("automatic_vasp_submission") is False
    ):
        errors.append("restrictions")
    _validate_producer(manifest, manifest_path, errors)
    if require_accepted:
        _validate_accepted(manifest, manifest_path, restrictions, errors)
    if errors:
        raise ValueError("invalid GPU ML-NEB path manifest: " + ", ".join(sorted(set(errors))))
    return manifest


def _validate_bindings(manifest: dict[str, Any], manifest_path: Path, errors: list[str]) -> None:
    for field in (
        "checkpoint_sha256",
        "runner_sha256",
        "contract_sha256",
        "atom_map_sha256",
        "compatibility_sha256",
    ):
        if not _sha256(manifest.get(field)):
            errors.append(field)
    if not manifest.get("model_identifier") or not isinstance(manifest.get("run_settings"), dict):
        errors.append("model_and_run_settings")
    source_ref = manifest.get("source_handoff")
    source_ref = source_ref if isinstance(source_ref, dict) else {}
    source_path = manifest_path.parent / str(source_ref.get("path", ""))
    if not source_path.is_file() or source_ref.get("sha256") != sha256_file(source_path):
        errors.append("source_handoff_hash")


def _validate_images(manifest: dict[str, Any], manifest_path: Path, errors: list[str]) -> list[dict[str, Any]]:
    raw_images = manifest.get("images")
    images = [row for row in raw_images if isinstance(row, dict)] if isinstance(raw_images, list) else []
    if not isinstance(raw_images, list) or len(images) != len(raw_images) or len(images) < 3:
        errors.append("images")
    for row in images:
        _validate_image_row(row, manifest_path, errors)
    names = [str(row.get("image", "")) for row in images]
    if names != [f"{index:02d}" for index in range(len(images))]:
        errors.append("image_sequence")
    adjacent = manifest.get("adjacent_rmsd_A")
    if not isinstance(adjacent, list) or len(adjacent) != max(0, len(images) - 1) or not all(
        _finite(value) for value in adjacent
    ):
        errors.append("adjacent_rmsd_A")
    return images


def _validate_image_row(row: dict[str, Any], manifest_path: Path, errors: list[str]) -> None:
    name = str(row.get("image", ""))
    structure_ref = row.get("structure_path")
    structure = manifest_path.parent / str(structure_ref or "")
    if not structure_ref or not structure.is_file() or row.get("structure_sha256") != sha256_file(structure):
        errors.append(f"image_{name}_structure_hash")
    for field in (
        "predicted_energy_eV",
        "predicted_physical_force_max_eVA",
        "projected_neb_force_max_eVA",
        "spring_force_max_eVA",
        "reaction_coordinate_value",
        "minimum_pair_distance_A",
    ):
        if not _finite(row.get(field)):
            errors.append(f"image_{name}_{field}")
    if not isinstance(row.get("key_bond_distances_A"), dict) or not row["key_bond_distances_A"]:
        errors.append(f"image_{name}_key_bonds")


def _validate_producer(manifest: dict[str, Any], manifest_path: Path, errors: list[str]) -> None:
    producer = manifest.get("producer")
    exit_ref = manifest.get("producer_exit_record")
    exit_ref = exit_ref if isinstance(exit_ref, dict) else {}
    exit_path = manifest_path.parent / str(exit_ref.get("path", ""))
    if not isinstance(producer, dict) or producer.get("backend") != "aqcat_gpu":
        errors.append("producer")
    if not exit_path.is_file() or exit_ref.get("sha256") != sha256_file(exit_path):
        errors.append("producer_exit_record_hash")
        return
    exit_record = load_json_object(exit_path)
    if not (
        exit_ref.get("status") == "success"
        and exit_ref.get("exit_code") == 0
        and exit_record.get("status") == "success"
        and exit_record.get("exit_code") == 0
        and isinstance(producer, dict)
        and exit_record.get("gpu_job_id") == producer.get("gpu_job_id")
    ):
        errors.append("producer_exit_record_content")


def _validate_accepted(
    manifest: dict[str, Any], manifest_path: Path, restrictions: Any, errors: list[str]
) -> None:
    review = manifest.get("path_review")
    if not isinstance(review, dict) or any(review.get(field) != "accepted" for field in REVIEW_FIELDS):
        errors.append("accepted_path_review")
    numeric = review.get("numeric_screen", {}) if isinstance(review, dict) else {}
    if any(
        numeric.get(field) is not True
        for field in (
            "adjacent_rmsd_passed",
            "periodic_branch_numeric_passed",
            "minimum_pair_distance_passed",
            "single_strict_internal_peak",
        )
    ):
        errors.append("accepted_numeric_path_screen")
    if not _sha256(manifest.get("source_candidate_manifest_sha256")) or not _sha256(
        manifest.get("path_review_sha256")
    ):
        errors.append("accepted_review_hash_binding")
    candidate_file = manifest.get("source_candidate_manifest_file")
    review_file = manifest.get("path_review_file")
    if not candidate_file or not review_file:
        errors.append("accepted_review_file_binding")
    else:
        candidate_path = manifest_path.parent / str(candidate_file)
        review_path = manifest_path.parent / str(review_file)
        if not candidate_path.is_file() or sha256_file(candidate_path) != manifest.get(
            "source_candidate_manifest_sha256"
        ):
            errors.append("source_candidate_manifest_file_hash")
        if not review_path.is_file() or sha256_file(review_path) != manifest.get("path_review_sha256"):
            errors.append("path_review_file_hash")
    if not isinstance(restrictions, dict) or restrictions.get("dimer_parent_accepted") is not True:
        errors.append("dimer_parent_accepted")


def finalize_gpu_ml_neb_path_manifest(
    candidate_path: Path,
    review_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.parent.resolve() != candidate_path.parent.resolve() or review_path.parent.resolve() != candidate_path.parent.resolve():
        raise ValueError("accepted path manifest, candidate, review, and image tree must stay together")
    if output_path.exists():
        raise FileExistsError(f"accepted path manifest already exists: {output_path}")
    candidate = validate_gpu_ml_neb_path_manifest(candidate_path)
    if candidate.get("status") != "needs_work_review":
        raise ValueError("only a needs_work_review candidate manifest can be finalized")
    review = load_json_object(review_path)
    required = {
        "document_kind": "gpu_ml_neb_path_review",
        "status": "accepted",
        "candidate_manifest_sha256": sha256_file(candidate_path),
    }
    for key, expected in required.items():
        if review.get(key) != expected:
            raise ValueError(f"GPU ML-NEB path review does not bind {key}")
    if not review.get("reviewer") or not review.get("reviewed_at"):
        raise ValueError("GPU ML-NEB path review requires reviewer and reviewed_at")
    if any(review.get(field) != "accepted" for field in REVIEW_FIELDS):
        raise ValueError("GPU ML-NEB path review has an unaccepted hard field")
    image_names = {row["image"] for row in candidate["images"]}
    if review.get("candidate_peak_image") not in image_names - {"00", f"{len(image_names) - 1:02d}"}:
        raise ValueError("reviewed candidate peak is not an internal path image")
    expected_peak = max(candidate["images"][1:-1], key=lambda row: row["predicted_energy_eV"])["image"]
    if review["candidate_peak_image"] != expected_peak:
        raise ValueError("reviewed candidate peak does not match the manifest energy maximum")
    numeric = candidate.get("path_review", {}).get("numeric_screen", {})
    required_numeric = (
        "adjacent_rmsd_passed",
        "periodic_branch_numeric_passed",
        "minimum_pair_distance_passed",
        "single_strict_internal_peak",
    )
    if any(numeric.get(field) is not True for field in required_numeric):
        raise ValueError("GPU ML-NEB numeric path screen is not eligible for Dimer-parent finalization")

    accepted = dict(candidate)
    accepted["status"] = "accepted_for_vasp_validated_dimer_parent"
    accepted["source_candidate_manifest_sha256"] = sha256_file(candidate_path)
    accepted["path_review_sha256"] = sha256_file(review_path)
    accepted["source_candidate_manifest_file"] = candidate_path.name
    accepted["path_review_file"] = review_path.name
    accepted["path_review"] = {
        **candidate["path_review"],
        **{field: "accepted" for field in REVIEW_FIELDS},
        "reviewer": review["reviewer"],
        "reviewed_at": review["reviewed_at"],
        "candidate_peak_image": review["candidate_peak_image"],
        "review_file": review_path.name,
    }
    accepted["restrictions"] = {**candidate["restrictions"], "dimer_parent_accepted": True}
    write_json_atomic(output_path, accepted, ensure_ascii=True)
    return validate_gpu_ml_neb_path_manifest(output_path, require_accepted=True)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )
