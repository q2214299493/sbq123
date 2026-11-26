from __future__ import annotations

import math

import shutil

from pathlib import Path

from statistics import fmean

from typing import Any

from scripts.aqcat25_calibration import parse_poscar_symbols

from scripts.aqcat25_handoff import atom_order_sha256

from scripts.aqcat25_ts_schema import load_document

from scripts.artifact_io import sha256_file

from scripts.execution_backends import load_execution_backends

from .active_learning_common import (
    PREDICTED_CLASS,
    current_round,
    force_metrics,
    load_bound_vasp_label,
    load_policy,
    load_state,
    read_json,
    utc_now,
    write_json,
)

from .active_learning_path_common import _empty_destination, _resolve

from .active_learning_common import _checkpoint_for_current


def prepare_path_force_predictions(state_path: Path, destination: Path) -> dict[str, Any]:
    state = load_state(state_path)
    current = current_round(state)
    if current["status"] != "awaiting_path_ml_prediction_preparation":
        raise ValueError("current round is not ready for path force-prediction preparation")
    policy = load_policy(Path(state["policy_path"]))
    _empty_destination(destination)
    checkpoint = _checkpoint_for_current(state, policy)
    predictions = []
    for label_ref in current["path_vasp_force_labels"]:
        report = load_bound_vasp_label(
            Path(label_ref["report_path"]),
            label_ref["report_sha256"],
            contract_sha256=state["contract_sha256"],
            compatibility_sha256=state["compatibility_sha256"],
        )
        image_dir = destination / f"image_{label_ref['image']}"
        image_dir.mkdir()
        target = image_dir / "POSCAR"
        shutil.copy2(Path(report["structure"]["path"]), target)
        symbols = parse_poscar_symbols(target)
        adsorbate = [index for index, symbol in enumerate(symbols, start=1) if symbol != "Fe"]
        if not adsorbate:
            raise ValueError("force-prediction request has no non-Fe adsorbate atoms")
        request = {
            "schema_version": 1,
            "document_kind": "aqcat25_ts_force_prediction_request",
            "reaction_id": state["reaction_id"],
            "round_index": current["round_index"],
            "structure": {
                "path": "POSCAR",
                "sha256": sha256_file(target),
                "atom_order_sha256": atom_order_sha256(symbols),
            },
            "checkpoint": checkpoint,
            "indexed_bond_changes": current["candidate"]["indexed_bond_changes"],
            "adsorbate_indices_1based": adsorbate,
            "result_class": PREDICTED_CLASS,
            "restrictions": {
                "backend": load_execution_backends().gpu.hostname,
                "reportable_dft": False,
                "automatic_submission": False,
            },
        }
        request_path = write_json(image_dir / "prediction_request.json", request)
        predictions.append(
            {
                "image": label_ref["image"],
                "directory": str(image_dir.resolve()),
                "structure_sha256": sha256_file(target),
                "request_path": str(request_path.resolve()),
                "request_sha256": sha256_file(request_path),
                "status": "prepared_not_submitted",
            }
        )
    batch = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_path_force_prediction_batch_request",
        "reaction_id": state["reaction_id"],
        "round_index": current["round_index"],
        "checkpoint": checkpoint,
        "source_path_manifest_sha256": current["candidate"]["manifest_sha256"],
        "predictions": [
            {
                "image": row["image"],
                "request": Path(row["request_path"])
                .relative_to(destination.resolve())
                .as_posix(),
                "request_sha256": row["request_sha256"],
                "structure_sha256": row["structure_sha256"],
            }
            for row in predictions
        ],
        "automatic_submission": False,
    }
    batch_path = write_json(destination / "path_prediction_batch_request.json", batch)
    current["path_force_predictions"] = predictions
    current["path_prediction_batch"] = {
        "path": str(batch_path.resolve()),
        "sha256": sha256_file(batch_path),
        "status": "prepared_not_submitted",
    }
    current["status"] = "awaiting_path_ml_force_predictions"
    state["status"] = current["status"]
    state["next_action"] = "run_hash_bound_exact_structure_prediction_batch_on_MZ73_after_review"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return batch

