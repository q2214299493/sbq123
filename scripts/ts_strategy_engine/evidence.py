from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import (
    ACCEPTED_FINAL_ENERGY_STATUSES,
    compatibility_fingerprint,
    open_registry,
    utc_now,
)
from .connectivity_evidence import (
    load_connectivity_report,
    validate_connectivity_jobs,
    validate_source_saddle_job,
    validate_ts_evidence_files,
)
from .matched_static_evidence import barrier_values, matched_static_convention, matched_static_rows
from .execution_gate import require_action
from .templates import record_template_in_connection
from scripts.artifact_io import sha256_json


def register_calculation_compatibility(
    database: Path,
    calculation_id: str,
    compatibility: dict[str, Any],
    reviewer: str,
    reviewed_at: str,
) -> str:
    fingerprint = compatibility_fingerprint(compatibility)
    with open_registry(database, migrate=True) as connection:
        connection.execute(
            """
            INSERT INTO calculation_compatibility
            (calculation_id, compatibility_fingerprint, compatibility_json, reviewer, reviewed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(calculation_id) DO UPDATE SET
                compatibility_fingerprint=excluded.compatibility_fingerprint,
                compatibility_json=excluded.compatibility_json,
                reviewer=excluded.reviewer,
                reviewed_at=excluded.reviewed_at
            """,
            (calculation_id, fingerprint, json.dumps(compatibility, sort_keys=True), reviewer, reviewed_at),
        )
    return fingerprint


def _endpoint_errors(
    name: str, endpoint: dict[str, str], item: dict[str, Any], compatibility_sha256: str
) -> list[str]:
    checks = (
        (item["calculation_id"] != endpoint["calculation_id"], "static_result_calculation_mismatch"),
        (item["structure_calculation_id"] != endpoint["calculation_id"], "structure_calculation_mismatch"),
        (
            item["validation_status"] not in ACCEPTED_FINAL_ENERGY_STATUSES,
            "energy_result_not_accepted_compatible_final_energy",
        ),
        (item["numeric_value"] is None or str(item["unit"]).lower() != "ev", "static_result_missing_ev"),
        (not item["reference_convention"], "static_result_missing_reference_convention"),
        (
            not item["source_file_id"]
            or item["source_calculation_id"] != endpoint["calculation_id"]
            or item["source_existence_status"] != "confirmed",
            "static_result_source_file_not_confirmed",
        ),
        (item["existence_status"] != "confirmed", "structure_file_not_confirmed"),
        (not item["structure_sha256"], "structure_file_missing_sha256"),
        (not item["source_sha256"], "static_result_source_file_missing_sha256"),
        (item["compatibility_fingerprint"] != compatibility_sha256, "compatibility_branch_mismatch"),
    )
    return [f"{name}:{message}" for failed, message in checks if failed]


def validate_endpoint_evidence(database: Path, contract: dict[str, Any]) -> dict[str, Any]:
    if not database.is_file():
        return {"status": "STOP", "errors": [f"registry_database_missing:{database}"], "endpoints": {}}
    errors: list[str] = []
    details: dict[str, Any] = {}
    with open_registry(database) as connection:
        for name in ("initial", "final"):
            endpoint = contract["endpoints"][name]
            row = connection.execute(
                """
                SELECT r.result_id, r.calculation_id, r.numeric_value, r.unit,
                       r.reference_convention, r.validation_status, r.source_file_id,
                       f.file_id AS structure_file_id, f.calculation_id AS structure_calculation_id,
                       f.existence_status, f.sha256 AS structure_sha256, c.compatibility_fingerprint,
                       sf.calculation_id AS source_calculation_id,
                       sf.existence_status AS source_existence_status,
                       sf.sha256 AS source_sha256
                FROM results AS r
                JOIN files AS f ON f.file_id=?
                LEFT JOIN files AS sf ON sf.file_id=r.source_file_id
                LEFT JOIN calculation_compatibility AS c ON c.calculation_id=r.calculation_id
                WHERE r.result_id=?
                """,
                (endpoint["structure_file_id"], endpoint["static_result_id"]),
            ).fetchone()
            if row is None:
                errors.append(f"{name}:registered_structure_or_static_result_missing")
                continue
            details[name] = dict(row)
            errors.extend(_endpoint_errors(name, endpoint, details[name], contract["compatibility_sha256"]))
    if {"initial", "final"} <= details.keys():
        if details["initial"]["reference_convention"] != details["final"]["reference_convention"]:
            errors.append("endpoint_reference_convention_mismatch")
    return {"status": "PASS" if not errors else "STOP", "errors": errors, "endpoints": details}


