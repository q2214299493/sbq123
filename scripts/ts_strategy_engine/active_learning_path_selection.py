from __future__ import annotations

import math

from pathlib import Path

from typing import Any

from scripts.aqcat25_calibration import parse_poscar_symbols

from scripts.aqcat25_handoff import atom_order_sha256

from scripts.artifact_io import sha256_file

from .active_learning_common import (
    read_json,
)

from .ml_neb_path import validate_gpu_ml_neb_path_manifest

from .active_learning_path_common import _resolve, _source_handoff


def _load_committee_assessment(
    assessment_path: Path | None,
    *,
    path_manifest_path: Path,
    path_manifest: dict[str, Any],
) -> dict[str, Any] | None:
    if assessment_path is None:
        return None
    assessment = read_json(assessment_path)
    if assessment.get("document_kind") != "aqcat25_ml_path_committee_assessment":
        raise ValueError("invalid path committee assessment kind")
    if assessment.get("source_path_manifest_sha256") != sha256_file(path_manifest_path):
        raise ValueError("committee assessment is not bound to the ML path manifest")
    if assessment.get("primary_checkpoint_sha256") != path_manifest["checkpoint_sha256"]:
        raise ValueError("committee assessment primary checkpoint mismatch")
    members = assessment.get("members")
    member_hashes = {
        str(row.get("checkpoint_sha256", "")) for row in members if isinstance(row, dict)
    } if isinstance(members, list) else set()
    if len(member_hashes) < 3 or any(len(value) != 64 for value in member_hashes):
        raise ValueError("committee assessment requires at least three unique checkpoints")
    image_names = {row["image"] for row in path_manifest["images"]}
    rows = assessment.get("images")
    if not isinstance(rows, list) or {row.get("image") for row in rows} != image_names:
        raise ValueError("committee assessment image set mismatch")
    for row in rows:
        for field in (
            "energy_std_eV",
            "force_component_std_rms_eV_per_A",
            "force_vector_std_max_eV_per_A",
        ):
            value = row.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"invalid committee disagreement field: {field}")
    return assessment

def _select_path_images(
    manifest: dict[str, Any],
    policy: dict[str, Any],
    committee: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    images = manifest["images"]
    internal = images[1:-1]
    if not internal:
        raise ValueError("ML path has no internal images")
    peak = max(internal, key=lambda row: float(row["predicted_energy_eV"]))
    peak_index = int(peak["image"])
    configured = policy.get("path_label_selection", {})
    maximum = int(configured.get("maximum_labels_per_round", 7))
    minimum = int(configured.get("minimum_labels_per_round", 3))
    if minimum < 3 or maximum < minimum:
        raise ValueError("invalid path label selection limits")
    reasons: dict[int, set[str]] = {}

    def add(index: int, reason: str) -> None:
        if 0 < index < len(images) - 1:
            reasons.setdefault(index, set()).add(reason)

    add(peak_index, "highest_predicted_energy")
    add(peak_index - 1, "peak_left_neighbor")
    add(peak_index + 1, "peak_right_neighbor")
    if peak_index > 1:
        add(max(1, peak_index // 2), "rising_path_representative")
    if peak_index < len(images) - 2:
        add(
            min(len(images) - 2, peak_index + (len(images) - 1 - peak_index) // 2),
            "falling_path_representative",
        )
    for candidate in manifest.get("vasp_label_candidates", []):
        index = int(candidate["image"])
        for reason in candidate.get("reasons", []):
            if "largest_adjacent_rmsd" in str(reason):
                add(index, "path_continuity_anomaly")
    if committee is not None:
        ranked = sorted(
            (row for row in committee["images"] if 0 < int(row["image"]) < len(images) - 1),
            key=lambda row: float(row["force_vector_std_max_eV_per_A"]),
            reverse=True,
        )
        for rank, row in enumerate(
            ranked[: int(configured.get("committee_high_disagreement_images", 2))], start=1
        ):
            add(int(row["image"]), f"committee_force_disagreement_rank_{rank}")

    mandatory = {peak_index, peak_index - 1, peak_index + 1}
    priority = sorted(
        reasons,
        key=lambda index: (
            0 if index in mandatory else 1,
            0 if "path_continuity_anomaly" in reasons[index] else 1,
            0 if any(value.startswith("committee_") for value in reasons[index]) else 1,
            abs(index - peak_index),
            index,
        ),
    )
    selected_indices = sorted(priority[:maximum])
    if len(selected_indices) < minimum:
        raise ValueError("path does not contain enough distinct internal images for labeling")
    rows_by_index = {int(row["image"]): row for row in images}
    selected: list[dict[str, Any]] = []
    for index in selected_indices:
        row = rows_by_index[index]
        role = "near_saddle" if abs(index - peak_index) <= 1 else (
            "rising_path" if index < peak_index else "falling_path"
        )
        selected.append(
            {
                "image": row["image"],
                "role": role,
                "reasons": sorted(reasons[index]),
                "structure_path": row["structure_path"],
                "structure_sha256": row["structure_sha256"],
                "predicted_energy_eV": row["predicted_energy_eV"],
                "reaction_coordinate_value": row["reaction_coordinate_value"],
            }
        )
    return selected

def _path_candidate_record(
    path_manifest_path: Path,
    contract: dict[str, Any],
    policy: dict[str, Any],
    committee_assessment_path: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    manifest = validate_gpu_ml_neb_path_manifest(path_manifest_path)
    if manifest["contract_sha256"] != contract["contract_sha256"]:
        raise ValueError("ML path reaction-contract hash mismatch")
    if manifest["atom_map_sha256"] != contract["atom_map_sha256"]:
        raise ValueError("ML path atom-map hash mismatch")
    if manifest["compatibility_sha256"] != contract["compatibility_sha256"]:
        raise ValueError("ML path compatibility hash mismatch")
    source_path, source = _source_handoff(path_manifest_path, manifest)
    committee = _load_committee_assessment(
        committee_assessment_path,
        path_manifest_path=path_manifest_path,
        path_manifest=manifest,
    )
    selected = _select_path_images(manifest, policy, committee)
    peak = max(manifest["images"][1:-1], key=lambda row: row["predicted_energy_eV"])
    structure = _resolve(path_manifest_path.parent, peak["structure_path"])
    symbols = parse_poscar_symbols(structure)
    candidate = {
        "candidate_kind": "gpu_ml_neb_complete_path",
        "manifest_path": str(path_manifest_path.resolve()),
        "manifest_sha256": sha256_file(path_manifest_path),
        "source_handoff_path": str(source_path.resolve()),
        "source_handoff_sha256": sha256_file(source_path),
        "structure_path": str(structure.resolve()),
        "structure_sha256": peak["structure_sha256"],
        "atom_order_sha256": atom_order_sha256(symbols),
        "peak_image": peak["image"],
        "model_identifier": manifest["model_identifier"],
        "checkpoint_sha256": manifest["checkpoint_sha256"],
        "result_class": "predicted_path_candidate_only",
        "reportable_final": False,
        "indexed_bond_changes": source["transition_state"]["indexed_bond_changes"],
        "run_settings": manifest["run_settings"],
    }
    return candidate, selected, committee
