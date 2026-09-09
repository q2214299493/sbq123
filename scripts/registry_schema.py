from __future__ import annotations

from scripts.runtime_resources import resource_path

import sqlite3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = resource_path('modules/calculation_registry/schema.sql')
CURRENT_VERSION = 9
REQUIRED_COLUMNS = {
    "job_recovery_events": {"event_id", "status_event_id", "timestamp", "actor", "reason"},
    "registry_events": {"event_id", "event_type", "payload_json", "occurred_at", "actor", "reason"},
    "registry_applications": {"plan_sha256", "batch_id", "batch_sha256", "receipt_json"},
    "compatibility_revisions": {"revision_id", "compatibility_json", "supersedes_revision_id"},
    "calculation_compatibility_revisions": {"calculation_id", "revision_id"},
    "ts_strategy_events": {"event_type", "entity_id", "payload_json", "payload_sha256", "created_at"},
    "calculation_workflow_status_history": {
        "status_change_id",
        "calculation_id",
        "previous_workflow_status",
        "new_workflow_status",
        "changed_at",
        "reviewer",
        "reason",
    },
    "calculation_compatibility": {"calculation_id", "compatibility_fingerprint", "compatibility_json"},
    "ts_barriers": {
        "barrier_set_id",
        "ts_validation_id",
        "initial_result_id",
        "ts_result_id",
        "final_result_id",
        "validation_status",
    },
    "ts_strategy_templates": {"template_id", "ts_validation_id", "barrier_set_id", "fingerprint_json"},
    "ts_validations": {
        "ts_validation_id",
        "source_saddle_calculation_id",
        "frequency_output_file_id",
        "positive_displacement_file_id",
        "negative_displacement_file_id",
        "contract_sha256",
        "atom_map_sha256",
        "compatibility_fingerprint",
        "connectivity_report_file_id",
        "positive_connectivity_job_record_id",
        "negative_connectivity_job_record_id",
        "connectivity_report_sha256",
    },
    "excel_promotions": {
        "promotion_id",
        "promotion_kind",
        "registry_id",
        "workbook_path",
        "worksheet_name",
        "row_number",
        "workbook_sha256_before",
        "workbook_sha256_after",
        "written_values_sha256",
        "reviewer",
        "reviewed_at",
        "receipt_path",
        "request_sha256",
    },
}


TS_STRATEGY_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS ts_strategy_events (
    event_type TEXT NOT NULL CHECK (event_type IN ('variant', 'attempt', 'outcome')),
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (event_type, entity_id)
)
"""

TS_BARRIERS_SQL = """
CREATE TABLE IF NOT EXISTS ts_barriers (
    barrier_set_id TEXT PRIMARY KEY,
    reaction_id TEXT NOT NULL,
    source_calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    ts_validation_id TEXT NOT NULL REFERENCES ts_validations(ts_validation_id),
    initial_result_id TEXT NOT NULL REFERENCES results(result_id),
    ts_result_id TEXT NOT NULL REFERENCES results(result_id),
    final_result_id TEXT NOT NULL REFERENCES results(result_id),
    compatibility_fingerprint TEXT NOT NULL,
    energy_convention TEXT NOT NULL,
    forward_barrier_ev REAL NOT NULL,
    reverse_barrier_ev REAL NOT NULL,
    reaction_energy_ev REAL NOT NULL,
    validation_status TEXT NOT NULL CHECK (validation_status IN ('accepted', 'rejected')),
    created_at TEXT NOT NULL,
    notes TEXT,
    UNIQUE (reaction_id, initial_result_id, ts_result_id, final_result_id)
)
"""

COMPATIBILITY_SQL = """
CREATE TABLE IF NOT EXISTS calculation_compatibility (
    calculation_id TEXT PRIMARY KEY REFERENCES calculations(calculation_id),
    compatibility_fingerprint TEXT NOT NULL,
    compatibility_json TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
)
"""

EXCEL_PROMOTIONS_SQL = """
CREATE TABLE IF NOT EXISTS excel_promotions (
    promotion_id TEXT PRIMARY KEY,
    promotion_kind TEXT NOT NULL CHECK (promotion_kind IN ('adsorption', 'barrier')),
    registry_id TEXT NOT NULL,
    calculation_id TEXT REFERENCES calculations(calculation_id),
    workbook_path TEXT NOT NULL,
    worksheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number > 1),
    workbook_sha256_before TEXT NOT NULL,
    workbook_sha256_after TEXT NOT NULL,
    written_values_sha256 TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    receipt_path TEXT NOT NULL,
    request_sha256 TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    notes TEXT,
    UNIQUE (promotion_kind, registry_id),
    UNIQUE (workbook_path, worksheet_name, row_number)
)
"""

CALCULATION_WORKFLOW_STATUS_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS calculation_workflow_status_history (
    status_change_id TEXT PRIMARY KEY,
    calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    previous_workflow_status TEXT NOT NULL,
    new_workflow_status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reason TEXT NOT NULL,
    CHECK (previous_workflow_status != new_workflow_status)
)
"""


