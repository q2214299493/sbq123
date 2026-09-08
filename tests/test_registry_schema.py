from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.registry_schema import CURRENT_VERSION, migrate_registry


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def test_registry_migrates_v2_to_evidence_bound_schema(tmp_path: Path) -> None:
    database = tmp_path / "registry.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO schema_metadata VALUES ('schema_version', '2');
            CREATE TABLE calculations (calculation_id TEXT PRIMARY KEY);
            CREATE TABLE files (file_id TEXT PRIMARY KEY);
            CREATE TABLE results (result_id TEXT PRIMARY KEY);
            CREATE TABLE ts_validations (ts_validation_id TEXT PRIMARY KEY);
            CREATE TABLE ts_strategy_templates (
                template_id TEXT PRIMARY KEY,
                source_calculation_id TEXT,
                fingerprint_json TEXT,
                outcome TEXT
            );
            INSERT INTO calculations VALUES ('preserved');
            """
        )

    assert migrate_registry(database) == CURRENT_VERSION
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM schema_metadata WHERE key='schema_version'"
        ).fetchone() == (str(CURRENT_VERSION),)
        assert connection.execute("SELECT calculation_id FROM calculations").fetchone() == ("preserved",)
        assert {"calculation_compatibility", "ts_barriers", "excel_promotions"} <= {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "source_saddle_calculation_id",
            "frequency_output_file_id",
            "positive_displacement_file_id",
            "negative_displacement_file_id",
            "contract_sha256",
            "atom_map_sha256",
            "compatibility_fingerprint",
        } <= _columns(connection, "ts_validations")


def test_fresh_registry_uses_current_schema(tmp_path: Path) -> None:
    database = tmp_path / "fresh.sqlite3"
    assert migrate_registry(database) == CURRENT_VERSION
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM schema_metadata WHERE key='schema_version'"
        ).fetchone() == (str(CURRENT_VERSION),)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
