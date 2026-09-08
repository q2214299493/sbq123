from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.artifact_io import sha256_file
from scripts.matris_training_exclusions import (
    geometry_fingerprint,
    write_heldout_exclusion_manifest,
)
from scripts.neb_agent.utils_structure import read_poscar
from scripts.prepare_matris_finetune_request import preflight_and_prepare


FINE_TUNE_DECISION = (
    "fine_tune_MatRIS_then_require_new_checkpoint_and_complete_path_rerun"
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_poscar(path: Path) -> None:
    path.write_text(
        "held-out\n"
        "1.0\n"
        "5.0 0.0 0.0\n"
        "0.0 5.0 0.0\n"
        "0.0 0.0 5.0\n"
        "Fe H\n"
        "1 1\n"
        "Selective dynamics\n"
        "Direct\n"
        "0.1 0.1 0.1 F F F\n"
        "0.2 0.2 0.2 T T T\n",
        encoding="ascii",
    )


def _fixture(tmp_path: Path, *, triggered: bool) -> tuple[Path, Path]:
    candidate = tmp_path / "candidate" / "POSCAR"
    candidate.parent.mkdir()
    _write_poscar(candidate)
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
                "sample_id": "heldout",
                "role": "near_saddle",
                "primary_heldout_metric_eligible": True,
                "structure_path": "candidate/POSCAR",
                "structure_sha256": sha256_file(candidate),
                "geometry_sha256": geometry_fingerprint(read_poscar(candidate)),
            }
        ],
    }
    plan_path = tmp_path / "heldout_plan.json"
    _write_json(plan_path, plan)
    exclusion_path = tmp_path / "heldout_exclusions.json"
    write_heldout_exclusion_manifest(plan_path, exclusion_path)

    labels_path = tmp_path / "labels.json"
    _write_json(
        labels_path,
        {
            "document_kind": "dual_model_ts_vasp_force_label_set",
            "reaction_id": "reaction",
            "round_index": 0,
        },
    )
    decision = FINE_TUNE_DECISION if triggered else (
        "retain_MatRIS_checkpoint_then_run_disjoint_heldout_TS_validation"
    )
    assessment_path = tmp_path / "assessment.json"
    _write_json(
        assessment_path,
        {
            "document_kind": "dual_model_ts_vasp_error_assessment",
            "reaction_id": "reaction",
            "round_index": 0,
            "source_vasp_label_set_sha256": sha256_file(labels_path),
            "decision": decision,
            "models": {
                "matris_primary": {"checkpoint_sha256": "1" * 64},
            },
        },
    )
    policy_path = tmp_path / "policy.yaml"
    _write_json(
        policy_path,
        {
            "matris_fine_tuning": {
                "training_targets": ["movable_atom_vasp_forces"],
                "replay_required": ["prior_ts_force_labels"],
                "acceptance_requires": ["independent_ts_force_metrics_pass"],
                "force_only_checkpoint_production_promotion": "forbidden",
            },
            "held_out_validation": {
                "exclusion_manifest_required_for_all_matris_training": True,
            },
        },
    )
    state_path = tmp_path / "state.json"
    _write_json(
        state_path,
        {
            "document_kind": "dual_model_ts_active_learning_state",
            "reaction_id": "reaction",
            "round_index": 0,
            "status": (
                "awaiting_energy_force_aware_MatRIS_fine_tuning"
                if triggered
                else "awaiting_disjoint_heldout_TS_validation"
            ),
            "source_bindings": {
                "policy": {
                    "path": str(policy_path),
                    "sha256": sha256_file(policy_path),
                }
            },
            "vasp_error_assessment": {
                "path": str(assessment_path),
                "sha256": sha256_file(assessment_path),
                "decision": decision,
            },
            "vasp_label_batch": {
                "completed_label_set_path": str(labels_path),
                "completed_label_set_sha256": sha256_file(labels_path),
            },
        },
    )
    return state_path, exclusion_path


def test_preflight_blocks_request_when_fine_tuning_was_not_triggered(
    tmp_path: Path,
) -> None:
    state_path, exclusion_path = _fixture(tmp_path, triggered=False)
    request_path = tmp_path / "request.json"
    preflight_path = tmp_path / "preflight.json"

    report = preflight_and_prepare(
        state_path,
        exclusion_path,
        expected_exclusion_sha256=sha256_file(exclusion_path),
        request_output=request_path,
        preflight_output=preflight_path,
    )

    assert report["passed"] is False
    assert report["request_generated"] is False
    assert "MATRIS_FINE_TUNE_STATUS_NOT_REACHED" in report["blockers"]
    assert "MATRIS_FINE_TUNE_DECISION_NOT_REACHED" in report["blockers"]
    assert preflight_path.is_file()
    assert not request_path.exists()


def test_preflight_rejects_tampered_exclusion_hash(tmp_path: Path) -> None:
    state_path, exclusion_path = _fixture(tmp_path, triggered=True)

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        preflight_and_prepare(
            state_path,
            exclusion_path,
            expected_exclusion_sha256="0" * 64,
            request_output=tmp_path / "request.json",
            preflight_output=tmp_path / "preflight.json",
        )


def test_preflight_generates_bound_non_executable_request_after_trigger(
    tmp_path: Path,
) -> None:
    state_path, exclusion_path = _fixture(tmp_path, triggered=True)
    request_path = tmp_path / "request.json"
    preflight_path = tmp_path / "preflight.json"

    report = preflight_and_prepare(
        state_path,
        exclusion_path,
        expected_exclusion_sha256=sha256_file(exclusion_path),
        request_output=request_path,
        preflight_output=preflight_path,
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert report["passed"] is True
    assert report["request_generated"] is True
    assert report["request_sha256"] == sha256_file(request_path)
    assert request["heldout_exclusion_manifest"]["sha256"] == sha256_file(
        exclusion_path
    )
    assert request["execution_authorized"] is False
    assert request["automatic_submission"] is False
    assert request["next_required_action"] == (
        "request_separate_MatRIS_finetune_authorization"
    )
