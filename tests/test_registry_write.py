from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from scripts.artifact_io import sha256_json
from scripts.registry_schema import migrate_registry
from scripts.registry_write import (
    apply_registry_batch,
    plan_registry_batch,
    validate_registry_batch,
)


ROOT = Path(__file__).resolve().parents[1]


def _batch() -> dict:
    return {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch",
        "batch_id": "fixture-batch-1",
        "created_at": "2026-08-18T00:00:00Z",
        "reviewer": "test-reviewer",
        "reason": "transactional registry gateway test",
        "rows": {
            "calculations": [
                {
                    "calculation_id": "fixture-calc",
                    "module": "test_module",
                    "purpose": "test",
                    "workflow_status": "registered",
                    "created_at": "2026-08-18T00:00:00Z",
                }
            ],
            "jobs": [
                {
                    "job_record_id": "fixture-job",
                    "calculation_id": "fixture-calc",
                    "scheduler_job_id": "123",
                    "scheduler": "LSF",
                    "server_alias": "sunboquan-codex",
                    "remote_directory": "/remote/fixture",
                }
            ],
            "job_status_history": [
                {
                    "job_record_id": "fixture-job",
                    "scheduler_status": "DONE",
                    "scientific_status": "test_only",
                    "checked_at": "2026-08-18T00:01:00Z",
                }
            ],
            "files": [
                {
                    "file_id": "fixture-outcar",
                    "calculation_id": "fixture-calc",
                    "job_record_id": "fixture-job",
                    "role": "output",
                    "filename": "OUTCAR",
                    "storage_mode": "test",
                    "existence_status": "confirmed",
                    "sha256": "a" * 64,
                }
            ],
            "results": [
                {
                    "result_id": "fixture-energy",
                    "calculation_id": "fixture-calc",
                    "result_name": "total_energy_eV",
                    "numeric_value": -1.0,
                    "unit": "eV",
                    "source_file_id": "fixture-outcar",
                    "validation_status": "test_only",
                    "created_at": "2026-08-18T00:02:00Z",
                }
            ],
            "reviews": [
                {
                    "review_id": "fixture-review",
                    "calculation_id": "fixture-calc",
                    "review_type": "test",
                    "decision": "accepted",
                    "reviewer": "test-reviewer",
                    "reviewed_at": "2026-08-18T00:03:00Z",
                    "reason": "fixture only",
                }
            ],
            "calculation_compatibility": [
                {
                    "calculation_id": "fixture-calc",
                    "compatibility_fingerprint": "b" * 64,
                    "compatibility_json": json.dumps({"branch": "fixture"}),
                    "reviewer": "test-reviewer",
                    "reviewed_at": "2026-08-18T00:03:00Z",
                }
            ],
        },
    }


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "registry.sqlite3"
    migrate_registry(database)
    return database


def test_registry_batch_plan_apply_and_repeat_are_deterministic(tmp_path: Path) -> None:
    database = _database(tmp_path)
    batch = _batch()
    plan = plan_registry_batch(database, batch)
    assert plan["insert_count"] == 7
    assert plan["update_count"] == 0
    assert plan["unchanged_count"] == 0

    result = apply_registry_batch(
        database,
        batch,
        confirmed_sha256=plan["batch_sha256"],
    )
    assert result["inserted"] == 7
    assert result["updated"] == 0
    assert result["unchanged"] == 0
    repeated = plan_registry_batch(database, batch)
    assert repeated["insert_count"] == 0
    assert repeated["update_count"] == 0
    assert repeated["unchanged_count"] == 7


