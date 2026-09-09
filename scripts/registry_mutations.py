"""Append-only registry batch validation and SQL mutation ownership."""
from __future__ import annotations

import re
import json
import sqlite3
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_json
from scripts.ts_strategy_engine.registry import open_registry
from scripts.provenance_fields import required_text, timestamp
from scripts.scientific_validation import validate_finite_tree

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "project_registry.sqlite3"
DOCUMENT_KIND = "calculation_registry_batch"
TABLE_ORDER = (
    "calculations",
    "jobs",
    "job_status_history",
    "job_recovery_events",
    "files",
    "results",
    "reviews",
    "calculation_compatibility",
)
STATUS_CHANGES_FIELD = "workflow_status_changes"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_status_changes(status_changes: list[Any]) -> None:
    required_fields = {
        "status_change_id",
        "calculation_id",
        "expected_workflow_status",
        "new_workflow_status",
        "changed_at",
        "reviewer",
        "reason",
    }
    for index, change in enumerate(status_changes):
        if not isinstance(change, dict):
            raise ValueError(f"registry batch {STATUS_CHANGES_FIELD}[{index}] must be an object")
        missing = required_fields - set(change)
        unknown = set(change) - required_fields
        if missing:
            raise ValueError(
                f"registry batch {STATUS_CHANGES_FIELD}[{index}] is missing required fields: "
                + ", ".join(sorted(missing))
            )
        if unknown:
            raise ValueError(
                f"registry batch {STATUS_CHANGES_FIELD}[{index}] has unknown fields: "
                + ", ".join(sorted(unknown))
            )
        if not _SAFE_ID.fullmatch(required_text(change["status_change_id"], "status_change_id")):
            raise ValueError("workflow status_change_id contains unsupported characters")
        if change["expected_workflow_status"] == change["new_workflow_status"]:
            raise ValueError("workflow status change must change the status")
        for field in ("calculation_id", "changed_at", "reviewer", "reason"):
            if not str(change[field]).strip():
                raise ValueError(f"workflow status change {field} is required")


def load_registry_batch(path: Path) -> dict[str, Any]:
    return validate_registry_batch(load_json_object(path))


def _reject_external_result(row: dict[str, Any], provenance: dict[str, Any]) -> None:
    declared_type = provenance.get("type", row.get("type"))
    method = str(row.get("extraction_method", "")).lower()
    if declared_type is not None and declared_type != "calculated_result" or any(
        marker in method for marker in ("prediction", "game-net", "game_net", "gamenet")
    ):
        raise ValueError("external claims and predictions cannot be stored as local calculated results")


def _validate_result_provenance(batch: dict[str, Any]) -> None:
    declarations = batch.get("result_provenance", {})
    if not isinstance(declarations, dict):
        raise ValueError("result provenance must be a mapping")
    results = batch["rows"].get("results", [])
    if set(declarations) - {row.get("result_id") for row in results}:
        raise ValueError("result provenance references an unknown result")
    for row in results:
        provenance = declarations.get(row.get("result_id"), {})
        if not isinstance(provenance, dict):
            raise ValueError("result provenance must be an object")
        _reject_external_result(row, provenance)


def validate_registry_batch(batch: dict[str, Any]) -> dict[str, Any]:
    if batch.get("schema_version") != 1 or batch.get("document_kind") != DOCUMENT_KIND:
        raise ValueError("registry batch must use calculation_registry_batch schema version 1")
    validate_finite_tree(batch)
    batch_id = required_text(batch.get("batch_id"), "registry batch_id")
    if not _SAFE_ID.fullmatch(batch_id):
        raise ValueError("registry batch_id contains unsupported characters")
    for field in ("created_at", "reviewer", "reason"):
        required_text(batch.get(field), f"registry batch {field}")
    timestamp(batch["created_at"], "batch created_at")
    rows = batch.get("rows", {})
    status_changes = batch.get(STATUS_CHANGES_FIELD, [])
    if not isinstance(rows, dict):
        raise ValueError("registry batch rows must be a mapping")
    if not isinstance(status_changes, list):
        raise ValueError(f"registry batch {STATUS_CHANGES_FIELD} must be a list")
    if not rows and not status_changes:
        raise ValueError("registry batch requires rows or workflow_status_changes")
    unknown_tables = set(rows) - set(TABLE_ORDER)
    if unknown_tables:
        raise ValueError(
            "registry batch contains unsupported tables: "
            + ", ".join(sorted(unknown_tables))
        )
    row_count = 0
    for table, values in rows.items():
        if not isinstance(values, list):
            raise ValueError(f"registry batch rows.{table} must be a list")
        for index, row in enumerate(values):
            if not isinstance(row, dict) or not row:
                raise ValueError(f"registry batch rows.{table}[{index}] must be a non-empty object")
            if any(not isinstance(column, str) or not column for column in row):
                raise ValueError(f"registry batch rows.{table}[{index}] has an invalid column name")
            row_count += 1
    if row_count == 0 and not status_changes:
        raise ValueError("registry batch must contain at least one change")
    _validate_status_changes(status_changes)
    _validate_result_provenance(batch)
    return batch