def _schema_version(connection: sqlite3.Connection) -> int | None:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_metadata'"
    ).fetchone()
    if table is None:
        return None
    row = connection.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
    return int(row[0]) if row else None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_columns(connection: sqlite3.Connection, table: str, definitions: tuple[tuple[str, str], ...]) -> None:
    existing = _columns(connection, table)
    for column, definition in definitions:
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_v2(connection: sqlite3.Connection) -> None:
    connection.execute(COMPATIBILITY_SQL)
    connection.execute(TS_BARRIERS_SQL)
    _add_columns(
        connection,
        "ts_validations",
        (
            ("source_saddle_calculation_id", "TEXT REFERENCES calculations(calculation_id)"),
            ("frequency_output_file_id", "TEXT REFERENCES files(file_id)"),
            ("positive_displacement_file_id", "TEXT REFERENCES files(file_id)"),
            ("negative_displacement_file_id", "TEXT REFERENCES files(file_id)"),
        ),
    )
    _add_columns(
        connection,
        "ts_strategy_templates",
        (
            ("ts_validation_id", "TEXT REFERENCES ts_validations(ts_validation_id)"),
            ("barrier_set_id", "TEXT REFERENCES ts_barriers(barrier_set_id)"),
        ),
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ts_strategy_unique_experience "
        "ON ts_strategy_templates(source_calculation_id, fingerprint_json, outcome)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_barriers_reaction ON ts_barriers(reaction_id, validation_status)"
    )
    connection.execute("UPDATE schema_metadata SET value='3' WHERE key='schema_version'")


def _migrate_v3(connection: sqlite3.Connection) -> None:
    _add_columns(
        connection,
        "ts_validations",
        (
            ("contract_sha256", "TEXT"),
            ("atom_map_sha256", "TEXT"),
            ("compatibility_fingerprint", "TEXT"),
        ),
    )
    connection.execute("UPDATE schema_metadata SET value='4' WHERE key='schema_version'")


def _migrate_v4(connection: sqlite3.Connection) -> None:
    _add_columns(
        connection,
        "ts_validations",
        (
            ("connectivity_report_file_id", "TEXT REFERENCES files(file_id)"),
            ("positive_connectivity_job_record_id", "TEXT REFERENCES jobs(job_record_id)"),
            ("negative_connectivity_job_record_id", "TEXT REFERENCES jobs(job_record_id)"),
            ("connectivity_report_sha256", "TEXT"),
        ),
    )
    connection.execute("UPDATE schema_metadata SET value='5' WHERE key='schema_version'")


def _migrate_v5(connection: sqlite3.Connection) -> None:
    connection.execute(EXCEL_PROMOTIONS_SQL)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_excel_promotions_registry "
        "ON excel_promotions(promotion_kind, registry_id)"
    )
    connection.execute("UPDATE schema_metadata SET value='6' WHERE key='schema_version'")


def _migrate_v6(connection: sqlite3.Connection) -> None:
    connection.execute(CALCULATION_WORKFLOW_STATUS_HISTORY_SQL)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_calculation_workflow_status_history "
        "ON calculation_workflow_status_history(calculation_id, changed_at)"
    )
    connection.execute("UPDATE schema_metadata SET value='7' WHERE key='schema_version'")


