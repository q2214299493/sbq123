from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from scripts.artifact_io import load_json_object, sha256_json
from scripts.ts_strategy_engine.registry import open_registry


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "project_registry.sqlite3"
DOCUMENT_KIND = "calculation_registry_batch"
TABLE_ORDER = (
    "calculations",
    "jobs",
    "job_status_history",
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
        if not _SAFE_ID.fullmatch(str(change["status_change_id"])):
            raise ValueError("workflow status_change_id contains unsupported characters")
        if change["expected_workflow_status"] == change["new_workflow_status"]:
            raise ValueError("workflow status change must change the status")
        for field in ("calculation_id", "changed_at", "reviewer", "reason"):
            if not str(change[field]).strip():
                raise ValueError(f"workflow status change {field} is required")


def load_registry_batch(path: Path) -> dict[str, Any]:
    return validate_registry_batch(load_json_object(path))


def validate_registry_batch(batch: dict[str, Any]) -> dict[str, Any]:
    if batch.get("schema_version") != 1 or batch.get("document_kind") != DOCUMENT_KIND:
        raise ValueError("registry batch must use calculation_registry_batch schema version 1")
    batch_id = str(batch.get("batch_id", ""))
    if not _SAFE_ID.fullmatch(batch_id):
        raise ValueError("registry batch_id contains unsupported characters")
    for field in ("created_at", "reviewer", "reason"):
        if not str(batch.get(field, "")).strip():
            raise ValueError(f"registry batch {field} is required")
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
    for index, change in enumerate(batch.get(STATUS_CHANGES_FIELD, [])):
        actions.append(
            {
                "table": "calculation_workflow_status_history",
                "index": index,
                "action": _status_change_action(connection, change),
            }
        )
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


def plan_registry_batch(database: Path, batch: dict[str, Any]) -> dict[str, Any]:
    validated = validate_registry_batch(batch)
    with open_registry(database) as connection:
        return _plan_with_connection(connection, validated)


def apply_registry_batch(
    database: Path,
    batch: dict[str, Any],
    *,
    confirmed_sha256: str,
) -> dict[str, Any]:
    validated = validate_registry_batch(batch)
    batch_sha256 = sha256_json(validated)
    if confirmed_sha256 != batch_sha256:
        raise ValueError("registry batch confirmation hash does not match the manifest")
    with open_registry(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        plan = _plan_with_connection(connection, validated)
        for action in plan["actions"]:
            if action["action"] == "update":
                change = validated[STATUS_CHANGES_FIELD][action["index"]]
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
            row = validated["rows"][table][action["index"]]
            columns = tuple(row)
            placeholders = ", ".join("?" for _ in columns)
            names = ", ".join(f'"{column}"' for column in columns)
            connection.execute(
                f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})',
                tuple(row[column] for column in columns),
            )
    return {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch_result",
        "batch_id": validated["batch_id"],
        "batch_sha256": batch_sha256,
        "inserted": plan["insert_count"],
        "updated": plan["update_count"],
        "unchanged": plan["unchanged_count"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan or apply a schema-gated append-only calculation-registry batch."
    )
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--confirm-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    batch = load_registry_batch(args.manifest)
    if args.command == "plan":
        result = plan_registry_batch(args.db, batch)
    else:
        if not args.confirm_sha256:
            raise ValueError("apply requires --confirm-sha256 from a reviewed plan")
        result = apply_registry_batch(
            args.db,
            batch,
            confirmed_sha256=args.confirm_sha256,
        )
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "batch_id": result["batch_id"],
                    "batch_sha256": result["batch_sha256"],
                    "insert_count": result.get("insert_count", result.get("inserted", 0)),
                    "update_count": result.get("update_count", result.get("updated", 0)),
                    "unchanged_count": result.get("unchanged_count", result.get("unchanged", 0)),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
