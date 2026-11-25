from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.aqcat25_calibration import parse_final_outcar, parse_poscar_symbols
from scripts.aqcat25_ts_schema import load_document
from scripts.artifact_io import sha256_file
from scripts.execution_backends import load_execution_backends
from scripts.neb_agent.utils_structure import read_poscar
from scripts.scheduler_evidence import query_lsf_job, verify_lsf_evidence_live
from scripts.vasp_result_gate import final_scf_status, validate_lsf_done_evidence

from .active_learning_common import (
    VASP_LABEL_CLASS,
    current_round,
    force_metrics,
    load_bound_vasp_label,
    load_policy,
    load_state,
    utc_now,
    write_json,
)
def ingest_vasp_force_label(
    state_path: Path,
    scheduler_evidence_path: Path,
    *,
    live_query: Callable[..., dict[str, Any]] = query_lsf_job,
) -> dict[str, Any]:
    state = load_state(state_path)
    policy = load_policy(Path(state["policy_path"]))
    round_record = current_round(state)
    if round_record["status"] != "awaiting_vasp_force_label_execution":
        raise ValueError("current round is not awaiting a VASP force label")
    label = round_record["vasp_force_label"]
    directory = Path(label["directory"])
    scheduler = load_document(scheduler_evidence_path, expected_kind="scheduler_job_evidence")
    required_status = policy["vasp_force_label"]["accepted_terminal_status"]
    validate_lsf_done_evidence(scheduler)
    if scheduler.get("status") != required_status:
        raise ValueError("force label lacks the configured terminal scheduler status")
    live_scheduler = verify_lsf_evidence_live(
        scheduler, required_status=required_status, live_query=live_query
    )
    poscar = directory / "POSCAR"
    label_request = directory / "label_request.json"
    if not label_request.is_file() or sha256_file(label_request) != label["request_sha256"]:
        raise ValueError("VASP force-label request changed after preparation")
    if sha256_file(poscar) != round_record["candidate"]["structure_sha256"]:
        raise ValueError("VASP force-label POSCAR does not match the ML candidate")
    parsed = parse_final_outcar(directory / "OUTCAR")
    scf = final_scf_status(directory / "OSZICAR", directory / "INCAR", directory / "OUTCAR")
    symbols = parse_poscar_symbols(poscar)
    structure = read_poscar(poscar)
    fixed_indices = [
        index
        for index, flags in enumerate(structure.flags)
        if tuple(value.upper() for value in flags) == ("F", "F", "F")
    ]
    if len(parsed["forces_eV_per_A"]) != len(symbols):
        raise ValueError("VASP force-label atom count does not match POSCAR")
    if not parsed["normal_completion"]:
        raise ValueError("VASP force label did not finish normally")
    if not scf["electronically_converged"]:
        raise ValueError("VASP force label is not electronically converged")
    report = {
        "schema_version": 1,
        "document_kind": "vasp_ts_force_label",
        "reaction_id": state["reaction_id"],
        "round_index": round_record["round_index"],
        "contract_sha256": state["contract_sha256"],
        "compatibility_sha256": state["compatibility_sha256"],
        "result_class": VASP_LABEL_CLASS,
        "reportable_final_energy": False,
        "eligible_for_force_only_training": True,
        "scheduler_evidence": {
            **scheduler,
            "path": str(scheduler_evidence_path.resolve()),
            "sha256": sha256_file(scheduler_evidence_path),
            "live_recheck": live_scheduler,
        },
        "label_request": {
            "path": str(label_request.resolve()),
            "sha256": label["request_sha256"],
        },
        "structure": {"path": str(poscar.resolve()), "sha256": sha256_file(poscar), "symbols": symbols},
        "fixed_atom_indices_zero_based": fixed_indices,
        "outcar": {"path": str((directory / "OUTCAR").resolve()), "sha256": sha256_file(directory / "OUTCAR")},
        "oszicar": {"path": str((directory / "OSZICAR").resolve()), "sha256": sha256_file(directory / "OSZICAR")},
        "normal_completion": True,
        **scf,
        "dft_toten_eV_force_label_only": parsed["final_toten_eV"],
        "forces_eV_per_A": parsed["forces_eV_per_A"],
    }
    report_path = write_json(directory / "vasp_force_label.json", report)
    label.update(
        {
            "status": "accepted_force_label_only",
            "result_class": VASP_LABEL_CLASS,
            "report_path": str(report_path.resolve()),
            "report_sha256": sha256_file(report_path),
            "reportable_final": False,
        }
    )
    registered_jobs = (round_record.get("job_evidence") or {}).get("vasp_force_label", [])
    if registered_jobs and str(registered_jobs[-1].get("job_id")) != str(scheduler["job_id"]):
        raise ValueError("completed VASP label job does not match the registered job evidence")
    round_record["status"] = "awaiting_ml_force_prediction_preparation"
    state["status"] = round_record["status"]
    gpu_backend = load_execution_backends().gpu
    state["next_action"] = (
        f"prepare_hash_bound_{gpu_backend.hostname}_force_prediction_request"
    )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return report


