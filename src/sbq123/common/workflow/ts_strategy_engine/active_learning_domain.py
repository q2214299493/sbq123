from __future__ import annotations

import math
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml

from scripts.aqcat25_ts_schema import load_document
from scripts.artifact_io import sha256_file, sha256_json
from scripts.neb_agent.utils_structure import read_poscar

from .active_learning_common import (
    current_round,
    force_metrics,
    load_bound_vasp_label,
    load_policy,
    load_state,
    read_json,
    utc_now,
    write_json,
)


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[position]


def _load_gate(policy_path: Path, policy: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    configured = Path(policy["ts_domain_validation"]["gate"])
    root = policy_path.resolve().parents[1]
    path = configured if configured.is_absolute() else root / configured
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("invalid AQCat25 TS domain gate")
    return path, payload


def _geometry_fingerprint(path: Path) -> str:
    structure = read_poscar(path)
    fixed = [
        index
        for index, flags in enumerate(structure.flags)
        if structure.selective and tuple(value.upper() for value in flags) == ("F", "F", "F")
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


def _training_structure_evidence(
    policy_path: Path, policy: dict[str, Any], state: dict[str, Any]
) -> tuple[set[str], set[str]]:
    hashes = {record["candidate"]["structure_sha256"] for record in state["rounds"]}
    geometries = {
        _geometry_fingerprint(Path(record["candidate"]["structure_path"]))
        for record in state["rounds"]
    }
    for record in state["rounds"]:
        for label_ref in record.get("path_vasp_force_labels") or []:
            if label_ref.get("status") != "accepted_force_label_only":
                continue
            report = load_bound_vasp_label(
                Path(label_ref["report_path"]),
                label_ref["report_sha256"],
                contract_sha256=state["contract_sha256"],
                compatibility_sha256=state["compatibility_sha256"],
            )
            structure_path = Path(report["structure"]["path"])
            hashes.add(report["structure"]["sha256"])
            geometries.add(_geometry_fingerprint(structure_path))
    replay_path = _resolve(
        policy_path.resolve().parents[1], policy["fine_tuning"]["replay"]["labels"]
    )
    replay = read_json(replay_path)
    structures_root = _resolve(
        policy_path.resolve().parents[1], policy["fine_tuning"]["replay"]["structures"]
    )
    for sample in replay.get("samples", []):
        structure_sha = str(sample.get("structure_sha256", ""))
        if len(structure_sha) == 64:
            hashes.add(structure_sha)
            geometries.add(_geometry_fingerprint(structures_root / f"{sample['sample_id']}.vasp"))
    return hashes, geometries


def _register_sample_id(sample: dict[str, Any], sample_ids: set[str]) -> str:
    sample_id = str(sample.get("sample_id", ""))
    if not sample_id or sample_id in sample_ids:
        raise ValueError("independent TS validation sample IDs must be unique and nonempty")
    sample_ids.add(sample_id)
    return sample_id


def _register_validation_hash(
    structure_sha: str,
    geometry_sha: str,
    training_hashes: set[str],
    training_geometries: set[str],
    validation_hashes: set[str],
    validation_geometries: set[str],
) -> None:
    if structure_sha in training_hashes:
        raise ValueError("independent TS validation structure overlaps active-learning training structures")
    if structure_sha in validation_hashes:
        raise ValueError("independent TS validation contains a duplicate structure hash")
    if geometry_sha in training_geometries:
        raise ValueError("independent TS validation geometry overlaps training or replay data")
    if geometry_sha in validation_geometries:
        raise ValueError("independent TS validation contains duplicate geometry")
    validation_hashes.add(structure_sha)
    validation_geometries.add(geometry_sha)


def assess_independent_ts_domain(state_path: Path, manifest_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    current = current_round(state)
    if state["status"] != "awaiting_independent_ts_domain_validation":
        raise ValueError("workflow is not awaiting independent TS-domain validation")
    policy_path = Path(state["policy_path"])
    policy = load_policy(policy_path)
    gate_path, gate = _load_gate(policy_path, policy)
    manifest = load_document(
        manifest_path, expected_kind="aqcat25_ts_independent_validation_set"
    )
    checkpoint_sha = current["candidate"]["checkpoint_sha256"]
    if manifest.get("checkpoint_sha256") != checkpoint_sha:
        raise ValueError("validation manifest checkpoint does not match the active candidate")
    if manifest.get("compatibility_sha256") != state["compatibility_sha256"]:
        raise ValueError("validation manifest compatibility mismatch")
    samples = manifest.get("samples")
    base = manifest_path.parent
    training_hashes, training_geometries = _training_structure_evidence(
        policy_path, policy, state
    )
    validation_hashes: set[str] = set()
    validation_geometries: set[str] = set()
    sample_ids: set[str] = set()
    roles: set[str] = set()
    component_errors: list[float] = []
    vector_errors: list[float] = []
    sample_reports: list[dict[str, Any]] = []
    for sample in samples:
        sample_id = _register_sample_id(sample, sample_ids)
        role = str(sample.get("role", ""))
        label_path = _resolve(base, str(sample.get("label", "")))
        prediction_path = _resolve(base, str(sample.get("prediction", "")))
        label = load_bound_vasp_label(
            label_path,
            sample["label_sha256"],
            contract_sha256=state["contract_sha256"],
            compatibility_sha256=state["compatibility_sha256"],
        )
        prediction = load_document(
            prediction_path, expected_kind="aqcat25_ts_force_prediction"
        )
        if sha256_file(prediction_path) != sample["prediction_sha256"]:
            raise ValueError("independent validation prediction hash mismatch")
        structure_sha = (label.get("structure") or {}).get("sha256")
        structure_path = Path(label["structure"]["path"])
        if not structure_path.is_absolute():
            structure_path = label_path.parent / structure_path
        geometry_sha = _geometry_fingerprint(structure_path)
        _register_validation_hash(
            structure_sha,
            geometry_sha,
            training_hashes,
            training_geometries,
            validation_hashes,
            validation_geometries,
        )
        if prediction.get("structure_sha256") != structure_sha:
            raise ValueError("independent validation prediction/label structure mismatch")
        if prediction.get("checkpoint_sha256") != checkpoint_sha:
            raise ValueError("independent validation used the wrong checkpoint")
        fixed = set(label.get("fixed_atom_indices_zero_based") or [])
        movable = [index for index in range(len(label["forces_eV_per_A"])) if index not in fixed]
        metrics, sample_components, sample_vectors = force_metrics(
            label["forces_eV_per_A"], prediction["forces_eV_per_A"], movable
        )
        component_errors.extend(sample_components)
        vector_errors.extend(sample_vectors)
        roles.add(role)
        sample_reports.append(
            {
                "sample_id": sample_id,
                "role": role,
                "structure_sha256": structure_sha,
                "geometry_sha256": geometry_sha,
                "label_sha256": sha256_file(label_path),
                "prediction_sha256": sha256_file(prediction_path),
                "metrics": metrics,
            }
        )
    requirements = gate["independent_validation"]
    missing_roles = sorted(set(requirements["required_roles"]) - roles)
    enough_samples = len(samples) >= int(requirements["minimum_samples"])
    metrics = {
        "sample_count": len(samples),
        "component_mae_eV_per_A": fmean(component_errors),
        "vector_rmse_eV_per_A": math.sqrt(fmean(value * value for value in vector_errors)),
        "vector_p95_eV_per_A": _percentile(vector_errors, 0.95),
        "vector_max_eV_per_A": max(vector_errors),
    }
    state_calibration = state.get("ts_domain_calibration") or {}
    state_calibration_matches = bool(
        state_calibration.get("checkpoint_sha256") == checkpoint_sha
        and state_calibration.get("compatibility_sha256") == state["compatibility_sha256"]
        and isinstance(state_calibration.get("force_acceptance"), dict)
    )
    gate_calibrated = gate.get("status") == "calibrated" and isinstance(
        gate.get("force_acceptance"), dict
    )
    calibrated = gate_calibrated or state_calibration_matches
    thresholds = (
        state_calibration["force_acceptance"]
        if state_calibration_matches
        else gate.get("force_acceptance")
    )
    checks: dict[str, bool] = {"minimum_samples": enough_samples, "required_roles": not missing_roles}
    if calibrated:
        checks.update(
            component_mae=metrics["component_mae_eV_per_A"] <= float(thresholds["component_mae_eV_per_A_max"]),
            vector_rmse=metrics["vector_rmse_eV_per_A"] <= float(thresholds["vector_rmse_eV_per_A_max"]),
            vector_p95=metrics["vector_p95_eV_per_A"] <= float(thresholds["vector_p95_eV_per_A_max"]),
            vector_max=metrics["vector_max_eV_per_A"] <= float(thresholds["vector_max_eV_per_A_max"]),
        )
    passed = calibrated and all(checks.values())
    bootstrap_ready = not calibrated and all(checks.values())
    assessment = {
        "schema_version": 1,
        "document_kind": "aqcat25_ts_domain_assessment",
        "status": "passed" if passed else "bootstrap_passed" if bootstrap_ready else "failed",
        "calibration_id": state_calibration.get("calibration_id")
        if state_calibration_matches
        else gate.get("calibration_id"),
        "gate_path": str(gate_path.resolve()),
        "gate_sha256": sha256_file(gate_path),
        "checkpoint_sha256": checkpoint_sha,
        "metrics": metrics,
        "thresholds": thresholds or {},
        "checks": checks,
        "missing_roles": missing_roles,
        "independence": {
            "training_and_replay_hash_count": len(training_hashes),
            "unique_validation_structure_count": len(validation_hashes),
            "unique_validation_geometry_count": len(validation_geometries),
            "exact_hash_overlap": False,
            "geometry_overlap": False,
        },
        "samples": sample_reports,
        "ts_domain_validated": passed,
        "active_learning_converged": passed,
        "scientifically_validated_ts": False,
        "reportable_final_energy": False,
    }
    report_path = write_json(state_path.parent / "ts_domain_assessment.json", assessment)
    current["ts_domain_assessment"] = {
        "path": str(report_path.resolve()),
        "sha256": sha256_file(report_path),
        "status": assessment["status"],
    }
    if passed:
        current["status"] = "independent_ts_domain_validation_passed"
        state["status"] = "ml_acceleration_ready_for_vasp_refinement"
        state["next_action"] = "work_review_then_VASP_NEB_CI_NEB_or_DIMER"
    elif bootstrap_ready:
        current["status"] = "bootstrap_ts_domain_metrics_ready"
        state["status"] = "awaiting_ts_domain_calibration_review"
        state["next_action"] = "review_and_register_bootstrap_TS_domain_calibration"
    else:
        state["status"] = "independent_ts_domain_validation_failed"
        state["next_action"] = "force_only_finetuning_or_model_rejection_required"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return assessment