def _status_change_action(
    connection: sqlite3.Connection,
    change: dict[str, Any],
) -> str:
    history = connection.execute(
        "SELECT * FROM calculation_workflow_status_history WHERE status_change_id=?",
        (change["status_change_id"],),
    ).fetchone()
    current = connection.execute(
        "SELECT workflow_status FROM calculations WHERE calculation_id=?",
        (change["calculation_id"],),
    ).fetchone()
    if current is None:
        raise ValueError(
            "workflow status change references missing calculation: "
            + str(change["calculation_id"])
        )
    expected_history = {
        "status_change_id": change["status_change_id"],
        "calculation_id": change["calculation_id"],
        "previous_workflow_status": change["expected_workflow_status"],
        "new_workflow_status": change["new_workflow_status"],
        "changed_at": change["changed_at"],
        "reviewer": change["reviewer"],
        "reason": change["reason"],
    }
    if history is not None:
        if any(history[key] != value for key, value in expected_history.items()):
            raise ValueError(
                "workflow status change conflicts with existing history: "
                + str(change["status_change_id"])
            )
        if current["workflow_status"] != change["new_workflow_status"]:
            raise ValueError(
                "workflow status history exists but calculation status differs: "
                + str(change["calculation_id"])
            )
        return "unchanged"
    if current["workflow_status"] != change["expected_workflow_status"]:
        raise ValueError(
            "workflow status change expected "
            f"{change['expected_workflow_status']!r} for {change['calculation_id']} "
            f"but found {current['workflow_status']!r}"
        )
    return "update"


def _table_contract(
    connection: sqlite3.Connection,
    table: str,
) -> tuple[set[str], tuple[str, ...], set[str]]:
    rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    if not rows:
        raise ValueError(f"registry table is missing: {table}")
    columns = {str(row[1]) for row in rows}
    primary_key = tuple(
        str(row[1])
        for row in sorted(rows, key=lambda item: int(item[5]))
        if int(row[5]) > 0 and not (str(row[2]).upper() == "INTEGER" and int(row[5]) == 1)
    )
    required = {
        str(row[1])
        for row in rows
        if int(row[3]) == 1 and row[4] is None
    } | set(primary_key)
    return columns, primary_key, required


def _existing_action(
    connection: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
    primary_key: tuple[str, ...],
) -> str:
    lookup_columns = primary_key or tuple(row)
    where = " AND ".join(f'"{column}" IS ?' for column in lookup_columns)
    existing = connection.execute(
        f'SELECT * FROM "{table}" WHERE {where} LIMIT 1',
        tuple(row[column] for column in lookup_columns),
    ).fetchone()
    if existing is None:
        return "insert"
    if primary_key and any(existing[column] != value for column, value in row.items()):
        key = ", ".join(f"{column}={row[column]!r}" for column in primary_key)
        raise ValueError(f"registry row conflicts with existing {table} primary key: {key}")
    return "unchanged"