def test_registry_batch_applies_hash_bound_workflow_status_change(tmp_path: Path) -> None:
    database = _database(tmp_path)
    batch = _batch()
    apply_registry_batch(database, batch, confirmed_sha256=sha256_json(batch))
    status_batch = {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch",
        "batch_id": "fixture-status-change-1",
        "created_at": "2026-08-18T00:10:00Z",
        "reviewer": "test-reviewer",
        "reason": "correct stale workflow status",
        "rows": {},
        "workflow_status_changes": [
            {
                "status_change_id": "fixture-status-change-row-1",
                "calculation_id": "fixture-calc",
                "expected_workflow_status": "registered",
                "new_workflow_status": "accepted",
                "changed_at": "2026-08-18T00:10:00Z",
                "reviewer": "test-reviewer",
                "reason": "accepted evidence already exists",
            }
        ],
    }
    plan = plan_registry_batch(database, status_batch)
    assert plan["insert_count"] == 0
    assert plan["update_count"] == 1
    result = apply_registry_batch(
        database,
        status_batch,
        confirmed_sha256=plan["batch_sha256"],
    )
    assert result["updated"] == 1
    repeated = plan_registry_batch(database, status_batch)
    assert repeated["update_count"] == 0
    assert repeated["unchanged_count"] == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT workflow_status FROM calculations WHERE calculation_id='fixture-calc'"
        ).fetchone()[0] == "accepted"
        assert connection.execute(
            "SELECT previous_workflow_status, new_workflow_status "
            "FROM calculation_workflow_status_history"
        ).fetchone() == ("registered", "accepted")


def test_registry_batch_rejects_stale_workflow_status_expectation(tmp_path: Path) -> None:
    database = _database(tmp_path)
    batch = _batch()
    apply_registry_batch(database, batch, confirmed_sha256=sha256_json(batch))
    status_batch = {
        "schema_version": 1,
        "document_kind": "calculation_registry_batch",
        "batch_id": "fixture-status-change-stale",
        "created_at": "2026-08-18T00:10:00Z",
        "reviewer": "test-reviewer",
        "reason": "fixture stale expectation",
        "rows": {},
        "workflow_status_changes": [
            {
                "status_change_id": "fixture-status-change-stale-row",
                "calculation_id": "fixture-calc",
                "expected_workflow_status": "submitted",
                "new_workflow_status": "accepted",
                "changed_at": "2026-08-18T00:10:00Z",
                "reviewer": "test-reviewer",
                "reason": "fixture stale expectation",
            }
        ],
    }
    with pytest.raises(ValueError, match="expected 'submitted'"):
        plan_registry_batch(database, status_batch)


def test_registry_batch_requires_exact_reviewed_hash(tmp_path: Path) -> None:
    database = _database(tmp_path)
    batch = _batch()
    with pytest.raises(ValueError, match="confirmation hash"):
        apply_registry_batch(database, batch, confirmed_sha256="0" * 64)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM calculations").fetchone()[0] == 0


def test_registry_batch_rolls_back_on_foreign_key_failure(tmp_path: Path) -> None:
    database = _database(tmp_path)
    batch = _batch()
    batch["rows"]["jobs"][0]["calculation_id"] = "missing-calculation"
    with pytest.raises(sqlite3.IntegrityError):
        apply_registry_batch(
            database,
            batch,
            confirmed_sha256=sha256_json(batch),
        )
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM calculations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_registry_batch_rejects_unknown_tables_and_conflicting_primary_keys(
    tmp_path: Path,
) -> None:
    unknown = _batch()
    unknown["rows"]["schema_metadata"] = [{"key": "schema_version", "value": "999"}]
    with pytest.raises(ValueError, match="unsupported tables"):
        validate_registry_batch(unknown)

    database = _database(tmp_path)
    batch = _batch()
    apply_registry_batch(database, batch, confirmed_sha256=sha256_json(batch))
    changed = _batch()
    changed["rows"]["calculations"][0]["module"] = "different_module"
    with pytest.raises(ValueError, match="conflicts with existing"):
        plan_registry_batch(database, changed)


def test_no_new_direct_sqlite_registry_writers() -> None:
    policy = yaml.safe_load(
        (ROOT / "configs" / "registry_legacy_writers.yaml").read_text(encoding="utf-8")
    )
    assert policy["policy"] == "no_new_direct_sqlite_registry_writers"
    allowed = set(policy["legacy_writers"])
    direct_writers = set()
    for path in (ROOT / "calculations").rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="replace")
        if "sqlite3.connect" in source and "INSERT" in source and "INTO" in source:
            direct_writers.add(path.relative_to(ROOT).as_posix())
    assert direct_writers - allowed == set()
