from __future__ import annotations

import shutil

from collections.abc import Callable

from pathlib import Path

from typing import Any

from scripts.aqcat25_calibration import parse_final_outcar, parse_poscar_symbols

from scripts.aqcat25_ts_schema import load_document

from scripts.artifact_io import sha256_file

from scripts.neb_agent.utils_structure import read_poscar

from scripts.scheduler_evidence import query_lsf_job, verify_lsf_evidence_live

from scripts.vasp_inputs import build_fe110_active_learning_force_label

from scripts.vasp_result_gate import final_scf_status, validate_lsf_done_evidence

from .active_learning_common import (
    PREDICTED_CLASS,
    VASP_LABEL_CLASS,
    current_round,
    load_policy,
    load_state,
    read_json,
    utc_now,
    write_json,
)

from .ml_neb_path import validate_gpu_ml_neb_path_manifest

from .active_learning_path_common import _empty_destination, _resolve

ROOT = Path(__file__).resolve().parents[2]

def _prepare_label_request(
    state: dict[str, Any],
    round_record: dict[str, Any],
    selected: dict[str, Any],
    source: Path,
    destination: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    target = destination / "POSCAR"
    shutil.copy2(source, target)
    if sha256_file(target) != selected["structure_sha256"]:
        raise ValueError(f"selected image {selected['image']} structure hash mismatch")
    label_policy = policy["vasp_force_label"]
    profile_path = Path(label_policy["input_profile"])
    if not profile_path.is_absolute():
        profile_path = ROOT / profile_path
    inputs = build_fe110_active_learning_force_label(destination, profile_path=profile_path)
    if inputs["stage"] != label_policy["input_stage"]:
        raise ValueError("active-learning VASP input stage does not match the production profile")
    request = {
        "schema_version": 1,
        "document_kind": "vasp_ts_force_label_request",
        "reaction_id": state["reaction_id"],
        "round_index": round_record["round_index"],
        "candidate_structure_sha256": sha256_file(target),
        "candidate_result_class": PREDICTED_CLASS,
        "requested_backend": label_policy["backend"],
        "scheduler": label_policy["scheduler"],
        "input_profile": {
            "path": inputs["profile_path"],
            "sha256": inputs["profile_sha256"],
            "stage": inputs["stage"],
            "base_profile": inputs["base_profile"],
            "compatibility_incar_source": inputs["compatibility_incar_source"],
            "compatibility_incar": inputs["compatibility_incar"],
            "final_energy_convention": inputs["final_energy_convention"],
        },
        "result_class_after_acceptance": VASP_LABEL_CLASS,
        "reportable_final_energy": False,
        "required_before_execution": [
            "structure_gate_pass",
            "approved_POTCAR",
            "vasp_preflight_pass",
        ],
    }
    request_path = write_json(destination / "label_request.json", request)
    return {
        "image": selected["image"],
        "role": selected["role"],
        "reasons": selected["reasons"],
        "directory": str(destination.resolve()),
        "structure_sha256": selected["structure_sha256"],
        "request_path": str(request_path.resolve()),
        "request_sha256": sha256_file(request_path),
        "status": "prepared_not_submitted",
        "reportable_final": False,
    }

def prepare_path_vasp_force_labels(state_path: Path, destination: Path) -> dict[str, Any]:
    state = load_state(state_path)
    policy = load_policy(Path(state["policy_path"]))
    current = current_round(state)
    if current["status"] != "awaiting_path_vasp_label_preparation":
        raise ValueError("current round is not ready for path VASP label preparation")
    _empty_destination(destination)
    manifest_path = Path(current["candidate"]["manifest_path"])
    if sha256_file(manifest_path) != current["candidate"]["manifest_sha256"]:
        raise ValueError("ML path manifest changed before VASP label preparation")
    manifest = validate_gpu_ml_neb_path_manifest(manifest_path)
    image_rows = {row["image"]: row for row in manifest["images"]}
    labels = []
    try:
        for selected in current["path_selection"]["selected_images"]:
            source = _resolve(manifest_path.parent, image_rows[selected["image"]]["structure_path"])
            labels.append(
                _prepare_label_request(
                    state,
                    current,
                    selected,
                    source,
                    destination / f"image_{selected['image']}",
                    policy,
                )
            )
    except Exception:
        # Keep any prepared directory for diagnosis; state remains unadvanced and retry-safe.
        raise
    batch = {
        "schema_version": 1,
        "document_kind": "vasp_ts_force_label_batch_request",
        "reaction_id": state["reaction_id"],
        "round_index": current["round_index"],
        "source_path_manifest_sha256": current["candidate"]["manifest_sha256"],
        "labels": [
            {
                "image": row["image"],
                "role": row["role"],
                "directory": str(Path(row["directory"]).relative_to(destination)),
                "request_sha256": row["request_sha256"],
                "structure_sha256": row["structure_sha256"],
            }
            for row in labels
        ],
        "submission_policy": {
            "automatic_submission": False,
            "single_bounded_batch_authorization_allowed": True,
            "direct_gpu_to_vasp_handoff": False,
        },
    }
    batch_path = write_json(destination / "path_label_batch_request.json", batch)
    current["path_vasp_force_labels"] = labels
    current["path_label_batch"] = {
        "path": str(batch_path.resolve()),
        "sha256": sha256_file(batch_path),
        "status": "prepared_not_submitted",
    }
    current["status"] = "awaiting_path_vasp_force_label_execution"
    state["status"] = current["status"]
    state["next_action"] = (
        "review_batch_copy_approved_POTCAR_run_preflights_then_request_one_bounded_VASP_batch_authorization"
    )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return batch

def _validated_scheduler(
    evidence_path: Path,
    *,
    required_status: str,
    live_query: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    scheduler = load_document(evidence_path, expected_kind="scheduler_job_evidence")
    validate_lsf_done_evidence(scheduler)
    if scheduler.get("status") != required_status:
        raise ValueError("force label lacks the configured terminal scheduler status")
    live = verify_lsf_evidence_live(
        scheduler, required_status=required_status, live_query=live_query
    )
    return scheduler, live

def _build_label_report(
    state: dict[str, Any],
    current: dict[str, Any],
    label: dict[str, Any],
    evidence_path: Path,
    scheduler: dict[str, Any],
    live_scheduler: dict[str, Any],
) -> dict[str, Any]:
    directory = Path(label["directory"])
    poscar = directory / "POSCAR"
    request_path = directory / "label_request.json"
    if sha256_file(poscar) != label["structure_sha256"]:
        raise ValueError(f"VASP label image {label['image']} structure hash mismatch")
    if not request_path.is_file() or sha256_file(request_path) != label["request_sha256"]:
        raise ValueError(f"VASP label image {label['image']} request hash mismatch")
    parsed = parse_final_outcar(directory / "OUTCAR")
    scf = final_scf_status(directory / "OSZICAR", directory / "INCAR", directory / "OUTCAR")
    symbols = parse_poscar_symbols(poscar)
    structure = read_poscar(poscar)
    fixed = [
        index
        for index, flags in enumerate(structure.flags)
        if tuple(value.upper() for value in flags) == ("F", "F", "F")
    ]
    if len(parsed["forces_eV_per_A"]) != len(symbols):
        raise ValueError(f"VASP label image {label['image']} atom count mismatch")
    if not parsed["normal_completion"]:
        raise ValueError(f"VASP label image {label['image']} did not finish normally")
    if not scf["electronically_converged"]:
        raise ValueError(f"VASP label image {label['image']} is not electronically converged")
    return {
        "schema_version": 1,
        "document_kind": "vasp_ts_force_label",
        "reaction_id": state["reaction_id"],
        "round_index": current["round_index"],
        "contract_sha256": state["contract_sha256"],
        "compatibility_sha256": state["compatibility_sha256"],
        "result_class": VASP_LABEL_CLASS,
        "reportable_final_energy": False,
        "eligible_for_force_only_training": True,
        "scheduler_evidence": {
            **scheduler,
            "path": str(evidence_path.resolve()),
            "sha256": sha256_file(evidence_path),
            "live_recheck": live_scheduler,
        },
        "label_request": {
            "path": str(request_path.resolve()),
            "sha256": label["request_sha256"],
        },
        "structure": {
            "path": str(poscar.resolve()),
            "sha256": sha256_file(poscar),
            "symbols": symbols,
        },
        "fixed_atom_indices_zero_based": fixed,
        "outcar": {
            "path": str((directory / "OUTCAR").resolve()),
            "sha256": sha256_file(directory / "OUTCAR"),
        },
        "oszicar": {
            "path": str((directory / "OSZICAR").resolve()),
            "sha256": sha256_file(directory / "OSZICAR"),
        },
        "normal_completion": True,
        **scf,
        "dft_toten_eV_force_label_only": parsed["final_toten_eV"],
        "forces_eV_per_A": parsed["forces_eV_per_A"],
    }

def ingest_path_vasp_force_labels(
    state_path: Path,
    evidence_manifest_path: Path,
    *,
    live_query: Callable[..., dict[str, Any]] = query_lsf_job,
) -> dict[str, Any]:
    state = load_state(state_path)
    policy = load_policy(Path(state["policy_path"]))
    current = current_round(state)
    if current["status"] != "awaiting_path_vasp_force_label_execution":
        raise ValueError("current round is not awaiting path VASP force labels")
    evidence = read_json(evidence_manifest_path)
    if evidence.get("document_kind") != "vasp_ts_force_label_batch_evidence":
        raise ValueError("invalid VASP force-label batch evidence kind")
    if evidence.get("source_batch_request_sha256") != current["path_label_batch"]["sha256"]:
        raise ValueError("VASP batch evidence is not bound to the prepared request")
    rows = evidence.get("labels")
    by_image = {row.get("image"): row for row in rows if isinstance(row, dict)} if isinstance(rows, list) else {}
    expected = {row["image"] for row in current["path_vasp_force_labels"]}
    if set(by_image) != expected or len(by_image) != len(rows):
        raise ValueError("VASP batch evidence image set mismatch or duplicate")
    prepared: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for label in current["path_vasp_force_labels"]:
        row = by_image[label["image"]]
        evidence_path = _resolve(evidence_manifest_path.parent, str(row.get("scheduler_evidence", "")))
        if not evidence_path.is_file() or sha256_file(evidence_path) != row.get("scheduler_evidence_sha256"):
            raise ValueError(f"scheduler evidence hash mismatch for image {label['image']}")
        scheduler, live = _validated_scheduler(
            evidence_path,
            required_status=policy["vasp_force_label"]["accepted_terminal_status"],
            live_query=live_query,
        )
        report = _build_label_report(state, current, label, evidence_path, scheduler, live)
        prepared.append((label, report))
    reports = []
    for label, report in prepared:
        report_path = write_json(Path(label["directory"]) / "vasp_force_label.json", report)
        label.update(
            {
                "status": "accepted_force_label_only",
                "result_class": VASP_LABEL_CLASS,
                "report_path": str(report_path.resolve()),
                "report_sha256": sha256_file(report_path),
                "reportable_final": False,
            }
        )
        reports.append(
            {
                "image": label["image"],
                "report_path": str(report_path.resolve()),
                "report_sha256": sha256_file(report_path),
            }
        )
    current["status"] = "awaiting_path_ml_prediction_preparation"
    state["status"] = current["status"]
    state["next_action"] = "prepare_exact_structure_MZ73_prediction_batch"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return {
        "document_kind": "vasp_ts_force_label_batch_ingestion",
        "status": "accepted_force_labels_only",
        "reports": reports,
        "reportable_final_energy": False,
    }
