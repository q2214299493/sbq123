from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from scripts.registry_schema import CURRENT_VERSION, migrate_registry
from scripts.artifact_io import sha256_json


ACCEPTED_STATIC_STATUS = "accepted_matched_static"
ACCEPTED_COMPATIBLE_FINAL_ENERGY_STATUS = "accepted_compatible_final_energy"
ACCEPTED_FINAL_ENERGY_STATUSES = frozenset(
    {ACCEPTED_STATIC_STATUS, ACCEPTED_COMPATIBLE_FINAL_ENERGY_STATUS}
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compatibility_fingerprint(compatibility: dict[str, Any]) -> str:
    return sha256_json(compatibility)


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def require_current_schema(connection: sqlite3.Connection) -> None:
    if not table_exists(connection, "schema_metadata"):
        raise ValueError("registry schema is missing; run scripts/init_registry.py")
    row = connection.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
    if row is None or int(row[0]) != CURRENT_VERSION:
        raise ValueError(f"registry schema must be version {CURRENT_VERSION}; run scripts/init_registry.py")


@contextmanager
def open_registry(database: Path, *, migrate: bool = False) -> Iterator[sqlite3.Connection]:
    if migrate:
        migrate_registry(database)
    if not database.is_file():
        raise ValueError(f"registry database not found: {database}")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        require_current_schema(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
