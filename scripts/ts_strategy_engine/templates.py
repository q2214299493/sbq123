from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .registry import compatibility_fingerprint, open_registry, table_exists, utc_now


JSON_FIELDS = {
    "fingerprint": "fingerprint_json",
    "waypoint_strategy": "waypoint_strategy_json",
    "neb_settings": "neb_settings_json",
    "dimer_usage": "dimer_usage_json",
    "convergence_history": "convergence_history_json",
    "failure_cases": "failure_cases_json",
}

NONTRANSFERABLE_STRATEGY_KEYS = {
    "atom_index",
    "atom_indices",
    "barrier_ev",
    "coordinates",
    "energy_ev",
    "image_index",
    "image_number",
    "initial_images",
    "internal_images",
    "job_id",
    "modecar",
    "source_image",
    "source_neighbor_images",
}

EVIDENCE_COLUMNS = """
    v.source_method AS validation_source_method,
    v.grade AS evidence_grade,
    v.kinetic_eligible,
    v.imaginary_frequency_count,
    v.geometry_status,
    v.connects_to_is,
    v.connects_to_fs,
    v.reviewer AS validation_reviewer,
    v.reviewed_at AS validation_reviewed_at,
    v.source_saddle_calculation_id,
    v.contract_sha256 AS validation_contract_sha256,
    v.atom_map_sha256 AS validation_atom_map_sha256,
    v.compatibility_fingerprint AS validation_compatibility,
    vf.role AS frequency_role,
    vf.existence_status AS frequency_existence_status,
    vf.sha256 AS frequency_sha256,
    pf.role AS positive_displacement_role,
    pf.existence_status AS positive_displacement_existence_status,
    pf.sha256 AS positive_displacement_sha256,
    nf.role AS negative_displacement_role,
    nf.existence_status AS negative_displacement_existence_status,
    nf.sha256 AS negative_displacement_sha256,
    b.validation_status AS barrier_status,
    b.forward_barrier_ev AS evidence_barrier_ev,
    b.compatibility_fingerprint AS barrier_compatibility,
    b.ts_validation_id AS barrier_validation_id,
    f.calculation_id AS structure_calculation_id,
    f.role AS structure_role,
    f.existence_status AS structure_existence_status,
    f.sha256 AS structure_sha256
"""

EVIDENCE_JOINS = """
    LEFT JOIN ts_validations AS v ON v.ts_validation_id=t.ts_validation_id
    LEFT JOIN ts_barriers AS b ON b.barrier_set_id=t.barrier_set_id
    LEFT JOIN files AS f ON f.file_id=t.ts_structure_file_id
    LEFT JOIN files AS vf ON vf.file_id=v.frequency_output_file_id
    LEFT JOIN files AS pf ON pf.file_id=v.positive_displacement_file_id
    LEFT JOIN files AS nf ON nf.file_id=v.negative_displacement_file_id
"""


def _decode_json_fields(item: dict[str, Any]) -> None:
    for output, source in JSON_FIELDS.items():
        item[output] = json.loads(item.pop(source))


def _evidence_valid(item: dict[str, Any]) -> bool:
    expected = compatibility_fingerprint(item.get("fingerprint", {}).get("compatibility", {}))
    source_method = str(item.get("validation_source_method", "")).lower()
    method_evidence_valid = (
        source_method == "dimer"
        or (
            item.get("connects_to_is") == 1
            and item.get("connects_to_fs") == 1
            and _file_valid(item, "positive_displacement", "mode_positive_displacement")
            and _file_valid(item, "negative_displacement", "mode_negative_displacement")
        )
    )
    checks = (
        item.get("outcome") == "success",
        item.get("validation_grade") == "A",
        item.get("evidence_grade") == "A",
        item.get("kinetic_eligible") == 1,
        item.get("imaginary_frequency_count") == 1,
        str(item.get("geometry_status", "")).lower() == "pass",
        method_evidence_valid,
        bool(item.get("validation_reviewer") and item.get("validation_reviewed_at")),
        item.get("source_saddle_calculation_id") == item.get("source_calculation_id"),
        item.get("validation_atom_map_sha256") == item.get("fingerprint", {}).get("atom_map_sha256"),
        item.get("validation_compatibility") == expected,
        _file_valid(item, "frequency", "frequency_output"),
        item.get("barrier_status") == "accepted",
        item.get("barrier_validation_id") == item.get("ts_validation_id"),
        item.get("barrier_compatibility") == expected,
        item.get("structure_calculation_id") == item.get("source_calculation_id"),
        item.get("structure_role") == "ts_structure",
        item.get("structure_existence_status") == "confirmed",
        bool(item.get("structure_sha256")),
    )
    return all(checks)


def _file_valid(item: dict[str, Any], prefix: str, role: str) -> bool:
    return bool(
        item.get(f"{prefix}_role") == role
        and item.get(f"{prefix}_existence_status") == "confirmed"
        and item.get(f"{prefix}_sha256")
    )


