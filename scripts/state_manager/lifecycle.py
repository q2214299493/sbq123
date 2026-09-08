from __future__ import annotations

from pathlib import Path
import json
import re

from scripts.artifact_io import canonical_json, sha256_bytes, sha256_file, sha256_text

from .models import StateEvent, utc_now
from .projections import END_MARKER, START_MARKER, load_policy
from .store import EventStore


TASK_PHASES = {"open", "active", "blocked", "verification"}
ALLOWED_TRANSITIONS = {
    "open": {"active", "blocked"},
    "active": {"blocked", "verification"},
    "blocked": {"active", "verification"},
    "verification": {"active", "blocked"},
}


def task_payload(event: StateEvent) -> dict[str, object]:
    if event.event_type == "baseline_adopted":
        return dict(event.payload["payload"]["task"])
    return dict(event.payload["payload"])


def effective_phase(event: StateEvent) -> str:
    return str(task_payload(event).get("phase", "active"))


def build_task_transition_event(
    *,
    event_store: EventStore,
    to_phase: str,
    reason: str,
    evidence_paths: list[Path],
    schema_path: Path,
    policy_path: Path,
) -> StateEvent:
    source = event_store.current_task_source()
    if source is None:
        raise ValueError("no active task to transition")
    _require_current_task_projection(source, event_store=event_store, policy_path=policy_path)
    if to_phase not in TASK_PHASES:
        raise ValueError(f"invalid task phase: {to_phase}")
    from_phase = effective_phase(source)
    if to_phase not in ALLOWED_TRANSITIONS[from_phase]:
        raise ValueError(f"invalid task phase transition: {from_phase} -> {to_phase}")
    if not reason.strip():
        raise ValueError("task transition requires a reason")
    if not evidence_paths:
        raise ValueError("task transition requires at least one evidence file")

    observed_at = utc_now()
    evidence = []
    for supplied in evidence_paths:
        path = supplied.resolve()
        if not path.is_file():
            raise ValueError(f"task transition evidence is not a file: {path}")
        try:
            locator = path.relative_to(event_store.project_root).as_posix()
        except ValueError as error:
            raise ValueError("task transition evidence must be inside the repository") from error
        evidence.append(
            {
                "locator": locator,
                "sha256": sha256_file(path),
                "authority": "repository_document",
                "observed_at": observed_at,
            }
        )

    payload = task_payload(source)
    payload["phase"] = to_phase
    payload["lifecycle_transition"] = {
        "from_phase": from_phase,
        "to_phase": to_phase,
        "reason": reason.strip(),
        "source_event_id": source.event_id,
        "source_event_sha256": source.digest,
    }
    identity = sha256_bytes(
        canonical_json(
            {
                "source": source.digest,
                "to_phase": to_phase,
                "reason": reason.strip(),
                "evidence": evidence,
            }
        )
    )[:24]
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"task-transition-{identity}",
            "event_type": "task_updated",
            "entity": {
                "kind": "task",
                "id": "task-current",
                "module": source.payload["entity"].get("module"),
            },
            "occurred_at": observed_at,
            "recorded_at": observed_at,
            "summary": f"Task phase {from_phase} -> {to_phase}: {reason.strip()}",
            "payload": payload,
            "evidence": evidence,
            "supersedes": [] if source.event_type == "baseline_adopted" else [source.event_id],
            "review": {
                "required": False,
                "reason_codes": [],
                "status": "not_required",
            },
        },
        schema_path=schema_path,
    )


def _require_current_task_projection(
    source: StateEvent,
    *,
    event_store: EventStore,
    policy_path: Path,
) -> None:
    policy = load_policy(policy_path)
    target_name = str(policy["managed_views"]["current_task"])
    target = event_store.project_root / target_name
    manifest_path = event_store.project_root / policy["paths"]["projection_manifest"]
    if not target.is_file() or not manifest_path.is_file():
        raise ValueError("current task projection must be adopted before a phase transition")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest.get("projections", {}).get(f"{target_name}#current_task")
    if not isinstance(record, dict):
        raise ValueError("current task projection manifest is missing")
    if record.get("source_event_id") != source.event_id:
        raise ValueError("current task projection source differs from the effective task")
    start = START_MARKER.format(block_id="current_task")
    end = END_MARKER.format(block_id="current_task")
    match = re.search(
        re.escape(start) + r".*?" + re.escape(end),
        target.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    actual = sha256_text(match.group(0)) if match else None
    if actual != record.get("managed_block_sha256"):
        raise ValueError("current task projection drift must be reconciled before a phase transition")
