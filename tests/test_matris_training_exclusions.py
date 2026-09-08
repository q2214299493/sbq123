from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file
from scripts.matris_finetune_speed_benchmark import verify_inputs
from scripts.matris_training_exclusions import (
    assert_training_samples_disjoint,
    geometry_fingerprint,
    load_heldout_exclusions,
    write_heldout_exclusion_manifest,
)
from scripts.neb_agent.utils_structure import read_poscar
from scripts.prepare_dual_model_ts_heldout_execution import prepare as prepare_execution


def _write_poscar(path: Path, *, movable_x: float, comment: str) -> None:
    path.write_text(
        f"{comment}\n"
        "1.0\n"
        "5.0 0.0 0.0\n"
        "0.0 5.0 0.0\n"
        "0.0 0.0 5.0\n"
        "Fe H\n"
        "1 1\n"
        "Selective dynamics\n"
        "Direct\n"
        "0.1 0.1 0.1 F F F\n"
        f"{movable_x} 0.2 0.2 T T T\n",
        encoding="ascii",
    )


def _write_plan(tmp_path: Path) -> tuple[Path, Path]:
    candidate = tmp_path / "candidates" / "held_rising" / "POSCAR"
    candidate.parent.mkdir(parents=True)
    _write_poscar(candidate, movable_x=0.2, comment="held-out")
    plan = {
        "schema_version": 1,
        "document_kind": "dual_model_ts_heldout_validation_candidate_plan",
        "status": "prepared_for_user_geometry_review_not_submitted",
        "heldout_definition": (
            "disjoint_from_round0_seven_VASP_screening_labels_and_not_used_for_training"
        ),
        "reaction_id": "reaction",
        "round_index": 0,
        "frozen_models": {
            "primary": {"checkpoint_sha256": "1" * 64},
            "secondary": {"checkpoint_sha256": "2" * 64},
        },
        "candidates": [
            {
                "sample_id": "held_rising",
                "role": "rising_path",
                "primary_heldout_metric_eligible": True,
                "structure_path": "candidates/held_rising/POSCAR",
                "structure_sha256": sha256_file(candidate),
                "geometry_sha256": geometry_fingerprint(read_poscar(candidate)),
            }
        ],
    }
    plan_path = tmp_path / "heldout_plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan_path, candidate


def _training_sample(path: Path, sample_id: str = "training") -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "structure": {
            "path": path.name,
            "sha256": sha256_file(path),
            "atom_count": 2,
        },
        "vasp_label": {"forces_eV_per_A": [[0.0, 0.0, 0.0]] * 2},
    }


def test_manifest_is_hash_bound_and_idempotent(tmp_path: Path) -> None:
    plan_path, _ = _write_plan(tmp_path)
    manifest_path = tmp_path / "heldout_exclusions.json"

    first = write_heldout_exclusion_manifest(plan_path, manifest_path)
    second = write_heldout_exclusion_manifest(plan_path, manifest_path)
    payload = load_heldout_exclusions(
        manifest_path, expected_sha256=sha256_file(manifest_path)
    )

    assert first == second == manifest_path
    assert payload["source_heldout_plan"]["sha256"] == sha256_file(plan_path)
    assert payload["excluded_structures"][0]["exclude_from_training_and_replay"] is True


def test_manifest_hash_tampering_is_rejected(tmp_path: Path) -> None:
    plan_path, _ = _write_plan(tmp_path)
    manifest_path = tmp_path / "heldout_exclusions.json"
    write_heldout_exclusion_manifest(plan_path, manifest_path)

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        load_heldout_exclusions(manifest_path, expected_sha256="0" * 64)


def test_exact_and_renamed_geometry_overlap_are_rejected(tmp_path: Path) -> None:
    plan_path, heldout = _write_plan(tmp_path)
    manifest_path = tmp_path / "heldout_exclusions.json"
    write_heldout_exclusion_manifest(plan_path, manifest_path)
    exclusions = load_heldout_exclusions(
        manifest_path, expected_sha256=sha256_file(manifest_path)
    )

    with pytest.raises(ValueError, match="overlaps held-out exact structure"):
        assert_training_samples_disjoint(
            [_training_sample(heldout)],
            structures_root=heldout.parent,
            exclusion_manifest=exclusions,
        )

    renamed = tmp_path / "renamed.vasp"
    _write_poscar(renamed, movable_x=0.2, comment="renamed-to-bypass-id-check")
    assert sha256_file(renamed) != sha256_file(heldout)
    with pytest.raises(ValueError, match="overlaps held-out geometry"):
        assert_training_samples_disjoint(
            [_training_sample(renamed)],
            structures_root=tmp_path,
            exclusion_manifest=exclusions,
        )