def assess_force_prediction(state_path: Path, prediction_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    policy = load_policy(Path(state["policy_path"]))
    round_record = current_round(state)
    if round_record["status"] != "awaiting_ml_force_prediction_on_exact_label_structure":
        raise ValueError("current round is not awaiting an ML force prediction")
    prediction = load_document(prediction_path, expected_kind="aqcat25_ts_force_prediction")
    candidate = round_record["candidate"]
    request = round_record.get("force_prediction") or {}
    if prediction.get("request_sha256") != request.get("request_sha256"):
        raise ValueError("ML force prediction is not bound to the prepared request")
    if prediction.get("structure_sha256") != candidate["structure_sha256"]:
        raise ValueError("ML force prediction structure hash mismatch")
    if prediction.get("checkpoint_sha256") != candidate["checkpoint_sha256"]:
        raise ValueError("ML force prediction checkpoint mismatch")
    label_ref = round_record["vasp_force_label"]
    label = load_bound_vasp_label(
        Path(label_ref["report_path"]),
        label_ref["report_sha256"],
        contract_sha256=state["contract_sha256"],
        compatibility_sha256=state["compatibility_sha256"],
    )
    fixed = set(label["fixed_atom_indices_zero_based"])
    movable = [index for index in range(len(label["forces_eV_per_A"])) if index not in fixed]
    metrics, _, _ = force_metrics(label["forces_eV_per_A"], prediction["forces_eV_per_A"], movable)
    metrics["movable_atom_count"] = len(movable)
    thresholds = policy["local_force_screen"]
    checks = {
        "component_mae": metrics["component_mae_eV_per_A"] <= float(thresholds["component_mae_eV_per_A_max"]),
        "vector_rmse": metrics["vector_rmse_eV_per_A"] <= float(thresholds["vector_rmse_eV_per_A_max"]),
        "vector_max": metrics["vector_max_eV_per_A"] <= float(thresholds["vector_max_eV_per_A_max"]),
    }
    passed = all(checks.values())
    assessment = {
        "status": "passed" if passed else "failed_needs_force_only_finetuning",
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "prediction_path": str(prediction_path.resolve()),
        "prediction_sha256": sha256_file(prediction_path),
        "local_force_screen_passed": passed,
        "active_learning_converged": False,
        "ts_domain_validated": False,
        "scientifically_validated_ts": False,
        "reportable_final_energy": False,
    }
    round_record["force_agreement"] = assessment
    if passed:
        round_record["status"] = "local_force_screen_passed"
        calibration = state.get("ts_domain_calibration") or {}
        reusable_scope = bool(
            calibration.get("checkpoint_sha256") == candidate["checkpoint_sha256"]
            and calibration.get("compatibility_sha256") == state["compatibility_sha256"]
        )
        state["status"] = (
            "awaiting_ts_domain_reuse_decision"
            if reusable_scope
            else "awaiting_independent_ts_domain_validation"
        )
        state["next_action"] = (
            "review_TS_domain_scope_novelty_and_audit_triggers"
            if reusable_scope
            else "assess_independent_held_out_ts_force_validation_set"
        )
    else:
        round_record["status"] = "fine_tuning_required"
        state["status"] = round_record["status"]
        state["next_action"] = "prepare_force_only_finetuning_package"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return assessment