def assess_path_force_predictions(state_path: Path, manifest_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    current = current_round(state)
    if current["status"] != "awaiting_path_ml_force_predictions":
        raise ValueError("current round is not awaiting path force predictions")
    policy = load_policy(Path(state["policy_path"]))
    payload = read_json(manifest_path)
    if payload.get("document_kind") != "aqcat25_ts_path_force_prediction_set":
        raise ValueError("invalid path force-prediction set")
    if payload.get("source_request_sha256") != current["path_prediction_batch"]["sha256"]:
        raise ValueError("path force predictions are not bound to the prepared batch")
    if payload.get("checkpoint_sha256") != current["candidate"]["checkpoint_sha256"]:
        raise ValueError("path force-prediction checkpoint mismatch")
    rows = payload.get("predictions")
    by_image = {row.get("image"): row for row in rows if isinstance(row, dict)} if isinstance(rows, list) else {}
    expected = {row["image"] for row in current["path_force_predictions"]}
    if set(by_image) != expected or len(by_image) != len(rows):
        raise ValueError("path force-prediction image set mismatch or duplicate")
    labels = {row["image"]: row for row in current["path_vasp_force_labels"]}
    component_errors: list[float] = []
    vector_errors: list[float] = []
    samples = []
    thresholds = policy["local_force_screen"]
    for request_ref in current["path_force_predictions"]:
        image = request_ref["image"]
        prediction_ref = by_image[image]
        prediction_path = _resolve(manifest_path.parent, str(prediction_ref.get("prediction", "")))
        if not prediction_path.is_file() or sha256_file(prediction_path) != prediction_ref.get("prediction_sha256"):
            raise ValueError(f"prediction hash mismatch for image {image}")
        prediction = load_document(prediction_path, expected_kind="aqcat25_ts_force_prediction")
        if prediction["request_sha256"] != request_ref["request_sha256"]:
            raise ValueError(f"prediction request mismatch for image {image}")
        if prediction["structure_sha256"] != request_ref["structure_sha256"]:
            raise ValueError(f"prediction structure mismatch for image {image}")
        if prediction["checkpoint_sha256"] != current["candidate"]["checkpoint_sha256"]:
            raise ValueError(f"prediction checkpoint mismatch for image {image}")
        label_ref = labels[image]
        label = load_bound_vasp_label(
            Path(label_ref["report_path"]),
            label_ref["report_sha256"],
            contract_sha256=state["contract_sha256"],
            compatibility_sha256=state["compatibility_sha256"],
        )
        fixed = set(label["fixed_atom_indices_zero_based"])
        movable = [index for index in range(len(label["forces_eV_per_A"])) if index not in fixed]
        metrics, components, vectors = force_metrics(
            label["forces_eV_per_A"], prediction["forces_eV_per_A"], movable
        )
        checks = {
            "component_mae": metrics["component_mae_eV_per_A"]
            <= float(thresholds["component_mae_eV_per_A_max"]),
            "vector_rmse": metrics["vector_rmse_eV_per_A"]
            <= float(thresholds["vector_rmse_eV_per_A_max"]),
            "vector_max": metrics["vector_max_eV_per_A"]
            <= float(thresholds["vector_max_eV_per_A_max"]),
        }
        component_errors.extend(components)
        vector_errors.extend(vectors)
        samples.append(
            {
                "image": image,
                "metrics": {**metrics, "movable_atom_count": len(movable)},
                "checks": checks,
                "passed": all(checks.values()),
                "label_sha256": label_ref["report_sha256"],
                "prediction_path": str(prediction_path.resolve()),
                "prediction_sha256": sha256_file(prediction_path),
            }
        )
    aggregate = {
        "sample_count": len(samples),
        "component_mae_eV_per_A": fmean(component_errors),
        "vector_rmse_eV_per_A": math.sqrt(fmean(value * value for value in vector_errors)),
        "vector_max_eV_per_A": max(vector_errors),
    }
    aggregate_checks = {
        "component_mae": aggregate["component_mae_eV_per_A"]
        <= float(thresholds["component_mae_eV_per_A_max"]),
        "vector_rmse": aggregate["vector_rmse_eV_per_A"]
        <= float(thresholds["vector_rmse_eV_per_A_max"]),
        "vector_max": aggregate["vector_max_eV_per_A"]
        <= float(thresholds["vector_max_eV_per_A_max"]),
        "every_selected_image": all(row["passed"] for row in samples),
    }
    passed = all(aggregate_checks.values())
    assessment = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_path_force_agreement",
        "status": "passed" if passed else "failed_needs_force_only_finetuning",
        "source_path_manifest_sha256": current["candidate"]["manifest_sha256"],
        "checkpoint_sha256": current["candidate"]["checkpoint_sha256"],
        "prediction_set_sha256": sha256_file(manifest_path),
        "aggregate_metrics": aggregate,
        "thresholds": thresholds,
        "aggregate_checks": aggregate_checks,
        "samples": samples,
        "local_force_screen_passed": passed,
        "active_learning_converged": False,
        "ts_domain_validated": False,
        "scientifically_validated_ts": False,
        "reportable_final_energy": False,
    }
    assessment_path = write_json(state_path.parent / "path_force_agreement.json", assessment)
    current["force_agreement"] = {
        **assessment,
        "path": str(assessment_path.resolve()),
        "sha256": sha256_file(assessment_path),
    }
    if passed:
        current["status"] = "local_force_screen_passed"
        calibration = state.get("ts_domain_calibration") or {}
        reusable = bool(
            calibration.get("checkpoint_sha256") == current["candidate"]["checkpoint_sha256"]
            and calibration.get("compatibility_sha256") == state["compatibility_sha256"]
        )
        state["status"] = (
            "awaiting_ts_domain_reuse_decision"
            if reusable
            else "awaiting_independent_ts_domain_validation"
        )
        state["next_action"] = (
            "review_TS_domain_scope_committee_or_novelty_and_audit_triggers"
            if reusable
            else "assess_disjoint_held_out_TS_force_validation_set"
        )
    else:
        current["status"] = "fine_tuning_required"
        state["status"] = current["status"]
        state["next_action"] = "prepare_force_only_finetuning_package_from_all_failed_path_labels"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return assessment
