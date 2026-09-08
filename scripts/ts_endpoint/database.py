from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.ts_strategy_engine.registry import open_registry, table_exists, utc_now


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "modules"
    / "calculation_registry"
    / "migrations"
    / "001_ts_endpoint_records.sql"
)
ROLLBACK = MIGRATION.with_name("001_ts_endpoint_records_rollback.sql")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_VALID_STATUSES = {
    "VALID",
    "VALID_WITH_WARNING",
    "REVIEW_REQUIRED",
    "REJECTED",
}
_EXPECTED_COLUMNS = (
    ("endpoint_record_id", "TEXT", 0, 1),
    ("reaction_id", "TEXT", 1, 0),
    ("endpoint_role", "TEXT", 1, 0),
    ("structure_hash", "TEXT", 1, 0),
    ("endpoint_version", "TEXT", 1, 0),
    ("source_calculation_id", "TEXT", 0, 0),
    ("stable_structure_file_id", "TEXT", 0, 0),
    ("ts_structure_file_id", "TEXT", 0, 0),
    ("endpoint_structure_path", "TEXT", 0, 0),
    ("is_same_as_stable", "INTEGER", 1, 0),
    ("validation_status", "TEXT", 1, 0),
    ("validation_json", "TEXT", 1, 0),
    ("threshold_version", "TEXT", 1, 0),
    ("created_at", "TEXT", 1, 0),
)
_EXPECTED_FOREIGN_KEYS = {
    ("source_calculation_id", "calculations", "calculation_id"),
    ("stable_structure_file_id", "files", "file_id"),
    ("ts_structure_file_id", "files", "file_id"),
}
_EXPECTED_REACTION_INDEX = ("reaction_id", "endpoint_role")
_EXPECTED_UNIQUE_INDEX = (
    "reaction_id",
    "endpoint_role",
    "structure_hash",
    "endpoint_version",
)
_REQUIRED_CHECK_FRAGMENTS = (
    "check (endpoint_role in ('initial', 'final'))",
    "check (is_same_as_stable in (0, 1))",
    "(is_same_as_stable = 1 and endpoint_structure_path is null)",
    "(is_same_as_stable = 0 and endpoint_structure_path is not null)",
    "'valid_with_warning'",
    "'review_required'",
    "'rejected'",
)
_EMPTY_ROLLBACK_CONFIRMATION = "DROP EMPTY TS ENDPOINT TABLE"