def load_templates(database: Path, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    if not database.is_file():
        if allow_empty:
            return []
        raise ValueError(f"registry database not found: {database}")
    with open_registry(database) as connection:
        if not table_exists(connection, "ts_strategy_templates"):
            raise ValueError("ts_strategy_templates table is missing")
        rows = connection.execute(
            f"""
            SELECT t.*, {EVIDENCE_COLUMNS}
            FROM ts_strategy_templates AS t
            {EVIDENCE_JOINS}
            ORDER BY t.updated_at DESC, t.template_id
            """
        ).fetchall()
    templates: list[dict[str, Any]] = []
    invalid: list[str] = []
    for row in rows:
        item = dict(row)
        try:
            _decode_json_fields(item)
        except (TypeError, json.JSONDecodeError):
            invalid.append(str(item.get("template_id")))
            continue
        item["evidence_valid"] = _evidence_valid(item)
        templates.append(item)
    if invalid:
        raise ValueError("invalid template JSON rows: " + ", ".join(invalid))
    return templates


def validate_record(record: dict[str, Any]) -> None:
    required = {
        "template_id",
        "reaction_family",
        "fingerprint",
        "waypoint_strategy",
        "interpolation_strategy",
        "neb_settings",
        "dimer_usage",
        "convergence_history",
        "failure_cases",
        "outcome",
        "validation_grade",
        "source_calculation_id",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise ValueError("missing template fields: " + ", ".join(missing))
    if record["outcome"] not in {"success", "failure"}:
        raise ValueError("outcome must be success or failure")
    if record["validation_grade"] not in {"A", "B", "C", "Ungraded"}:
        raise ValueError("invalid validation_grade")
    if not isinstance(record["fingerprint"], dict) or not record["fingerprint"].get("compatibility"):
        raise ValueError("fingerprint.compatibility is required")
    if not isinstance(record["waypoint_strategy"], list) or not record["waypoint_strategy"]:
        raise ValueError("waypoint_strategy must be a non-empty list")
    has_bond_change = bool(record["fingerprint"].get("broken_bonds") or record["fingerprint"].get("formed_bonds"))
    if has_bond_change and record["interpolation_strategy"] not in {"segmented_idpp", "constrained_idpp"}:
        raise ValueError("bond-changing templates require segmented_idpp or constrained_idpp")
    if record["outcome"] == "success" and (
        record["validation_grade"] != "A"
        or not record.get("ts_structure_file_id")
        or not record.get("ts_validation_id")
        or not record.get("barrier_set_id")
    ):
        raise ValueError("successful templates require Grade A, TS structure, validation, and matched-static barrier IDs")
    if record["outcome"] == "failure" and (
        not record["failure_cases"] or not record.get("correction_strategy")
    ):
        raise ValueError("failed experience requires failure_cases and correction_strategy")
    for field in ("waypoint_strategy", "neb_settings", "dimer_usage"):
        forbidden = _find_nontransferable_strategy_keys(record[field])
        if forbidden:
            raise ValueError(
                f"{field} contains non-transferable system-specific keys: "
                + ", ".join(sorted(forbidden))
            )


def _find_nontransferable_strategy_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = {
            str(key).lower()
            for key in value
            if str(key).lower() in NONTRANSFERABLE_STRATEGY_KEYS
        }
        for nested in value.values():
            found.update(_find_nontransferable_strategy_keys(nested))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for nested in value:
            found.update(_find_nontransferable_strategy_keys(nested))
        return found
    return set()


def _successful_evidence(connection: sqlite3.Connection, record: dict[str, Any]) -> float:
    row = connection.execute(
        f"""
        SELECT {EVIDENCE_COLUMNS}
        FROM ts_validations AS v
        JOIN ts_barriers AS b ON b.barrier_set_id=?
        JOIN files AS f ON f.file_id=?
        JOIN files AS vf ON vf.file_id=v.frequency_output_file_id
        LEFT JOIN files AS pf ON pf.file_id=v.positive_displacement_file_id
        LEFT JOIN files AS nf ON nf.file_id=v.negative_displacement_file_id
        WHERE v.ts_validation_id=?
        """,
        (record["barrier_set_id"], record["ts_structure_file_id"], record["ts_validation_id"]),
    ).fetchone()
    evidence = {**record, **dict(row)} if row else record
    if not _evidence_valid(evidence):
        raise ValueError("successful template evidence is incomplete or incompatible")
    return float(evidence["evidence_barrier_ev"])


def record_template_in_connection(
    connection: sqlite3.Connection, record: dict[str, Any]
) -> str:
    validate_record(record)
    now = utc_now()
    values = {
        "template_id": record["template_id"],
        "reaction_family": record["reaction_family"],
        "fingerprint_json": json.dumps(record["fingerprint"], sort_keys=True),
        "waypoint_strategy_json": json.dumps(record["waypoint_strategy"]),
        "interpolation_strategy": record["interpolation_strategy"],
        "neb_settings_json": json.dumps(record["neb_settings"], sort_keys=True),
        "dimer_usage_json": json.dumps(record["dimer_usage"], sort_keys=True),
        "ts_structure_file_id": record.get("ts_structure_file_id"),
        "ts_validation_id": record.get("ts_validation_id"),
        "barrier_set_id": record.get("barrier_set_id"),
        "barrier_ev": None,
        "convergence_history_json": json.dumps(record["convergence_history"], sort_keys=True),
        "failure_cases_json": json.dumps(record["failure_cases"], sort_keys=True),
        "correction_strategy": record.get("correction_strategy"),
        "outcome": record["outcome"],
        "validation_grade": record["validation_grade"],
        "source_calculation_id": record["source_calculation_id"],
        "created_at": now,
        "updated_at": now,
    }
    if record["outcome"] == "success":
        values["barrier_ev"] = _successful_evidence(connection, record)
    existing = connection.execute(
        "SELECT * FROM ts_strategy_templates WHERE template_id=?",
        (record["template_id"],),
    ).fetchone()
    if existing is not None:
        comparable = {key: value for key, value in values.items() if key not in {"created_at", "updated_at"}}
        conflicts = [key for key, value in comparable.items() if existing[key] != value]
        if conflicts:
            raise ValueError(
                "template_id already exists with different content: " + ", ".join(conflicts)
            )
        return str(record["template_id"])
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO ts_strategy_templates ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )
    return str(record["template_id"])


def record_template(database: Path, record: dict[str, Any]) -> str:
    with open_registry(database, migrate=True) as connection:
        return record_template_in_connection(connection, record)