def record_matched_static_barrier(
    database: Path,
    *,
    gate_decision: Path,
    gate_state_sha256: str,
    barrier_set_id: str,
    reaction_id: str,
    source_calculation_id: str,
    ts_validation_id: str,
    initial_result_id: str,
    ts_result_id: str,
    final_result_id: str,
    learning_record: dict[str, Any],
    notes: str | None = None,
) -> dict[str, float | str]:
    decision = require_action(gate_decision, "REPORT_FINAL_BARRIER", gate_state_sha256)
    expected_claim = {
        "barrier_set_id": barrier_set_id,
        "reaction_id": reaction_id,
        "source_calculation_id": source_calculation_id,
        "ts_validation_id": ts_validation_id,
        "initial_result_id": initial_result_id,
        "ts_result_id": ts_result_id,
        "final_result_id": final_result_id,
    }
    if decision["EVIDENCE"]["validation"].get("barrier_claim") != expected_claim:
        raise ValueError("authoritative gate is not bound to this final barrier claim")
    result_ids = (initial_result_id, ts_result_id, final_result_id)
    expected_learning_links = {
        "outcome": "success",
        "validation_grade": "A",
        "source_calculation_id": source_calculation_id,
        "ts_validation_id": ts_validation_id,
        "barrier_set_id": barrier_set_id,
    }
    learning_link_errors = [
        key
        for key, expected in expected_learning_links.items()
        if learning_record.get(key) != expected
    ]
    if learning_link_errors:
        raise ValueError(
            "learning record is not bound to this successful Grade-A barrier: "
            + ", ".join(learning_link_errors)
        )
    with open_registry(database, migrate=True) as connection:
        validation = connection.execute(
            "SELECT * FROM ts_validations WHERE ts_validation_id=?", (ts_validation_id,)
        ).fetchone()
        if validation is None or validation["grade"] != "A" or validation["kinetic_eligible"] != 1:
            raise ValueError("final barrier requires a Grade-A kinetic-eligible TS validation")
        if validation["source_saddle_calculation_id"] != source_calculation_id:
            raise ValueError("barrier source calculation does not match the validated saddle calculation")
        rows = matched_static_rows(connection, result_ids)
        convention, compatibility = matched_static_convention(rows)
        if validation["compatibility_fingerprint"] != compatibility:
            raise ValueError("TS validation and final-energy IS/TS/FS compatibility fingerprints do not match")
        values = barrier_values(rows)
        connection.execute(
            """
            INSERT INTO ts_barriers
            (barrier_set_id, reaction_id, source_calculation_id, ts_validation_id,
             initial_result_id, ts_result_id, final_result_id, compatibility_fingerprint,
             energy_convention, forward_barrier_ev, reverse_barrier_ev, reaction_energy_ev,
             validation_status, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?)
            """,
            (
                barrier_set_id,
                reaction_id,
                source_calculation_id,
                ts_validation_id,
                *result_ids,
                compatibility,
                convention,
                values["forward_barrier_ev"],
                values["reverse_barrier_ev"],
                values["reaction_energy_ev"],
                utc_now(),
                notes,
            ),
        )
        template_id = record_template_in_connection(connection, learning_record)
    return {"barrier_set_id": barrier_set_id, "template_id": template_id, **values}


VALIDATION_REQUIRED = (
    "validation_calculation_id",
    "source_saddle_calculation_id",
    "source_job_record_id",
    "source_method",
    "frequency_output_file_id",
    "vfa_handoff",
    "vfa_handoff_sha256",
    "source_saddle_sha256",
    "frequency_poscar_sha256",
    "contract_sha256",
    "atom_map_sha256",
    "compatibility_sha256",
    "grade",
    "kinetic_eligible",
)

CONNECTIVITY_REQUIRED = (
    "positive_displacement_file_id",
    "negative_displacement_file_id",
    "connectivity_report_file_id",
    "positive_connectivity_job_record_id",
    "negative_connectivity_job_record_id",
    "connectivity_report",
    "connectivity_report_sha256",
)


