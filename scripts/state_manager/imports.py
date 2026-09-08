from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_text

from .baseline import _current_gate_payload, _task_payload
from .models import StateEvent
from .projections import END_MARKER, START_MARKER
from .store import EventStore


def _observed_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def build_current_task_import(
    *, project_root: Path, event_store: EventStore, schema_path: Path
) -> StateEvent:
    root = project_root.resolve()
    path = root / "tasks" / "current_task.md"
    text = path.read_text(encoding="utf-8")
    unmanaged = text.replace(START_MARKER.format(block_id="current_task"), "").replace(
        END_MARKER.format(block_id="current_task"), ""
    )
    payload = _task_payload(unmanaged)
    phase_match = re.search(r"(?m)^- Phase:\s*`([^`]+)`\s*$", text)
    payload["phase"] = phase_match.group(1) if phase_match else "active"
    payload["adopt_current_projection"] = True
    source = event_store.current_task_source()
    if source is None:
        raise ValueError("no effective task event exists for current-task import")
    digest = sha256_file(path)
    observed_at = _observed_at(path)
    identity = sha256_text(f"task:{digest}:{source.digest}")[:24]
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"task-import-{identity}",
            "event_type": "task_updated",
            "entity": {
                "kind": "task",
                "id": str(source.payload["entity"]["id"]),
                "module": source.payload["entity"].get("module"),
            },
            "occurred_at": observed_at,
            "recorded_at": observed_at,
            "summary": "Import the existing reviewed current-task projection into the event ledger.",
            "payload": payload,
            "evidence": [
                {
                    "locator": "tasks/current_task.md",
                    "sha256": digest,
                    "authority": "repository_document",
                    "observed_at": observed_at,
                }
            ],
            "supersedes": [] if source.event_type == "baseline_adopted" else [source.event_id],
            "review": {
                "required": True,
                "reason_codes": ["manual_projection_import"],
                "status": "pending",
            },
        },
        schema_path=schema_path,
    )


def build_current_gate_import(
    *, project_root: Path, event_store: EventStore, schema_path: Path
) -> StateEvent:
    root = project_root.resolve()
    path = root / "docs" / "02_CURRENT_STATE.md"
    payload = _current_gate_payload(path.read_text(encoding="utf-8"))
    payload["adopt_current_projection"] = True
    block_id = str(payload["block_id"])
    prior = event_store.latest_by_entity().get(("state", block_id))
    digest = sha256_file(path)
    observed_at = _observed_at(path)
    identity = sha256_text(f"state:{block_id}:{digest}")[:24]
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"state-import-{identity}",
            "event_type": "state_observed",
            "entity": {"kind": "state", "id": block_id, "module": "state_handoff"},
            "occurred_at": observed_at,
            "recorded_at": observed_at,
            "summary": "Import the existing reviewed Current Gate projection into the event ledger.",
            "payload": payload,
            "evidence": [
                {
                    "locator": "docs/02_CURRENT_STATE.md",
                    "sha256": digest,
                    "authority": "repository_document",
                    "observed_at": observed_at,
                }
            ],
            "supersedes": [prior.event_id] if prior else [],
            "review": {
                "required": True,
                "reason_codes": ["manual_projection_import"],
                "status": "pending",
            },
        },
        schema_path=schema_path,
    )
