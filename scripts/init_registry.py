from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

try:
    from scripts.registry_schema import migrate_registry
except ModuleNotFoundError:
    from registry_schema import migrate_registry


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "project_registry.sqlite3"
DEFAULT_SCHEMA = ROOT / "modules" / "calculation_registry" / "schema.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the project calculation registry without inserting scientific data.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    schema_path = args.schema.resolve()
    database_path = args.db.resolve()

    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    version = migrate_registry(database_path, schema_path)
    with sqlite3.connect(database_path) as connection:
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()

    print(f"database={database_path}")
    print(f"schema_version={version}")
    print("tables=" + ",".join(name for (name,) in tables))
    print("scientific_records_inserted=0")


if __name__ == "__main__":
    main()
