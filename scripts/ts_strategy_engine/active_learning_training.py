from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from scripts.artifact_io import sha256_file
from scripts.aqcat25_ts_schema import load_document
from scripts.execution_backends import load_execution_backends, require_gpu_write_path

from .active_learning_common import (
    VASP_LABEL_CLASS,
    candidate_record,
    contract_for_state,
    current_round,
    load_policy,
    load_bound_vasp_label,
    load_state,
    read_json,
    utc_now,
    write_json,
)


def _project_path(policy_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else policy_path.resolve().parents[1] / path


def _replay_samples(
    policy_path: Path, policy: dict[str, Any], destination: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    replay = policy["fine_tuning"]["replay"]
    labels_path = _project_path(policy_path, replay["labels"])
    structures_root = _project_path(policy_path, replay["structures"])
    payload = read_json(labels_path)
    validation_ids = set(replay["validation_sample_ids"])
    training: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sample in payload.get("samples", []):
        sample_id = str(sample["sample_id"])
        structure = structures_root / f"{sample_id}.vasp"
        if sha256_file(structure) != sample["structure_sha256"]:
            raise ValueError(f"replay structure hash mismatch: {sample_id}")
        split = "validation" if sample_id in validation_ids else "training"
        target_dir = destination / "replay" / split
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{sample_id}.vasp"
        shutil.copy2(structure, target)
        if sample["structure_sha256"] in seen:
            raise ValueError("duplicate replay structure hash")
        seen.add(sample["structure_sha256"])
        record = {
            "sample_id": sample_id,
            "sample_role": "adsorption_regression_replay",
            "family": sample["family"],
            "structure_path": target.relative_to(destination).as_posix(),
            "structure_sha256": sample["structure_sha256"],
            "forces_eV_per_A": sample["forces_eV_per_A"],
            "energy_eV_force_label_only": sample["final_toten_eV"],
            "source_result_class": "vasp_completed_adsorption_calibration_force_label",
            "source_labels_sha256": sha256_file(labels_path),
        }
        (validation if split == "validation" else training).append(record)
    if len(training) < int(replay["minimum_training_samples"]):
        raise ValueError("insufficient adsorption replay training samples")
    if len(validation) < int(replay["minimum_validation_samples"]):
        raise ValueError("insufficient held-out adsorption regression samples")
    thresholds_source = _project_path(policy_path, replay["validation_thresholds"])
    thresholds_target = destination / "replay" / "adsorption_domain_gate.yaml"
    shutil.copy2(thresholds_source, thresholds_target)
    evidence = {
        "calibration_id": payload.get("calibration_id"),
        "labels_sha256": sha256_file(labels_path),
        "training_sample_count": len(training),
        "validation_sample_count": len(validation),
        "validation_sample_ids": sorted(validation_ids),
        "thresholds_path": thresholds_target.relative_to(destination).as_posix(),
        "thresholds_sha256": sha256_file(thresholds_target),
    }
    return training, validation, evidence


def prepare_finetuning_package(state_path: Path, destination: Path) -> dict[str, Any]:
    state = load_state(state_path)
    policy_path = Path(state["policy_path"])
    policy = load_policy(policy_path)
    current = current_round(state)
    if current["status"] != "fine_tuning_required":
        raise ValueError("force-only fine-tuning is not required for the current round")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"fine-tuning destination is not empty: {destination}")
    labels: list[dict[str, Any]] = []
    for round_record in state["rounds"]:
        path_refs = round_record.get("path_vasp_force_labels") or []
        legacy_ref = round_record.get("vasp_force_label")
        label_refs = path_refs or ([legacy_ref] if legacy_ref else [])
        for position, label_ref in enumerate(label_refs):
            if not label_ref or label_ref.get("status") != "accepted_force_label_only":
                continue
            report = load_bound_vasp_label(
                Path(label_ref["report_path"]),
                label_ref["report_sha256"],
                contract_sha256=state["contract_sha256"],
                compatibility_sha256=state["compatibility_sha256"],
            )
            image = str(label_ref.get("image", f"candidate_{position:02d}"))
            label_directory = (
                destination
                / "labels"
                / f"round_{int(round_record['round_index']):03d}"
                / f"image_{image}"
            )
            label_directory.mkdir(parents=True, exist_ok=True)
            structure_target = label_directory / "POSCAR"
            shutil.copy2(Path(report["structure"]["path"]), structure_target)
            if sha256_file(structure_target) != report["structure"]["sha256"]:
                raise ValueError("copied VASP label structure hash mismatch")
            labels.append(
                {
                    "round_index": round_record["round_index"],
                    "image": image,
                    "structure_path": structure_target.relative_to(destination).as_posix(),
                    "structure_sha256": report["structure"]["sha256"],
                    "forces_eV_per_A": report["forces_eV_per_A"],
                    "energy_eV_force_label_only": report["dft_toten_eV_force_label_only"],
                    "source_outcar_sha256": report["outcar"]["sha256"],
                    "source_result_class": VASP_LABEL_CLASS,
                }
            )
    if not labels:
        raise ValueError("no accepted VASP force labels are available for training")
    training = policy["fine_tuning"]
    gpu_backend = load_execution_backends().gpu
    require_gpu_write_path(training["remote_root"])
    latest_checkpoint = state.get("latest_finetuned_checkpoint")
    base = latest_checkpoint or {
        "path": training["initial_checkpoint_path"],
        "sha256": current["candidate"]["checkpoint_sha256"],
    }
    replay_training, replay_validation, replay_evidence = _replay_samples(policy_path, policy, destination)
    ts_hashes = {label["structure_sha256"] for label in labels}
    replay_hashes = {sample["structure_sha256"] for sample in replay_training + replay_validation}
    if ts_hashes & replay_hashes:
        raise ValueError("TS labels overlap adsorption replay or validation structures")
    ts_training = [
        {
            **label,
            "sample_id": (
                f"ts_round_{int(label['round_index']):03d}_image_{label['image']}"
            ),
            "sample_role": "ts_force_training",
        }
        for label in labels
    ]
    manifest = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_force_only_training_manifest",
        "reaction_id": state["reaction_id"],
        "round_index": current["round_index"],
        "base_checkpoint": base,
        "labels": labels,
        "training_samples": ts_training + replay_training,
        "validation_samples": replay_validation,
        "replay_evidence": replay_evidence,
        "epochs": int(training["epochs"]),
        "output_result_class": training["result_class"],
        "training_target": "forces_only",
        "energy_loss_coefficient": 0.0,
        "checkpoint_acceptance_requires": [
            "checkpoint_load_and_finite_prediction",
            "held_out_adsorption_regression_pass",
            "new_checkpoint_sha256",
        ],
        "restrictions": {
            "remote_write_root": training["remote_root"],
            "reportable_final_energy": False,
            "scientific_acceptance": False,
        },
    }
    manifest_path = write_json(destination / "training_manifest.json", manifest)
    current["fine_tuning"] = {
        "status": "prepared_not_submitted",
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
    }
    current["status"] = "awaiting_force_only_finetuning"
    state["status"] = current["status"]
    state["next_action"] = (
        f"review_then_submit_force_only_finetuning_on_{gpu_backend.hostname}_with_user_authority"
    )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return manifest


