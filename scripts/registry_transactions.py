"""Registry snapshot, approval and durable transaction receipts (no scientific rules)."""
from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from scripts.artifact_io import sha256_json, require_sha256
from scripts.provenance_fields import required_text, timestamp
from scripts.ts_strategy_engine.registry import utc_now


def database_fingerprint(connection: sqlite3.Connection) -> str:
    schema = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name").fetchall()
    rows = {}
    for kind, name, _, _ in schema:
        if kind != "table":
            continue
        escaped = name.replace('"', '""')
        query = f'SELECT * FROM "{escaped}"'
        if name == "registry_events":
            query += " WHERE event_type != 'batch_failed'"
        values = [list(row) for row in connection.execute(query)]
        rows[name] = sorted(values, key=lambda row: json.dumps(row, sort_keys=True, default=str))
    # Failure/audit events are excluded so a rolled-back plan can be retried.
    return sha256_json({"schema": [list(row) for row in schema], "rows": rows})


def record_event(connection, event_type, entity_id, payload, *, actor, reason, event_id=None):
    required_text(actor, "event actor")
    required_text(reason, "event reason")
    connection.execute("INSERT INTO registry_events VALUES (?,?,?,?,?,?,?)", (
        event_id or uuid4().hex, event_type, entity_id, json.dumps(payload, sort_keys=True),
        utc_now(), actor, reason,
    ))


def approve_plan(plan: dict, *, reviewer: str, reviewed_at: str) -> dict:
    """Create an explicit approval document for the exact plan shown to a reviewer."""
    required_text(reviewer, "approval reviewer")
    timestamp(reviewed_at, "approval reviewed_at")
    if reviewer != plan["approval_identity"]:
        raise ValueError("approval reviewer does not match the planned identity")
    return {"plan_sha256": plan["plan_sha256"], "database_fingerprint": plan["database_fingerprint"],
            "reviewer": reviewer, "reviewed_at": reviewed_at, "decision": "approve",
            "scope": plan["scope"]}


def verify_approval(plan, approval, batch, confirmed_sha256):
    require_sha256(confirmed_sha256, label="confirmed plan hash")
    core = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if confirmed_sha256 != sha256_json(core) or plan.get("plan_sha256") != confirmed_sha256:
        raise ValueError("registry plan confirmation hash mismatch")
    if plan["scope"] != sorted({item["table"] for item in plan["actions"]}):
        raise ValueError("mutation scope does not match actions")
    if plan["batch_sha256"] != sha256_json(batch):
        raise ValueError("approved batch changed after approval")
    required_text(approval.get("reviewer"), "approval reviewer")
    timestamp(approval.get("reviewed_at"), "approval reviewed_at")
    if approval != approve_plan(plan, reviewer=approval["reviewer"], reviewed_at=approval["reviewed_at"]):
        raise ValueError("approval identity, plan hash, database fingerprint or mutation scope mismatch")


def applied_receipt(connection, plan):
    row = connection.execute("SELECT * FROM registry_applications WHERE batch_id=?", (plan["batch_id"],)).fetchone()
    if row is None:
        return None
    if row["plan_sha256"] != plan["plan_sha256"] or row["batch_sha256"] != plan["batch_sha256"]:
        raise ValueError("batch already applied with another immutable plan")
    return {**json.loads(row["receipt_json"]), "already_applied": True}
