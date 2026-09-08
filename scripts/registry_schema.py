from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "modules" / "calculation_registry" / "schema.sql"
CURRENT_VERSION = 8
REQUIRED_COLUMNS = {
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


def migrate_registry(database: Path, schema: Path = SCHEMA) -> int:
    if not schema.is_file():
        raise FileNotFoundError(f"Schema not found: {schema}")
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        version = _schema_version(connection)
        if version is None:
            connection.executescript(schema.read_text(encoding="utf-8"))
            version = CURRENT_VERSION
        elif version > CURRENT_VERSION:
            raise ValueError(f"registry schema {version} is newer than supported version {CURRENT_VERSION}")
        elif version < 2:
            raise ValueError("registry schema versions below 2 require an explicit historical migration")
        if version == 2:
            _migrate_v2(connection)
            connection.commit()
            version = 3
        if version == 3:
            _migrate_v3(connection)
            connection.commit()
            version = 4
        if version == 4:
            _migrate_v4(connection)
            connection.commit()
            version = 5
        if version == 5:
            _migrate_v5(connection)
            connection.commit()
            version = 6
        if version == 6:
            _migrate_v6(connection)
            connection.commit()
            version = 7
        if version == 7:
            connection.execute(TS_STRATEGY_EVENTS_SQL)
            connection.execute("UPDATE schema_metadata SET value='8' WHERE key='schema_version'")
            connection.commit()
        final_version = _schema_version(connection)
        if final_version != CURRENT_VERSION:
            raise ValueError(f"registry migration ended at unexpected schema version {final_version}")
        for table, required in REQUIRED_COLUMNS.items():
            missing = required - _columns(connection, table)
            if missing:
                raise ValueError(f"registry table {table} missing columns: {', '.join(sorted(missing))}")
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise ValueError(f"registry foreign-key check failed for {len(foreign_key_errors)} row(s)")
    return CURRENT_VERSION