def _execute_sql_file(connection: Any, path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    for statement in path.read_text(encoding="utf-8").split(";"):
        sql = statement.strip()
        if sql:
            connection.execute(sql)


def _endpoint_schema_version(connection: Any) -> str | None:
    row = connection.execute(
        "SELECT value FROM schema_metadata WHERE key='ts_endpoint_schema_version'"
    ).fetchone()
    return None if row is None else str(row[0])


def _index_columns(connection: Any, name: str) -> tuple[str, ...]:
    quoted_name = name.replace('"', '""')
    return tuple(
        str(row[2])
        for row in connection.execute(
            f'PRAGMA index_info("{quoted_name}")'
        ).fetchall()
    )


def _validate_endpoint_schema(connection: Any) -> None:
    if not table_exists(connection, "ts_endpoint_records"):
        raise ValueError("TS endpoint table is missing")
    columns = tuple(
        (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
        for row in connection.execute("PRAGMA table_info(ts_endpoint_records)")
    )
    if columns != _EXPECTED_COLUMNS:
        raise ValueError("incompatible TS endpoint schema columns")
    foreign_keys = {
        (str(row[3]), str(row[2]), str(row[4]))
        for row in connection.execute("PRAGMA foreign_key_list(ts_endpoint_records)")
    }
    if foreign_keys != _EXPECTED_FOREIGN_KEYS:
        raise ValueError("incompatible TS endpoint schema foreign keys")
    indexes = connection.execute("PRAGMA index_list(ts_endpoint_records)").fetchall()
    named_reaction_index = next(
        (row for row in indexes if str(row[1]) == "idx_ts_endpoint_reaction"),
        None,
    )
    if (
        named_reaction_index is None
        or int(named_reaction_index[2]) != 0
        or _index_columns(connection, str(named_reaction_index[1]))
        != _EXPECTED_REACTION_INDEX
    ):
        raise ValueError("incompatible TS endpoint reaction index")
    unique_indexes = {
        _index_columns(connection, str(row[1]))
        for row in indexes
        if int(row[2]) == 1
    }
    if _EXPECTED_UNIQUE_INDEX not in unique_indexes:
        raise ValueError("incompatible TS endpoint uniqueness constraint")
    row = connection.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='ts_endpoint_records'"
    ).fetchone()
    normalized_sql = " ".join(str(row[0]).lower().split()) if row else ""
    if any(fragment not in normalized_sql for fragment in _REQUIRED_CHECK_FRAGMENTS):
        raise ValueError("incompatible TS endpoint check constraints")
    if _endpoint_schema_version(connection) != "1":
        raise ValueError("TS endpoint migration version is not 1")


def apply_ts_endpoint_migration(database: Path, *, rollback: bool = False) -> None:
    """Apply the isolated extension after rejecting incompatible existing schemas."""

    if rollback:
        raise ValueError(
            "TS endpoint rollback is prohibited by default; "
            "use rollback_empty_ts_endpoint_migration for an empty test schema"
        )
    with open_registry(database) as connection:
        exists = table_exists(connection, "ts_endpoint_records")
        version = _endpoint_schema_version(connection)
        if exists:
            _validate_endpoint_schema(connection)
            return
        if version is not None:
            raise ValueError("TS endpoint migration metadata exists without its table")
        connection.execute("BEGIN IMMEDIATE")
        _execute_sql_file(connection, MIGRATION)
        _validate_endpoint_schema(connection)


def rollback_empty_ts_endpoint_migration(
    database: Path,
    *,
    confirmation: str,
) -> None:
    """Remove only an empty endpoint extension after an exact explicit confirmation."""

    if confirmation != _EMPTY_ROLLBACK_CONFIRMATION:
        raise ValueError("explicit empty TS endpoint rollback confirmation is required")
    with open_registry(database) as connection:
        _validate_endpoint_schema(connection)
        count = int(
            connection.execute("SELECT COUNT(*) FROM ts_endpoint_records").fetchone()[0]
        )
        if count:
            raise ValueError("non-empty TS endpoint rollback is prohibited")
        connection.execute("BEGIN IMMEDIATE")
        _execute_sql_file(connection, ROLLBACK)
        if table_exists(connection, "ts_endpoint_records"):
            raise ValueError("TS endpoint migration rollback did not remove its table")
        if _endpoint_schema_version(connection) is not None:
            raise ValueError("TS endpoint migration rollback did not remove its version")


@dataclass(frozen=True)
class TSEndpointRecord:
    endpoint_record_id: str
    reaction_id: str
    endpoint_role: str
    structure_hash: str
    endpoint_version: str
    validation_status: str
    validation: dict[str, Any]
    threshold_version: str
    is_same_as_stable: bool
    endpoint_structure_path: str | None
    source_calculation_id: str | None = None
    stable_structure_file_id: str | None = None
    ts_structure_file_id: str | None = None
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.endpoint_record_id):
            raise ValueError("endpoint_record_id contains unsupported characters")
        if not isinstance(self.reaction_id, str) or not self.reaction_id.strip():
            raise ValueError("reaction_id is required")
        if self.endpoint_role not in {"initial", "final"}:
            raise ValueError("endpoint_role must be 'initial' or 'final'")
        if self.validation_status not in _VALID_STATUSES:
            raise ValueError("unsupported TS endpoint validation status")
        if self.is_same_as_stable and self.endpoint_structure_path is not None:
            raise ValueError("an endpoint identical to the stable structure must not duplicate its path")
        if not self.is_same_as_stable and not self.endpoint_structure_path:
            raise ValueError("a TS-specific endpoint must retain its reviewed structure path")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class TSEndpointDatabase:
    """Repository adapter for the isolated ts_endpoint_records table."""

    def __init__(self, database: Path) -> None:
        self.database = database

    def save(self, record: TSEndpointRecord) -> str:
        with open_registry(self.database) as connection:
            self._require_table(connection)
            existing = connection.execute(
                """
                SELECT endpoint_record_id
                FROM ts_endpoint_records
                WHERE reaction_id = ?
                  AND endpoint_role = ?
                  AND structure_hash = ?
                  AND endpoint_version = ?
                """,
                (
                    record.reaction_id,
                    record.endpoint_role,
                    record.structure_hash,
                    record.endpoint_version,
                ),
            ).fetchone()
            if existing is not None:
                return str(existing[0])
            identifier = connection.execute(
                "SELECT 1 FROM ts_endpoint_records WHERE endpoint_record_id = ?",
                (record.endpoint_record_id,),
            ).fetchone()
            if identifier is not None:
                raise ValueError(
                    f"TS endpoint record ID already exists with different content: "
                    f"{record.endpoint_record_id}"
                )
            connection.execute(
                """
                INSERT INTO ts_endpoint_records (
                    endpoint_record_id,
                    reaction_id,
                    endpoint_role,
                    structure_hash,
                    endpoint_version,
                    source_calculation_id,
                    stable_structure_file_id,
                    ts_structure_file_id,
                    endpoint_structure_path,
                    is_same_as_stable,
                    validation_status,
                    validation_json,
                    threshold_version,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.endpoint_record_id,
                    record.reaction_id,
                    record.endpoint_role,
                    record.structure_hash,
                    record.endpoint_version,
                    record.source_calculation_id,
                    record.stable_structure_file_id,
                    record.ts_structure_file_id,
                    record.endpoint_structure_path,
                    int(record.is_same_as_stable),
                    record.validation_status,
                    json.dumps(
                        record.validation,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    record.threshold_version,
                    record.created_at,
                ),
            )
        return record.endpoint_record_id

    def get(self, endpoint_record_id: str) -> dict[str, Any]:
        with open_registry(self.database) as connection:
            self._require_table(connection)
            row = connection.execute(
                "SELECT * FROM ts_endpoint_records WHERE endpoint_record_id = ?",
                (endpoint_record_id,),
            ).fetchone()
            if row is None:
                raise KeyError(endpoint_record_id)
            return self._row(row)

    def find_by_reaction(self, reaction_id: str) -> list[dict[str, Any]]:
        with open_registry(self.database) as connection:
            self._require_table(connection)
            rows = connection.execute(
                """
                SELECT *
                FROM ts_endpoint_records
                WHERE reaction_id = ?
                ORDER BY endpoint_role, created_at, endpoint_record_id
                """,
                (reaction_id,),
            ).fetchall()
            return [self._row(row) for row in rows]

    @staticmethod
    def _require_table(connection: Any) -> None:
        if not table_exists(connection, "ts_endpoint_records"):
            raise ValueError(
                "TS endpoint table is missing; apply the isolated TS endpoint migration"
            )

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["is_same_as_stable"] = bool(payload["is_same_as_stable"])
        payload["validation"] = json.loads(payload.pop("validation_json"))
        return payload