def test_disjoint_training_geometry_passes(tmp_path: Path) -> None:
    plan_path, _ = _write_plan(tmp_path)
    manifest_path = tmp_path / "heldout_exclusions.json"
    write_heldout_exclusion_manifest(plan_path, manifest_path)
    exclusions = load_heldout_exclusions(
        manifest_path, expected_sha256=sha256_file(manifest_path)
    )
    disjoint = tmp_path / "disjoint.vasp"
    _write_poscar(disjoint, movable_x=0.35, comment="disjoint")

    result = assert_training_samples_disjoint(
        [_training_sample(disjoint)],
        structures_root=tmp_path,
        exclusion_manifest=exclusions,
    )

    assert result == {"training_sample_count_checked": 1, "heldout_structure_count": 1}


def test_matris_training_entrypoint_requires_exclusions_and_rejects_overlap(
    tmp_path: Path,
) -> None:
    plan_path, heldout = _write_plan(tmp_path)
    exclusion_path = tmp_path / "heldout_exclusions.json"
    write_heldout_exclusion_manifest(plan_path, exclusion_path)
    checkpoint = tmp_path / "checkpoint.pth.tar"
    checkpoint.write_bytes(b"checkpoint")
    sample = _training_sample(heldout, "train_heldout")
    sample["structure"]["path"] = heldout.relative_to(tmp_path).as_posix()
    benchmark_manifest = {
        "document_kind": "mlip_same_structure_benchmark_manifest",
        "matris_checkpoint_sha256": sha256_file(checkpoint),
        "samples": [sample],
    }
    benchmark_path = tmp_path / "benchmark_manifest.json"
    benchmark_path.write_text(json.dumps(benchmark_manifest), encoding="utf-8")
    experiment = {
        "document_kind": "matris_finetune_speed_benchmark_experiment",
        "benchmark_manifest": {
            "path": str(benchmark_path),
            "sha256": sha256_file(benchmark_path),
        },
        "base_checkpoint": {
            "path": str(checkpoint),
            "sha256": sha256_file(checkpoint),
        },
        "fine_tuning": {
            "folds": [
                {
                    "training_sample_ids": ["train_heldout"],
                    "held_out_sample_ids": [],
                }
            ]
        },
    }
    experiment_path = tmp_path / "experiment.json"

    with pytest.raises(ValueError, match="requires a hash-bound"):
        verify_inputs(experiment_path, experiment)

    experiment["heldout_exclusion_manifest"] = {
        "path": str(exclusion_path),
        "sha256": sha256_file(exclusion_path),
    }
    with pytest.raises(ValueError, match="overlaps held-out exact structure"):
        verify_inputs(experiment_path, experiment)


def test_heldout_execution_binds_generated_exclusion_manifest(tmp_path: Path) -> None:
    plan_path, _ = _write_plan(tmp_path)
    plan_hash = sha256_file(plan_path)
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "document_kind": "dual_model_ts_active_learning_state",
                "reaction_id": "reaction",
                "status": "awaiting_user_heldout_geometry_review",
                "heldout_validation_plan": {"sha256": plan_hash},
            }
        ),
        encoding="utf-8",
    )
    source_batch_path = tmp_path / "source_prediction_batch.json"
    source_batch_path.write_text(
        json.dumps(
            {
                "document_kind": "dual_model_ts_path_force_prediction_batch_request",
                "reaction_id": "reaction",
                "models": {
                    "primary": {"checkpoint_sha256": "1" * 64},
                    "secondary": {"checkpoint_sha256": "2" * 64},
                },
                "indexed_bond_changes": [],
                "fixed_atom_indices_zero_based": [0],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "execution"

    summary = prepare_execution(
        plan_path,
        state_path,
        source_batch_path,
        Path("configs/true_fe110_production.yaml"),
        output,
    )

    exclusion_path = output / "heldout_training_exclusions.json"
    exclusion_hash = sha256_file(exclusion_path)
    prediction_request = json.loads(
        (output / "gpu_prediction" / "dual_model_prediction_batch_request.json").read_text(
            encoding="utf-8"
        )
    )
    vasp_request = json.loads(
        (output / "vasp_static_labels" / "heldout_vasp_batch_request.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["heldout_training_exclusion_manifest"]["sha256"] == exclusion_hash
    assert (
        prediction_request["source"]["heldout_training_exclusion_manifest_sha256"]
        == exclusion_hash
    )
    assert vasp_request["heldout_training_exclusion_manifest_sha256"] == exclusion_hash