def _plan_with_connection(
    connection: sqlite3.Connection,
    batch: dict[str, Any],
    *, simulate: bool = False,
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for table in TABLE_ORDER:
        values = batch["rows"].get(table, [])
        if not values:
            continue
        columns, primary_key, required = _table_contract(connection, table)
        for index, row in enumerate(values):
            unknown = set(row) - columns
            missing = required - set(row)
            if unknown:
                raise ValueError(
                    f"registry batch {table}[{index}] has unknown columns: "
                    + ", ".join(sorted(unknown))
                )
            if missing:
                raise ValueError(
                    f"registry batch {table}[{index}] is missing required columns: "
                    + ", ".join(sorted(missing))
                )
            for key in primary_key:
                required_text(row.get(key), f"{table}.{key}")
            actions.append(
                {
                    "table": table,
                    "index": index,
                    "action": _existing_action(
                        connection,
                        table,
                        row,
                        primary_key,
                    ),
                }
            )
            if simulate:
                _execute_actions(connection, batch, {"actions": [actions[-1]]})
    for index, change in enumerate(batch.get(STATUS_CHANGES_FIELD, [])):
        actions.append(
            {
                "table": "calculation_workflow_status_history",
                "index": index,
                "action": _status_change_action(connection, change),
            }
        )
        if simulate:
            _execute_actions(connection, batch, {"actions": [actions[-1]]})
    return {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch_plan",
        "batch_id": batch["batch_id"],
        "batch_sha256": sha256_json(batch),
        "insert_count": sum(item["action"] == "insert" for item in actions),
        "update_count": sum(item["action"] == "update" for item in actions),
        "unchanged_count": sum(item["action"] == "unchanged" for item in actions),
        "actions": actions,
    }


def _execute_actions(connection, batch, plan):
    for action in plan["actions"]:
        if action["action"] == "update":
            change = batch[STATUS_CHANGES_FIELD][action["index"]]
            connection.execute(
                """
                INSERT INTO calculation_workflow_status_history
                (status_change_id, calculation_id, previous_workflow_status,
                 new_workflow_status, changed_at, reviewer, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change["status_change_id"],
                    change["calculation_id"],
                    change["expected_workflow_status"],
                    change["new_workflow_status"],
                    change["changed_at"],
                    change["reviewer"],
                    change["reason"],
                ),
            )
            cursor = connection.execute(
                """
                UPDATE calculations SET workflow_status=?
                WHERE calculation_id=? AND workflow_status=?
                """,
                (
                    change["new_workflow_status"],
                    change["calculation_id"],
                    change["expected_workflow_status"],
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "workflow status changed after plan for "
                    + str(change["calculation_id"])
                )
            continue
        if action["action"] != "insert":
            continue
        table = action["table"]
        row = batch["rows"][table][action["index"]]
        columns = tuple(row)
        placeholders = ", ".join("?" for _ in columns)
        names = ", ".join(f'"{column}"' for column in columns)
        connection.execute(
            f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})',
            tuple(row[column] for column in columns),
        )


def _snapshot(connection):
    clone = sqlite3.connect(":memory:")
    clone.row_factory = sqlite3.Row
    clone.deserialize(connection.serialize())
    clone.execute("PRAGMA foreign_keys=ON")
    return clone


def plan_registry_batch(database: Path, batch: dict[str, Any]) -> dict[str, Any]:
    from scripts.registry_transactions import database_fingerprint

    validated = validate_registry_batch(batch)
    with open_registry(database) as connection:
        connection.execute("BEGIN")
        fingerprint = database_fingerprint(connection)
        clone = _snapshot(connection)
        try:
            plan = _plan_with_connection(clone, validated, simulate=True)
            _validate_final_mutation(clone, validated)
            if clone.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("complete mutation violates foreign keys")
        finally:
            clone.close()
    plan.update({"approval_identity": validated["reviewer"], "database_fingerprint": fingerprint, "database_identity": str(database.resolve()),
                 "scope": sorted({item["table"] for item in plan["actions"]})})
    plan["plan_sha256"] = sha256_json(plan)
    return plan


def apply_registry_batch(database: Path, batch: dict[str, Any], *, confirmed_sha256: str,
                         plan: dict | None = None, approval: dict | None = None) -> dict[str, Any]:
    from scripts.registry_transactions import applied_receipt, database_fingerprint, record_event, verify_approval

    validated = validate_registry_batch(batch)
    if plan is None or approval is None:
        raise ValueError("confirmation hash requires the saved reviewed plan and explicit approval; no regeneration")
    # Freeze caller-owned dictionaries before validation or transaction entry.
    plan, approval, validated = json.loads(json.dumps([plan, approval, validated]))
    verify_approval(plan, approval, validated, confirmed_sha256)
    if plan["database_identity"] != str(database.resolve()):
        raise ValueError("approved database identity mismatch")
    try:
        with open_registry(database) as connection:
            connection.execute("BEGIN IMMEDIATE")
            receipt = applied_receipt(connection, plan)
            if receipt is not None:
                return receipt
            if database_fingerprint(connection) != plan["database_fingerprint"]:
                raise ValueError("database fingerprint changed after approval")
            preview = _snapshot(connection)
            try:
                current = _plan_with_connection(preview, validated, simulate=True)
                _validate_final_mutation(preview, validated)
            finally:
                preview.close()
            if any(current[key] != plan[key] for key in current):
                raise ValueError("approved actions differ from complete mutation")
            _execute_actions(connection, validated, plan)
            _validate_final_mutation(connection, validated)
            receipt = {"schema_version": 1, "document_kind": "calculation_registry_batch_result",
                       "batch_id": validated["batch_id"], "batch_sha256": plan["batch_sha256"],
                       "plan_sha256": plan["plan_sha256"], "inserted": plan["insert_count"],
                       "updated": plan["update_count"], "unchanged": plan["unchanged_count"],
                       "already_applied": False}
            _record_batch_events(connection, validated, plan, approval)
            connection.execute("INSERT INTO registry_applications VALUES (?,?,?,?)", (
                plan["plan_sha256"], plan["batch_id"], plan["batch_sha256"], json.dumps(receipt)))
            record_event(connection, "batch_applied", plan["batch_id"], {"plan": plan, "approval": approval, "batch": validated},
                         actor=approval["reviewer"], reason=validated["reason"])
        return receipt
    except Exception as error:
        # The accepted mutation rolled back. Persist failure in a separate transaction.
        with open_registry(database) as connection:
            record_event(connection, "batch_failed", plan["batch_id"],
                         {"plan_sha256": plan["plan_sha256"], "error": str(error)},
                         actor=approval["reviewer"], reason="approved mutation failed; rolled back")
        raise


def _validate_final_mutation(connection, batch):
    from scripts.registry_acceptance import validate_result_acceptance
    from scripts.state_manager.job_lifecycle import validate_job_history, validate_workflow_transition

    for change in batch.get(STATUS_CHANGES_FIELD, []):
        validate_workflow_transition(change)
    jobs = {row["job_record_id"] for row in batch["rows"].get("job_status_history", [])}
    for recovery in batch["rows"].get("job_recovery_events", []):
        row = connection.execute("SELECT job_record_id FROM job_status_history WHERE status_event_id=?", (recovery["status_event_id"],)).fetchone()
        jobs.add(row[0])
    for job_id in jobs:
        validate_job_history(connection, job_id)
    for compatibility in batch["rows"].get("calculation_compatibility", []):
        payload = json.loads(compatibility["compatibility_json"])
        if not isinstance(payload, dict) or not payload or sha256_json(payload) != compatibility["compatibility_fingerprint"]:
            raise ValueError("compatibility content binding mismatch")
    for row in batch["rows"].get("results", []):
        validate_result_acceptance(connection, row, batch.get("result_provenance", {}).get(row["result_id"], {}))


def _record_batch_events(connection, batch, plan, approval):
    from scripts.registry_transactions import record_event

    types = {"calculations": "calculation_created", "jobs": "job_created", "job_status_history": "job_status_observed",
             "reviews": "review_completed", "job_recovery_events": "job_recovery", "calculation_compatibility": "compatibility_created",
             "calculation_workflow_status_history": "workflow_transition"}
    for action in plan["actions"]:
        if action["action"] == "unchanged":
            continue
        table = action["table"]
        row = (batch[STATUS_CHANGES_FIELD] if action["action"] == "update" else batch["rows"][table])[action["index"]]
        event_type = types.get(table, "record_created")
        if table == "job_status_history":
            event_type = {"SUBMITTED": "job_submitted", "PEND": "job_submitted", "DONE": "job_finished", "EXIT": "job_finished"}.get(row["scheduler_status"], event_type)
        record_event(connection, event_type, row.get("calculation_id", row.get("job_record_id", batch["batch_id"])),
                     {"table": table, "row": row, "plan_sha256": plan["plan_sha256"]},
                     actor=approval["reviewer"], reason=batch["reason"])
