from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_text

from .models import StateEvent
from .store import EventStore


def _slug(value: str) -> str:
    rendered = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return rendered[:48] or "entity"


def build_entity_reconciliation_event(
    *,
    event_store: EventStore,
    entity_kind: str,
    entity_id: str,
    keep_event_id: str,
    refresh_evidence: bool = False,
) -> StateEvent:
    """Clone one approved effective event and supersede all conflicting peers."""

    competing = [
        event
        for event in event_store.effective_events()
        if event.entity_key == (entity_kind, entity_id)
    ]
    if len(competing) < 2:
        raise ValueError(f"entity has no effective-event conflict: {entity_kind}:{entity_id}")
    by_id = {event.event_id: event for event in competing}
    source = by_id.get(keep_event_id)
    if source is None:
        raise ValueError("--keep must name one effective conflicting event")
    source_decision = event_store.event_decision(source.event_id)
    if source.review_required and source_decision != "approve":
        raise ValueError("--keep must name an approved event when review is required")

    payload = dict(source.payload)
    evidence = [dict(item) for item in payload["evidence"]]
    refresh_fingerprint = ""
    if refresh_evidence:
        refreshed: list[str] = []
        for item in evidence:
            locator = str(item["locator"])
            if item["authority"] not in {"calculation_file", "structure_output", "module_validation", "repository_document"} or "://" in locator:
                continue
            path = Path(locator)
            if not path.is_absolute():
                path = event_store.project_root / path
            if not path.is_file():
                raise ValueError(f"cannot refresh missing evidence: {locator}")
            item["sha256"] = sha256_file(path)
            item["observed_at"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
            refreshed.append(f"{locator}:{item['sha256']}:{item['observed_at']}")
        if not refreshed:
            raise ValueError("--refresh-evidence found no local authoritative evidence to refresh")
        refresh_fingerprint = sha256_text(":".join(sorted(refreshed)))

    supersedes = sorted(by_id)
    digest = sha256_text(
        f"{source.digest}:{':'.join(supersedes)}:{refresh_fingerprint}:event-chain-reconciliation"
    )
    payload["event_id"] = (
        f"reconciled-{source.event_type.replace('_', '-')}-"
        f"{_slug(entity_kind)}-{_slug(entity_id)}-{digest[:20]}"
    )
    # A preview must be byte-identical to the later --record invocation.  The
    # reconciliation records no new observation; it reaffirms the chosen
    # source event, so the source observation timestamp is the stable record
    # timestamp for this derived event as well.
    # Keep the source event's recorded timestamp.  The reconciliation event ID
    # is content-addressed, so using the wall clock here would make a preview
    # differ from the subsequently recorded event.
    payload["recorded_at"] = str(source.payload["recorded_at"])
    payload["summary"] = (
        f"Reconcile {entity_kind}:{entity_id}; preserve {source.event_id} as the "
        "single effective event and supersede conflicting peers."
    )
    if refresh_evidence:
        payload["summary"] += " Refresh the hash-bound local evidence after user approval."
    payload["evidence"] = evidence
    payload["supersedes"] = supersedes
    review = dict(payload["review"])
    if review["required"]:
        review["status"] = "pending"
        review["reason_codes"] = sorted(
            set(review["reason_codes"]) | {"event_chain_reconciliation"}
        )
    payload["review"] = review
    if source.event_type == "state_observed":
        state_payload = dict(payload["payload"])
        state_payload["project_state_header"] = True
        payload["payload"] = state_payload
    return StateEvent.from_mapping(payload, schema_path=event_store.schema_path)
