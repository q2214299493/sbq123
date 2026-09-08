from __future__ import annotations

import json
import sqlite3

from scripts.execution_backends import load_execution_backends

from .contract import has_final_energy_compatibility
from .registry import (
    ACCEPTED_COMPATIBLE_FINAL_ENERGY_STATUS,
    ACCEPTED_FINAL_ENERGY_STATUSES,
    ACCEPTED_STATIC_STATUS,
)


_ACCEPTED_SOURCE_STATES = {
    ACCEPTED_STATIC_STATUS: "accepted_matched_static",
    ACCEPTED_COMPATIBLE_FINAL_ENERGY_STATUS: "accepted_compatible_final_energy",
}


def matched_static_rows(
    connection: sqlite3.Connection, result_ids: tuple[str, str, str]
) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT r.*, c.compatibility_fingerprint, c.compatibility_json,
               calc.workflow_status,
               f.calculation_id AS source_calculation_id,
               f.existence_status AS source_existence_status,
               f.sha256 AS source_sha256,
               f.job_record_id AS source_job_record_id,
               j.scheduler AS source_job_scheduler,
               j.server_alias AS source_job_server_alias,
               j.finished_at AS source_job_finished_at,
               h.scheduler_status AS latest_scheduler_status,
               h.scientific_status AS latest_scientific_status,
               h.checked_at AS latest_status_checked_at,
               h.status_event_id AS latest_status_event_id,
               EXISTS(
                   SELECT 1 FROM reviews AS rv
                   WHERE rv.calculation_id=r.calculation_id
                     AND rv.review_type='historical_scheduler_retention_exception'
                     AND rv.decision='accepted'
                     AND rv.reviewer IS NOT NULL
                     AND rv.reviewed_at IS NOT NULL
                     AND rv.evidence IS NOT NULL
               ) AS scheduler_retention_exception
        FROM results AS r
        LEFT JOIN files AS f ON f.file_id=r.source_file_id
        LEFT JOIN jobs AS j ON j.job_record_id=f.job_record_id
        LEFT JOIN job_status_history AS h ON h.status_event_id=(
            SELECT h2.status_event_id
            FROM job_status_history AS h2
            WHERE h2.job_record_id=f.job_record_id
            ORDER BY h2.checked_at DESC, h2.status_event_id DESC
            LIMIT 1
        )
        LEFT JOIN calculation_compatibility AS c ON c.calculation_id=r.calculation_id
        LEFT JOIN calculations AS calc ON calc.calculation_id=r.calculation_id
        WHERE r.result_id IN (?, ?, ?)
        """,
        result_ids,
    ).fetchall()
    by_id = {row["result_id"]: row for row in rows}
    missing = [result_id for result_id in result_ids if result_id not in by_id]
    if missing:
        raise ValueError("final-energy results missing: " + ", ".join(missing))
    return [by_id[result_id] for result_id in result_ids]


def matched_static_convention(rows: list[sqlite3.Row]) -> tuple[str, str]:
    backend = load_execution_backends().vasp
    statuses = {row["validation_status"] for row in rows}
    if len(statuses) != 1 or not statuses <= ACCEPTED_FINAL_ENERGY_STATUSES:
        allowed = ", ".join(sorted(ACCEPTED_FINAL_ENERGY_STATUSES))
        raise ValueError(
            "all three energies must use one accepted validation status: " + allowed
        )
    validation_status = str(next(iter(statuses)))
    scientific_status = _ACCEPTED_SOURCE_STATES[validation_status]

    def accepted_job_evidence(row: sqlite3.Row) -> bool:
        scheduler_done = bool(
            row["latest_scheduler_status"] == "DONE"
            and row["latest_status_checked_at"]
        )
        retained_output_exception = bool(
            row["latest_scheduler_status"] == "UNKNOWN"
            and row["scheduler_retention_exception"] == 1
        )
        return scheduler_done or retained_output_exception

    if any(
        not row["source_job_record_id"]
        or row["source_job_scheduler"] != backend.name
        or row["source_job_server_alias"] != backend.server_alias
        or not accepted_job_evidence(row)
        or row["latest_scientific_status"] != scientific_status
        for row in rows
    ):
        raise ValueError(
            "IS/TS/FS require each source-file-bound configured VASP job "
            f"to have latest scientific status {scientific_status} in the latest "
            "status event, and either retained "
            "DONE evidence or an accepted "
            "historical-scheduler-retention exception with latest scheduler UNKNOWN"
        )
    if any(row["numeric_value"] is None or str(row["unit"]).lower() != "ev" for row in rows):
        raise ValueError("all three final-energy results must be numeric eV values")
    if any(
        row["source_calculation_id"] != row["calculation_id"]
        or row["source_existence_status"] != "confirmed"
        or not row["source_sha256"]
        for row in rows
    ):
        raise ValueError("all three final-energy results require confirmed source files from their calculations")
    conventions = {row["reference_convention"] for row in rows}
    compatibilities = {row["compatibility_fingerprint"] for row in rows}
    if None in conventions or len(conventions) != 1:
        raise ValueError("IS/TS/FS reference conventions do not match")
    if None in compatibilities or len(compatibilities) != 1:
        raise ValueError("IS/TS/FS compatibility branches do not match")
    compatibility_documents = []
    for row in rows:
        try:
            compatibility_documents.append(json.loads(row["compatibility_json"]))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("IS/TS/FS compatibility JSON is missing or invalid") from exc
    if any(not has_final_energy_compatibility(item) for item in compatibility_documents):
        raise ValueError(
            "final barrier compatibility must hash ISMEAR, SIGMA, fixed-atom mask, "
            "LDIPOL, numeric vacuum thickness, and final-energy convention"
        )
    convention = str(next(iter(conventions)))
    if any(item["final_energy_convention"].lower() != convention.lower() for item in compatibility_documents):
        raise ValueError("compatibility final-energy convention does not match the result convention")
    return convention, str(next(iter(compatibilities)))


def barrier_values(rows: list[sqlite3.Row]) -> dict[str, float]:
    initial, saddle, final = (float(row["numeric_value"]) for row in rows)
    values = {
        "forward_barrier_ev": saddle - initial,
        "reverse_barrier_ev": saddle - final,
        "reaction_energy_ev": final - initial,
    }
    if values["forward_barrier_ev"] < 0 or values["reverse_barrier_ev"] < 0:
        raise ValueError("TS final energy lies below an endpoint")
    return values
