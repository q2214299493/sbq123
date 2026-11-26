from __future__ import annotations

from scripts.runtime_resources import explicit_database

from scripts.runtime_resources import resource_path

import argparse
from pathlib import Path

try:
    from scripts.registry_schema import migrate_registry, registry_tables
except ModuleNotFoundError:
    from registry_schema import migrate_registry, registry_tables


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "project_registry.sqlite3"
DEFAULT_SCHEMA = resource_path('modules/calculation_registry/schema.sql')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the project calculation registry without inserting scientific data.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.db = explicit_database(args.db, DEFAULT_DB)
    schema_path = args.schema.resolve()
    database_path = args.db.resolve()

    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    version = migrate_registry(database_path, schema_path)
    tables = registry_tables(database_path)

    print(f"database={database_path}")
    print(f"schema_version={version}")
    print("tables=" + ",".join(tables))
    print("scientific_records_inserted=0")


if __name__ == "__main__":
    main()