def _validate_ts_payload(payload: dict[str, Any]) -> None:
    source_method = str(payload.get("source_method", "")).lower()
    required = (
        VALIDATION_REQUIRED
        if source_method == "dimer"
        else (*VALIDATION_REQUIRED, *CONNECTIVITY_REQUIRED)
    )
    missing = [
        field
        for field in required
        if not payload.get(field) and payload.get(field) is not False
    ]
    if missing:
        raise ValueError("validation record missing: " + ", ".join(missing))
    method_evidence_complete = bool(
        payload.get("dimer_technical_acceptance") is True
        if source_method == "dimer"
        else (
            payload.get("connects_to_is") is True
            and payload.get("connects_to_fs") is True
            and payload.get("connectivity_status") == "PASS"
        )
    )
    grade_a_complete = bool(
        payload.get("kinetic_eligible")
        and source_method in {"neb", "ci_neb", "dimer"}
        and payload.get("imaginary_frequency_count") == 1
        and payload.get("principal_mode_assignment") == "accepted"
        and payload.get("geometry_status") == "pass"
        and method_evidence_complete
        and payload.get("reviewer")
        and payload.get("reviewed_at")
    )
    if payload["grade"] == "A" and not grade_a_complete:
        raise ValueError("Grade-A validation evidence is incomplete")


def record_ts_validation(
    database: Path,
    ts_validation_id: str,
    payload: dict[str, Any],
    *,
    gate_decision: Path,
    gate_state_sha256: str,
) -> str:
    decision = require_action(gate_decision, "APPROVE_TS_CANDIDATE", gate_state_sha256)
    if sha256_json(decision["EVIDENCE"]["validation"]) != sha256_json(payload):
        raise ValueError("authoritative gate is not bound to this TS validation payload")
    _validate_ts_payload(payload)
    source_method = str(payload.get("source_method", "")).lower()
    connectivity_report = (
        None if source_method == "dimer" else load_connectivity_report(payload)
    )
    values = {
        "ts_validation_id": ts_validation_id,
        "calculation_id": payload["validation_calculation_id"],
        "source_saddle_calculation_id": payload["source_saddle_calculation_id"],
        "source_method": payload["source_method"],
        "source_job_record_id": payload.get("source_job_record_id"),
        "frequency_output_file_id": payload["frequency_output_file_id"],
        "positive_displacement_file_id": payload.get("positive_displacement_file_id"),
        "negative_displacement_file_id": payload.get("negative_displacement_file_id"),
        "connectivity_report_file_id": payload.get("connectivity_report_file_id"),
        "positive_connectivity_job_record_id": payload.get("positive_connectivity_job_record_id"),
        "negative_connectivity_job_record_id": payload.get("negative_connectivity_job_record_id"),
        "connectivity_report_sha256": payload.get("connectivity_report_sha256"),
        "contract_sha256": payload["contract_sha256"],
        "atom_map_sha256": payload["atom_map_sha256"],
        "compatibility_fingerprint": payload["compatibility_sha256"],
        "imaginary_frequency_count": payload.get("imaginary_frequency_count"),
        "imaginary_frequencies_cm1": json.dumps(payload.get("imaginary_frequencies_cm1", [])),
        "principal_mode_assignment": payload.get("principal_mode_assignment"),
        "soft_mode_assessment": payload.get("soft_mode_assessment"),
        "geometry_status": payload.get("geometry_status"),
        "connects_to_is": _optional_bool(payload.get("connects_to_is")),
        "connects_to_fs": _optional_bool(payload.get("connects_to_fs")),
        "grade": payload["grade"],
        "kinetic_eligible": int(bool(payload["kinetic_eligible"])),
        "reviewed_at": payload.get("reviewed_at"),
        "reviewer": payload.get("reviewer"),
        "notes": payload.get("notes"),
    }
    with open_registry(database, migrate=True) as connection:
        validate_ts_evidence_files(connection, payload)
        validate_source_saddle_job(connection, payload)
        if connectivity_report is not None:
            validate_connectivity_jobs(connection, payload, connectivity_report)
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        connection.execute(
            f"INSERT INTO ts_validations ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    return ts_validation_id


def _optional_bool(value: Any) -> int | None:
    return int(bool(value)) if value is not None else None