def validate_schema(connection: sqlite3.Connection) -> None:
    if _schema_version(connection) != CURRENT_VERSION:
        raise ValueError(f"registry schema must be version {CURRENT_VERSION}; explicit migration required")
    for table, required in REQUIRED_COLUMNS.items():
        missing = required - _columns(connection, table)
        if missing:
            raise ValueError(f"registry table {table} missing columns: {', '.join(sorted(missing))}")
    protected = ("registry_events", "registry_applications", "compatibility_revisions",
                 "calculation_compatibility_revisions", "calculation_compatibility", "job_status_history",
                 "calculation_workflow_status_history", "ts_strategy_events", "results", "files", "reviews",
                 "ts_validations", "ts_barriers", "ts_strategy_templates", "excel_promotions", "job_recovery_events")
    expected = {f"immutable_{table}_{operation}" for table in protected for operation in ("update", "delete", "replace")}
    actual = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    if expected - actual:
        raise ValueError("registry immutable guards missing; schema is incompatible")
    bindings = connection.execute(
        "SELECT c.compatibility_json,r.compatibility_json,c.compatibility_fingerprint,b.revision_id "
        "FROM calculation_compatibility c LEFT JOIN calculation_compatibility_revisions b USING(calculation_id) "
        "LEFT JOIN compatibility_revisions r ON r.revision_id=b.revision_id"
    ).fetchall()
    for original, revision, fingerprint, binding in bindings:
        if binding != fingerprint or revision is None or json.loads(original) != json.loads(revision):
            raise ValueError("historical compatibility revision binding mismatch")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("registry foreign-key check failed")
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("registry integrity check failed")


def _execute_script(connection: sqlite3.Connection, text: str) -> None:
    # executescript implicitly commits: execute complete statements inside our transaction.
    statement = ""
    for line in text.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        raise ValueError("incomplete migration SQL")


def migrate_registry(database: Path, schema: Path = SCHEMA) -> int:
    """Explicit migration only; all versions and validation share one transaction.

    Failure rolls back DDL and data. Before upgrading an existing database, the
    caller must retain an off-line backup for later operational downgrade.
    Version 9 also supports guarded additive rollback via rollback_registry_v9.
    """
    if not schema.is_file():
        raise FileNotFoundError(f"Schema not found: {schema}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        version = _schema_version(connection)
        if version is None:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError("unversioned nonempty registry requires explicit historical migration")
            _execute_script(connection, schema.read_text(encoding="utf-8"))
            version = CURRENT_VERSION
        elif version > CURRENT_VERSION:
            raise ValueError(f"registry schema {version} is newer than supported version {CURRENT_VERSION}")
        elif version < 2:
            raise ValueError("registry schema versions below 2 require an explicit historical migration")
        for previous, migration in ((2, _migrate_v2), (3, _migrate_v3), (4, _migrate_v4),
                                    (5, _migrate_v5), (6, _migrate_v6)):
            if version == previous:
                migration(connection)
                version += 1
        if version == 7:
            connection.execute(TS_STRATEGY_EVENTS_SQL)
            connection.execute("UPDATE schema_metadata SET value='8' WHERE key='schema_version'")
            version = 8
        if version == 8:
            _execute_script(connection, (resource_path('modules/calculation_registry/migrations/009_registry_governance.sql')).read_text(encoding="utf-8"))
        validate_schema(connection)
    return CURRENT_VERSION


def rollback_registry_v9(database: Path) -> int:
    """Explicit additive downgrade; reject loss of any post-migration governance records."""
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        validate_schema(connection)
        for table in ("registry_events", "registry_applications", "job_recovery_events"):
            if connection.execute(f"SELECT 1 FROM {table}").fetchone():
                raise ValueError("rollback would discard governance history; restore reviewed backup instead")
        if connection.execute("SELECT 1 FROM compatibility_revisions WHERE revision_id NOT IN "
                              "(SELECT compatibility_fingerprint FROM calculation_compatibility)").fetchone():
            raise ValueError("rollback would discard compatibility revisions")
        _execute_script(connection, (resource_path('modules/calculation_registry/migrations/009_registry_governance_rollback.sql')).read_text(encoding="utf-8"))
        if _schema_version(connection) != 8 or connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("rollback validation failed")
    return 8


def registry_tables(database: Path) -> list[str]:
    with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as connection:
        return [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
