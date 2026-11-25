"""Append-only strategy history; scientific results stay in the existing registry tables."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from scripts.artifact_io import canonical_json, sha256_json

from .registry import open_registry, utc_now

DEFAULT_DATABASE = Path(__file__).resolve().parents[2] / "data/project_registry.sqlite3"
EVENT_TYPES = {"variant", "attempt", "outcome"}


def append_event(connection: sqlite3.Connection, kind: str, entity_id: str, payload: dict[str, Any]) -> str:
    if kind not in EVENT_TYPES:
        raise ValueError(f"unknown strategy event type: {kind}")
    digest = sha256_json(payload)
    existing = connection.execute(
        "SELECT payload_sha256 FROM ts_strategy_events WHERE event_type=? AND entity_id=?", (kind, entity_id)
    ).fetchone()
    if existing:
        if existing[0] != digest:
            raise ValueError(f"immutable {kind} already exists: {entity_id}")
        return entity_id
    connection.execute(
        "INSERT INTO ts_strategy_events(event_type,entity_id,payload_json,payload_sha256,created_at) VALUES (?,?,?,?,?)",
        (kind, entity_id, canonical_json(payload).decode(), digest, utc_now()),
    )
    return entity_id


def read_events(database: Path, kind: str) -> dict[str, dict[str, Any]]:
    with open_registry(database) as connection:
        rows = connection.execute(
            "SELECT entity_id,payload_json,payload_sha256 FROM ts_strategy_events WHERE event_type=? ORDER BY rowid", (kind,)
        ).fetchall()
    result = {}
    for row in rows:
        payload = json.loads(row[1])
        if sha256_json(payload) != row[2]:
            raise ValueError(f"strategy history hash mismatch: {row[0]}")
        if kind == "outcome" and "outcome_revision" in payload:
            revision = payload["outcome_revision"]
            target = revision["attempt_id"]
            if target not in result or sha256_json(result[target]) != revision["previous_sha256"]:
                raise ValueError(f"stale outcome revision: {row[0]}")
            result[target] = payload
        else:
            result[row[0]] = payload
    return result


def get_event(database: Path, kind: str, entity_id: str) -> dict[str, Any]:
    records = read_events(database, kind)
    if entity_id not in records:
        raise ValueError(f"unknown {kind}: {entity_id}")
    return records[entity_id]


def _history_token(connection: sqlite3.Connection) -> str:
    return sha256_json([tuple(row) for row in connection.execute(
        "SELECT event_type,entity_id,payload_sha256 FROM ts_strategy_events ORDER BY event_type,entity_id"
    )])


def history_token(database: Path) -> str:
    with open_registry(database) as connection:
        return _history_token(connection)


def save_event(database: Path, kind: str, entity_id: str, payload: dict[str, Any], *, expected_history: str | None = None) -> str:
    with open_registry(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if expected_history is not None and expected_history != _history_token(connection):
            raise ValueError("strategy history changed concurrently; reload before retrying")
        return append_event(connection, kind, entity_id, payload)
