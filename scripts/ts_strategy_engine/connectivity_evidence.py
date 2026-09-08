from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_file
from scripts.execution_backends import load_execution_backends


def load_connectivity_report(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(payload["connectivity_report"])
    if not path.is_file():
        raise ValueError("TS connectivity report does not exist")
    actual_sha = sha256_file(path)
    if actual_sha != payload["connectivity_report_sha256"]:
        raise ValueError("TS connectivity report hash mismatch")
    report = load_json_object(path)
    if (
        report.get("document_kind") != "vasp_bidirectional_ts_connectivity"
        or report.get("status") != "PASS"
        or report.get("grade_a_connectivity_eligible") is not True
        or report.get("connects_to_is") is not True
        or report.get("connects_to_fs") is not True
    ):
        raise ValueError("TS connectivity report did not prove both VASP downhill directions")
    if any(
        report.get(key) != payload[key]
        for key in ("contract_sha256", "atom_map_sha256", "compatibility_sha256")
    ):
        raise ValueError("TS connectivity report contract binding mismatch")
    for name in ("source_saddle", "frequency_poscar", "frequency_outcar"):
        reference = report.get(name) or {}
        artifact = Path(str(reference.get("path", "")))
        if not artifact.is_absolute():
            artifact = path.parent / artifact
        if not artifact.is_file() or sha256_file(artifact) != reference.get("sha256"):
            raise ValueError(f"TS connectivity {name} evidence is missing or hash-mismatched")
    if (
        report["source_saddle"]["sha256"] != payload["source_saddle_sha256"]
        or report["frequency_poscar"]["sha256"] != payload["frequency_poscar_sha256"]
    ):
        raise ValueError("TS saddle/frequency structure binding mismatch")
    handoff_path = Path(payload["vfa_handoff"])
    if not handoff_path.is_file() or sha256_file(handoff_path) != payload["vfa_handoff_sha256"]:
        raise ValueError("VFA handoff is missing or hash-mismatched")
    handoff = load_json_object(handoff_path)
    if (
        handoff.get("source_sha256") != payload["source_saddle_sha256"]
        or handoff.get("frequency_poscar_sha256") != payload["frequency_poscar_sha256"]
    ):
        raise ValueError("VFA handoff does not bind the registered saddle and frequency structure")
    return report


def validate_connectivity_jobs(
    connection: sqlite3.Connection, payload: dict[str, Any], report: dict[str, Any]
) -> None:
    backend = load_execution_backends().vasp
    record_ids = (
        payload["positive_connectivity_job_record_id"],
        payload["negative_connectivity_job_record_id"],
    )
    rows = connection.execute(
        """
        SELECT j.job_record_id, j.scheduler_job_id, j.scheduler, j.server_alias, j.finished_at,
               (SELECT h.scheduler_status
                FROM job_status_history AS h
                WHERE h.job_record_id=j.job_record_id
                ORDER BY h.checked_at DESC, h.status_event_id DESC LIMIT 1) AS latest_status
        FROM jobs AS j WHERE j.job_record_id IN (?, ?)
        """,
        record_ids,
    ).fetchall()
    by_id = {row["job_record_id"]: row for row in rows}
    branches = {branch["direction"]: branch for branch in report.get("branches", [])}
    for direction, record_id in zip(("positive", "negative"), record_ids):
        row = by_id.get(record_id)
        branch = branches.get(direction)
        if (
            row is None
            or branch is None
            or row["scheduler"] != backend.name
            or row["server_alias"] != backend.server_alias
            or str(row["scheduler_job_id"]) != str(branch.get("job_id"))
            or row["finished_at"] is None
            or row["latest_status"] != "DONE"
        ):
            raise ValueError(f"{direction} connectivity job lacks latest authoritative DONE evidence")


def validate_source_saddle_job(
    connection: sqlite3.Connection, payload: dict[str, Any]
) -> None:
    backend = load_execution_backends().vasp
    row = connection.execute(
        """
        SELECT j.calculation_id, j.scheduler, j.server_alias, j.finished_at,
               (SELECT h.scheduler_status FROM job_status_history AS h
                WHERE h.job_record_id=j.job_record_id
                ORDER BY h.checked_at DESC, h.status_event_id DESC LIMIT 1) AS latest_status,
               (SELECT h.checked_at FROM job_status_history AS h
                WHERE h.job_record_id=j.job_record_id
                ORDER BY h.checked_at DESC, h.status_event_id DESC LIMIT 1) AS latest_checked_at
        FROM jobs AS j WHERE j.job_record_id=?
        """,
        (payload["source_job_record_id"],),
    ).fetchone()
    if (
        row is None
        or row["calculation_id"] != payload["source_saddle_calculation_id"]
        or row["scheduler"] != backend.name
        or row["server_alias"] != backend.server_alias
        or row["latest_status"] != "DONE"
        or row["latest_checked_at"] is None
    ):
        raise ValueError(
            "source saddle job lacks latest authoritative configured VASP DONE evidence"
        )


def validate_ts_evidence_files(connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
    expected = {payload["frequency_output_file_id"]: "frequency_output"}
    if str(payload.get("source_method", "")).lower() != "dimer":
        expected.update(
            {
                payload["positive_displacement_file_id"]: "mode_positive_displacement",
                payload["negative_displacement_file_id"]: "mode_negative_displacement",
                payload["connectivity_report_file_id"]: "bidirectional_connectivity_report",
            }
        )
    placeholders = ", ".join("?" for _ in expected)
    rows = connection.execute(
        "SELECT file_id, calculation_id, role, existence_status, sha256 "
        f"FROM files WHERE file_id IN ({placeholders})",
        tuple(expected),
    ).fetchall()
    evidence = {row["file_id"]: row for row in rows}
    invalid = any(
        file_id not in evidence
        or evidence[file_id]["calculation_id"] != payload["validation_calculation_id"]
        or evidence[file_id]["role"] != role
        or evidence[file_id]["existence_status"] != "confirmed"
        or not evidence[file_id]["sha256"]
        for file_id, role in expected.items()
    )
    if invalid:
        raise ValueError("TS validation file evidence is missing, unconfirmed, or has the wrong role")
    if (
        str(payload.get("source_method", "")).lower() != "dimer"
        and evidence[payload["connectivity_report_file_id"]]["sha256"]
        != payload["connectivity_report_sha256"]
    ):
        raise ValueError("registered connectivity report hash does not match the analyzed report")
