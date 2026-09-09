"""Append-only compatibility versions and immutable calculation bindings."""
from __future__ import annotations

import json
from scripts.artifact_io import sha256_json
from scripts.provenance_fields import required_text, timestamp
from scripts.scientific_validation import validate_finite_tree
from scripts.registry_transactions import record_event
from scripts.ts_strategy_engine.registry import open_registry


def _revision_identity(compatibility):
    if not isinstance(compatibility, dict) or not compatibility:
        raise ValueError("compatibility must be a nonempty object")
    validate_finite_tree(compatibility)
    return sha256_json(compatibility)


def create_compatibility_revision(database, compatibility, reviewer, reviewed_at, *, supersedes=None):
    required_text(reviewer, "compatibility reviewer")
    timestamp(reviewed_at, "compatibility review time")
    revision = _revision_identity(compatibility)
    if supersedes == revision:
        raise ValueError("compatibility revision cannot supersede itself")
    with open_registry(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT * FROM compatibility_revisions WHERE revision_id=?", (revision,)).fetchone()
        if previous:
            if json.loads(previous["compatibility_json"]) != compatibility or previous["supersedes_revision_id"] != supersedes:
                raise ValueError("immutable compatibility revision conflict")
            return revision
        connection.execute("INSERT INTO compatibility_revisions VALUES (?,?,?,?,?)", (
            revision, json.dumps(compatibility, sort_keys=True), reviewer, reviewed_at, supersedes))
        record_event(connection, "compatibility_created", revision, {"compatibility": compatibility},
                     actor=reviewer, reason="explicit compatibility revision")
        if supersedes:
            record_event(connection, "compatibility_superseded", supersedes, {"new_revision": revision},
                         actor=reviewer, reason="new revision; historical bindings retained")
    return revision


def register_calculation_compatibility(database, calculation_id, compatibility, reviewer, reviewed_at):
    revision = _revision_identity(compatibility)
    required_text(reviewer, "compatibility reviewer")
    timestamp(reviewed_at, "compatibility review time")
    with open_registry(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute("SELECT * FROM calculation_compatibility WHERE calculation_id=?", (calculation_id,)).fetchone()
        if existing:
            if existing["compatibility_fingerprint"] != revision or json.loads(existing["compatibility_json"]) != compatibility:
                raise ValueError("immutable calculation compatibility; create a new revision and a new calculation")
            return revision
        connection.execute("INSERT INTO calculation_compatibility VALUES (?,?,?,?,?)", (
            calculation_id, revision, json.dumps(compatibility, sort_keys=True), reviewer, reviewed_at))
        record_event(connection, "compatibility_created", calculation_id, {"revision_id": revision},
                     actor=reviewer, reason="original calculation compatibility binding")
    return revision
