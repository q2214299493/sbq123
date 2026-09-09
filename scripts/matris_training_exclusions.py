#!/usr/bin/env python3
"""Build and enforce hash-bound held-out exclusions for MatRIS training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.artifact_io import (
    load_json_object,
    require_sha256,
    sha256_file,
    sha256_json,
    write_json_atomic,
)
from scripts.neb_agent.utils_structure import Poscar, read_poscar
from scripts.scientific_validation import finite_array
from scripts.provenance_fields import required_text


DOCUMENT_KIND = "matris_heldout_training_exclusion_manifest"


def structure_equivalence_fingerprint(structure: Poscar) -> str:
    """Conservative split identity, invariant to atom permutation and rigid motion.

    Labelled periodic distance multisets may collide for homometric structures;
    such collisions block a split, never authorize scientific-result reuse.
    Keep the existing five-decimal exclusion precision and legacy binding hash.
    """
    import numpy as np
    from ase.geometry import find_mic

    coordinates = np.asarray(finite_array(structure.frac.tolist(), "structure coordinates", shape=(len(structure.labels), 3)))
    cell = np.asarray(finite_array(structure.cell.tolist(), "structure cell", shape=(3, 3)))
    if abs(np.linalg.det(cell)) == 0:
        raise ValueError("singular structure cell")
    rows = []
    for index, label in enumerate(structure.labels):
        _, distances = find_mic((coordinates - coordinates[index]) @ cell, cell, pbc=True)
        rows.append((label, sorted((other, round(float(distance), 5))
                                  for other, distance in zip(structure.labels, distances))))
    return sha256_json({"volume": round(abs(float(np.linalg.det(cell))), 5), "neighborhoods": sorted(rows)})


def assert_dataset_splits_disjoint(splits: Mapping[str, Iterable[Mapping[str, Any]]], *, structures_root: Path) -> None:
    """Reject identity/geometry/reaction overlap across training, validation, test.

    Source identity is a row within a source, not a whole multi-reaction file.
    Reaction grouping is mandatory when a sample declares a reaction.
    """
    seen: dict[tuple[str, str], str] = {}
    for split, samples in splits.items():
        ids: set[str] = set()
        for sample in samples:
            sample_id = required_text(sample.get("sample_id"), "sample identity")
            if sample_id in ids:
                raise ValueError(f"duplicate sample in {split}: {sample_id}")
            ids.add(sample_id)
            source = sample.get("label_source", {})
            source_id = required_text(sample.get("source_sample_id"), "source row identity")
            source_hash = require_sha256(source.get("sha256"), label="label source identity")
            calculation = required_text(sample.get("calculation_id"), "calculation identity")
            structure = sample["structure"]
            path = structures_root / required_text(structure.get("path"), "structure path")
            if not path.is_file() or sha256_file(path) != structure.get("sha256"):
                raise ValueError(f"split structure binding failed: {sample_id}")
            identities = {
                "structure": structure_equivalence_fingerprint(read_poscar(path)),
                "calculation": calculation, "source": f"{source_hash}:{source_id}",
            }
            if sample.get("reaction_id") is not None:
                identities["reaction"] = required_text(sample["reaction_id"], "reaction identity")
            for kind, identity in identities.items():
                previous = seen.setdefault((kind, identity), split)
                if previous != split:
                    raise ValueError(f"{kind} leakage between {previous} and {split}: {sample_id}")


def geometry_fingerprint(structure: Poscar) -> str:
    """Hash translation-invariant rounded geometry, atom order, cell, and flags."""

    fixed = [
        index
        for index, flags in enumerate(structure.flags)
        if structure.selective
        and tuple(value.upper() for value in flags) == ("F", "F", "F")
    ]
    origin = structure.frac[fixed[0] if fixed else 0]
    relative = (structure.frac - origin) % 1.0
    return sha256_json(
        {
            "cell": structure.cell.round(5).tolist(),
            "labels": structure.labels,
            "relative_fractional_coordinates": relative.round(5).tolist(),
            "flags": structure.flags,
        }
    )




def build_heldout_exclusion_manifest(plan_path: Path) -> dict[str, Any]:
    """Build exclusions from one reviewed dual-model held-out candidate plan."""

    plan_path = plan_path.resolve()
    plan = load_json_object(plan_path)
    if plan.get("document_kind") != "dual_model_ts_heldout_validation_candidate_plan":
        raise ValueError("invalid dual-model held-out candidate plan")
    if plan.get("status") != "prepared_for_user_geometry_review_not_submitted":
        raise ValueError("held-out plan is not a frozen reviewable candidate plan")
    if plan.get("heldout_definition") != (
        "disjoint_from_round0_seven_VASP_screening_labels_and_not_used_for_training"
    ):
        raise ValueError("held-out plan does not forbid training use")

    exclusions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_structures: set[str] = set()
    seen_geometries: set[str] = set()
    for candidate in plan.get("candidates", []):
        sample_id = str(candidate.get("sample_id", ""))
        if not sample_id or sample_id in seen_ids:
            raise ValueError(f"invalid or duplicate held-out sample ID: {sample_id!r}")
        structure_path = plan_path.parent / str(candidate.get("structure_path", ""))
        expected_structure = require_sha256(
            candidate.get("structure_sha256"), label=f"{sample_id}.structure_sha256"
        )
        expected_geometry = require_sha256(
            candidate.get("geometry_sha256"), label=f"{sample_id}.geometry_sha256"
        )
        if not structure_path.is_file() or sha256_file(structure_path) != expected_structure:
            raise ValueError(f"held-out structure binding failed: {sample_id}")
        actual_geometry = geometry_fingerprint(read_poscar(structure_path))
        if actual_geometry != expected_geometry:
            raise ValueError(f"held-out geometry binding failed: {sample_id}")
        if expected_structure in seen_structures or expected_geometry in seen_geometries:
            raise ValueError(f"duplicate held-out structure or geometry: {sample_id}")
        seen_ids.add(sample_id)
        seen_structures.add(expected_structure)
        seen_geometries.add(expected_geometry)
        exclusions.append(
            {
                "sample_id": sample_id,
                "role": candidate["role"],
                "primary_metric_eligible": bool(
                    candidate["primary_heldout_metric_eligible"]
                ),
                "structure_sha256": expected_structure,
                "geometry_sha256": expected_geometry,
                "equivalence_sha256": structure_equivalence_fingerprint(read_poscar(structure_path)),
                "exclude_from_training_and_replay": True,
            }
        )

    if not exclusions:
        raise ValueError("held-out plan contains no exclusions")
    frozen_models = plan.get("frozen_models")
    if not isinstance(frozen_models, dict):
        raise ValueError("held-out plan lacks frozen model bindings")
    checkpoints = {
        role: require_sha256(
            frozen_models.get(role, {}).get("checkpoint_sha256"),
            label=f"frozen_models.{role}.checkpoint_sha256",
        )
        for role in ("primary", "secondary")
    }
    return {
        "schema_version": 1,
        "document_kind": DOCUMENT_KIND,
        "reaction_id": plan["reaction_id"],
        "round_index": plan["round_index"],
        "source_heldout_plan": {
            "path": str(plan_path),
            "sha256": sha256_file(plan_path),
        },
        "frozen_model_checkpoint_sha256": checkpoints,
        "excluded_structures": exclusions,
        "policy": {
            "training_overlap_allowed": False,
            "match_fields": ["structure_sha256", "geometry_sha256"],
            "applies_to": ["matris_training", "matris_replay"],
        },
    }


def write_heldout_exclusion_manifest(plan_path: Path, output: Path) -> Path:
    """Write once, or accept an already-identical immutable manifest."""

    payload = build_heldout_exclusion_manifest(plan_path)
    if output.exists():
        if load_json_object(output) != payload:
            raise FileExistsError(f"existing exclusion manifest differs: {output}")
        return output
    return write_json_atomic(output, payload, ensure_ascii=True)


def load_heldout_exclusions(
    path: Path, *, expected_sha256: str
) -> dict[str, Any]:
    """Load a manifest only after its caller-provided file hash is verified."""

    expected_sha256 = require_sha256(expected_sha256, label="heldout_exclusion_manifest")
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError("held-out exclusion manifest hash mismatch")
    payload = load_json_object(path)
    if payload.get("document_kind") != DOCUMENT_KIND:
        raise ValueError("invalid held-out exclusion manifest document kind")
    if payload.get("policy", {}).get("training_overlap_allowed") is not False:
        raise ValueError("held-out exclusion manifest does not forbid training overlap")
    if payload.get("policy", {}).get("match_fields") != [
        "structure_sha256",
        "geometry_sha256",
    ]:
        raise ValueError("held-out exclusion manifest has incomplete match fields")
    source_plan = payload.get("source_heldout_plan")
    if not isinstance(source_plan, dict):
        raise ValueError("held-out exclusion manifest lacks its source plan binding")
    require_sha256(source_plan.get("sha256"), label="source_heldout_plan.sha256")
    checkpoints = payload.get("frozen_model_checkpoint_sha256")
    if not isinstance(checkpoints, dict):
        raise ValueError("held-out exclusion manifest lacks frozen checkpoints")
    for role in ("primary", "secondary"):
        require_sha256(checkpoints.get(role), label=f"frozen_model_checkpoint_sha256.{role}")

    exclusions = payload.get("excluded_structures")
    if not isinstance(exclusions, list) or not exclusions:
        raise ValueError("held-out exclusion manifest contains no structures")
    sample_ids: set[str] = set()
    structure_hashes: set[str] = set()
    geometry_hashes: set[str] = set()
    for row in exclusions:
        if not isinstance(row, dict) or row.get("exclude_from_training_and_replay") is not True:
            raise ValueError("invalid held-out exclusion row")
        sample_id = str(row.get("sample_id", ""))
        structure_hash = require_sha256(
            row.get("structure_sha256"), label=f"{sample_id}.structure_sha256"
        )
        geometry_hash = require_sha256(
            row.get("geometry_sha256"), label=f"{sample_id}.geometry_sha256"
        )
        require_sha256(row.get("equivalence_sha256"), label=f"{sample_id}.equivalence_sha256; rebuild legacy exclusions")
        if (
            not sample_id
            or sample_id in sample_ids
            or structure_hash in structure_hashes
            or geometry_hash in geometry_hashes
        ):
            raise ValueError("duplicate held-out exclusion identity")
        sample_ids.add(sample_id)
        structure_hashes.add(structure_hash)
        geometry_hashes.add(geometry_hash)
    source_path = Path(required_text(source_plan.get("path"), "heldout source plan path"))
    if not source_path.is_file() or sha256_file(source_path) != source_plan["sha256"]:
        raise ValueError("held-out source plan is missing or stale")
    if build_heldout_exclusion_manifest(source_path) != payload:
        raise ValueError("held-out manifest differs from current source plan")
    return payload


def assert_training_samples_disjoint(
    samples: Iterable[Mapping[str, Any]],
    *,
    structures_root: Path,
    exclusion_manifest: Mapping[str, Any],
) -> dict[str, int]:
    """Reject any exact or rounded-geometry overlap before training starts."""

    exclusions = exclusion_manifest["excluded_structures"]
    excluded_structures = {str(row["structure_sha256"]) for row in exclusions}
    excluded_geometries = {str(row["geometry_sha256"]) for row in exclusions}
    excluded_equivalents = {require_sha256(row.get("equivalence_sha256"), label="heldout equivalence") for row in exclusions}
    checked = 0
    seen_equivalents: set[str] = set()
    for sample in samples:
        sample_id = str(sample.get("sample_id", ""))
        structure = sample.get("structure")
        if not sample_id or not isinstance(structure, Mapping):
            raise ValueError("training sample lacks a bound structure")
        structure_path = structures_root / str(structure.get("path", ""))
        expected_structure = require_sha256(
            structure.get("sha256"), label=f"{sample_id}.structure.sha256"
        )
        if not structure_path.is_file() or sha256_file(structure_path) != expected_structure:
            raise ValueError(f"training structure binding failed: {sample_id}")
        if expected_structure in excluded_structures:
            raise ValueError(
                f"MatRIS training sample overlaps held-out exact structure: {sample_id}"
            )
        parsed = read_poscar(structure_path)
        geometry_hash = geometry_fingerprint(parsed)
        if geometry_hash in excluded_geometries or structure_equivalence_fingerprint(parsed) in excluded_equivalents:
            raise ValueError(
                f"MatRIS training sample overlaps held-out geometry: {sample_id}"
            )
        equivalent = structure_equivalence_fingerprint(parsed)
        if equivalent in seen_equivalents:
            raise ValueError(f"duplicate optimizer structure: {sample_id}")
        seen_equivalents.add(equivalent)
        checked += 1
    return {
        "training_sample_count_checked": checked,
        "heldout_structure_count": len(excluded_structures),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = write_heldout_exclusion_manifest(args.plan, args.output)
    print(
        json.dumps(
            {"path": str(path.resolve()), "sha256": sha256_file(path)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
