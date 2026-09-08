from __future__ import annotations

from pathlib import Path

from .models import StateEvent, utc_now
from .store import EventStore


def derive_task_completion_event(
    acceptance: StateEvent,
    *,
    event_store: EventStore,
    schema_path: Path,
) -> StateEvent:
    """Build the only task-closure event allowed by a formal acceptance record."""

    if acceptance.event_type != "task_acceptance_recorded":
        raise ValueError("end checkpoint requires task_acceptance_recorded")
    payload = acceptance.payload["payload"]
    source = event_store.get(str(payload["task_event_id"]))
    recorded_at = utc_now()
    requires_review = bool(payload["requires_user_review"])
    reason_codes = [str(item) for item in payload.get("review_reason_codes", [])]
    if payload["handoff"]["errors"]:
        reason_codes.append("unresolved_error_handoff")
    if payload["handoff"]["decisions"]:
        reason_codes.append("durable_decision_handoff")
    if requires_review:
        reason_codes.append("task_closure_review")
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"task-completed-{acceptance.digest[:24]}",
            "event_type": "task_completed",
            "entity": {
                "kind": "task",
                "id": str(payload["task_entity_id"]),
                "module": source.payload["entity"].get("module"),
            },
            "occurred_at": acceptance.payload["occurred_at"],
            "recorded_at": recorded_at,
            "summary": str(payload["completion_summary"]),
            "payload": {
                "completion_summary": str(payload["completion_summary"]),
                "task_event_id": source.event_id,
                "task_event_sha256": source.digest,
                "acceptance_event_id": acceptance.event_id,
                "acceptance_event_sha256": acceptance.digest,
                "handoff": payload["handoff"],
            },
            "evidence": list(acceptance.payload["evidence"]),
            "supersedes": (
                [] if source.event_type == "baseline_adopted" else [source.event_id]
            ),
            "review": {
                "required": requires_review,
                "reason_codes": sorted(set(reason_codes)),
                "status": "pending" if requires_review else "not_required",
            },
        },
        schema_path=schema_path,
    )