def register_finetuning_result(state_path: Path, result_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    policy = load_policy(Path(state["policy_path"]))
    current = current_round(state)
    if current["status"] != "awaiting_force_only_finetuning":
        raise ValueError("current round is not awaiting fine-tuning")
    result = load_document(result_path, expected_kind="aqcat25_ts_force_only_finetune_result")
    expected_manifest = current["fine_tuning"]["manifest_sha256"]
    if result.get("status") != "success" or result.get("training_manifest_sha256") != expected_manifest:
        raise ValueError("fine-tuning result is failed or bound to the wrong manifest")
    checkpoint = result.get("checkpoint") or {}
    remote_root = require_gpu_write_path(policy["fine_tuning"]["remote_root"])
    checkpoint_path = require_gpu_write_path(checkpoint.get("path", ""))
    if len(str(checkpoint.get("sha256", ""))) != 64 or not (
        checkpoint_path == remote_root
        or checkpoint_path.startswith(f"{remote_root.rstrip('/')}/")
    ):
        raise ValueError(
            "fine-tuned checkpoint evidence is invalid or outside the configured GPU write boundary"
        )
    if policy["round_control"]["require_new_checkpoint_after_finetune"] and (
        checkpoint["sha256"] == current["candidate"]["checkpoint_sha256"]
    ):
        raise ValueError("fine-tuning did not produce a new checkpoint")
    validation_ref = result.get("checkpoint_validation") or {}
    validation_path = result_path.parent / str(validation_ref.get("path", ""))
    if not validation_path.is_file() or sha256_file(validation_path) != validation_ref.get("sha256"):
        raise ValueError("fine-tuned checkpoint validation report is missing or hash-mismatched")
    validation = read_json(validation_path)
    if (
        validation.get("document_kind") != "aqcat25_finetuned_checkpoint_validation"
        or validation.get("status") != "passed"
        or validation.get("checkpoint_sha256") != checkpoint["sha256"]
        or validation_ref.get("status") != "passed"
        or validation_ref.get("checkpoint_sha256") != checkpoint["sha256"]
    ):
        raise ValueError("fine-tuned checkpoint failed load/regression validation")
    current["fine_tuning"].update(
        {
            "status": "completed_candidate_checkpoint",
            "result_path": str(result_path.resolve()),
            "result_sha256": sha256_file(result_path),
            "checkpoint": checkpoint,
        }
    )
    state["latest_finetuned_checkpoint"] = checkpoint
    path_mode = current["candidate"].get("candidate_kind") == "gpu_ml_neb_complete_path"
    current["status"] = (
        "awaiting_ml_neb_path_rerun" if path_mode else "awaiting_ba_sella_rerun"
    )
    state["status"] = current["status"]
    state["next_action"] = (
        "prepare_full_ML_NEB_path_rerun_with_new_checkpoint"
        if path_mode
        else "rerun_AQCat25_BA_Sella_with_new_checkpoint_then_register_candidate"
    )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return result


def register_next_candidate(
    state_path: Path,
    candidate_manifest: Path,
    handoff_root: Path,
    contract_path: Path,
) -> dict[str, Any]:
    state = load_state(state_path)
    policy = load_policy(Path(state["policy_path"]))
    current = current_round(state)
    if current["status"] != "awaiting_ba_sella_rerun_result":
        raise ValueError("current round is not awaiting a BA-Sella rerun")
    next_index = int(current["round_index"]) + 1
    if next_index >= int(policy["round_control"]["max_rounds"]):
        state["status"] = "blocked_maximum_active_learning_rounds_reached"
        state["next_action"] = "human_review_required"
        state["updated_at"] = utc_now()
        write_json(state_path, state)
        raise ValueError("maximum active-learning rounds reached")
    contract = contract_for_state(contract_path, state)
    candidate = candidate_record(candidate_manifest, handoff_root, contract)
    expected_checkpoint = state["latest_finetuned_checkpoint"]["sha256"]
    if candidate["checkpoint_sha256"] != expected_checkpoint:
        raise ValueError("BA-Sella rerun did not use the registered fine-tuned checkpoint")
    state["rounds"].append(
        {
            "round_index": next_index,
            "status": "awaiting_vasp_force_label_preparation",
            "candidate": candidate,
            "vasp_force_label": None,
            "force_agreement": None,
            "force_prediction": None,
            "fine_tuning": None,
            "ts_domain_assessment": None,
            "job_evidence": {},
        }
    )
    state["status"] = "awaiting_vasp_force_label_preparation"
    state["next_action"] = "prepare_vasp_force_label"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return state
