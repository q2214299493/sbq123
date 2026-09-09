"""One-off authorized rollout: SQLite snapshots, owner migration, row audit."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from scripts.registry_schema import migrate_registry, rollback_registry_v9, validate_schema

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/project_registry.sqlite3"
BACKUP = ROOT / "data/backups/registry_v8_before_migration_20260909"


def snapshot(source, destination):
    if destination.exists():
        raise FileExistsError(destination)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)


def inspect(path):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as c:
        c.execute("BEGIN")
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
        version = int(c.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()[0])
        tables = {}
        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            if name in {"schema_metadata", "sqlite_sequence"}:
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            hashes = sorted(hashlib.sha256(json.dumps(row, ensure_ascii=False, default=str).encode()).hexdigest()
                            for row in c.execute("SELECT * FROM " + quoted))
            tables[name] = {"rows": len(hashes), "sha256": hashlib.sha256("\n".join(hashes).encode()).hexdigest()}
        return {"version": version, "tables": tables}


def preserves(old, new):
    assert all(new["tables"].get(k) == v for k, v in old["tables"].items()), "old table content changed"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["rehearse", "apply"])
    args = parser.parse_args()
    original = BACKUP / "original_v8.sqlite3"
    rehearsal = BACKUP / "rehearsal.sqlite3"
    if args.phase == "rehearse":
        BACKUP.mkdir(parents=True, exist_ok=False)
        snapshot(DB, original)
        before = inspect(original)
        assert before["version"] == 8
        snapshot(original, rehearsal)
        assert migrate_registry(rehearsal) == 9
        preserves(before, inspect(rehearsal))
        assert rollback_registry_v9(rehearsal) == 8
        assert inspect(rehearsal) == before
        assert migrate_registry(rehearsal) == 9
        preserves(before, inspect(rehearsal))
        assert inspect(DB) == before, "production changed during rehearsal"
        print(json.dumps({"phase": "rehearsal_pass", "backup": str(original),
                          "backup_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                          "old_tables": before["tables"], "rollback_test": "PASS"}))
    else:
        before = inspect(original)
        assert before["version"] == 8 and inspect(rehearsal)["version"] == 9
        preserves(before, inspect(rehearsal))
        assert inspect(DB) == before, "production changed: fresh backup/rehearsal required"
        snapshot(DB, BACKUP / "immediate_preapply_v8.sqlite3")
        assert migrate_registry(DB) == 9
        after = inspect(DB)
        preserves(before, after)
        with sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True) as c:
            validate_schema(c)
        print(json.dumps({"phase": "production_migrated", "version": after["version"],
                          "old_tables_unchanged": len(before["tables"]),
                          "old_rows_unchanged": sum(t["rows"] for t in before["tables"].values()),
                          "integrity": "ok", "foreign_keys": "ok", "backup": str(original)}))


if __name__ == "__main__":
    main()
