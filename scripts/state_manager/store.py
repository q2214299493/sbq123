from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from scripts.artifact_io import sha256_file

from .models import ROOT, StateEvent, utc_now


DEFAULT_EVENTS_DIR = ROOT / "modules" / "state_handoff" / "events"
FILE_AUTHORITIES = {
    "calculation_file",
    "structure_output",
    "module_validation",
    "calculation_registry",
    "repository_document",
}


def _write_immutable_json(target: Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if existing != payload:
                raise ValueError(f"immutable event target already differs: {target}")
    finally:
        temporary.unlink(missing_ok=True)


class EventStore:
    """Immutable per-file event store with idempotent inserts."""

    def __init__(
        self,
        events_dir: Path = DEFAULT_EVENTS_DIR,
        *,
        schema_path: Path | None = None,
        project_root: Path = ROOT,
    ) -> None:
        self.events_dir = events_dir
        self.schema_path = schema_path
        self.project_root = project_root.resolve()

    def _load_path(self, path: Path) -> StateEvent:
        if self.schema_path is None:
            return StateEvent.from_path(path)
        return StateEvent.from_path(path, schema_path=self.schema_path)

    def load_all(self) -> list[StateEvent]:
        if not self.events_dir.exists():
            return []
        events = [self._load_path(path) for path in sorted(self.events_dir.glob("*.json"))]
        identifiers = [event.event_id for event in events]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate state event IDs")
        known = set(identifiers)
        for event in events:
            missing = set(event.payload["supersedes"]) - known
            if missing:
                raise ValueError(
                    f"event {event.event_id} supersedes missing events: {sorted(missing)}"
                )
        return sorted(
            events,
            key=lambda event: (
                str(event.payload["recorded_at"]),
                event.event_id,
            ),
        )

    def get(self, event_id: str) -> StateEvent:
        path = self.events_dir / f"{event_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"unknown state event: {event_id}")
        return self._load_path(path)

    def record(self, event: StateEvent) -> Path:
        self.events_dir.mkdir(parents=True, exist_ok=True)
        target = self.events_dir / f"{event.event_id}.json"
        if target.exists():
            existing = self._load_path(target)
            if existing.digest != event.digest:
                raise ValueError(
                    f"immutable event ID already has different content: {event.event_id}"
                )
            return target

        known = {item.event_id for item in self.load_all()}
        missing = set(event.payload["supersedes"]) - known
        if missing:
            raise ValueError(f"superseded events do not exist: {sorted(missing)}")
        if event.event_type == "task_acceptance_recorded":
            self._validate_task_acceptance(event)
        if event.event_type == "task_updated" and event.payload["payload"].get("lifecycle_transition"):
            self._validate_task_transition(event)
        if event.event_type == "task_completed":
            self._validate_task_completion(event)
        self.verify_evidence(event)
        _write_immutable_json(target, event.payload)
        return target

    def _validate_task_transition(self, event: StateEvent) -> None:
        from .lifecycle import ALLOWED_TRANSITIONS, effective_phase

        transition = event.payload["payload"]["lifecycle_transition"]
        source = self.get(str(transition["source_event_id"]))
        if source.digest != transition["source_event_sha256"]:
            raise ValueError("task transition source-event hash mismatch")
        current = self.current_task_source()
        if current is None or current.event_id != source.event_id:
            raise ValueError("task transition source is not the current effective task")
        from_phase = effective_phase(source)
        to_phase = str(transition["to_phase"])
        if transition["from_phase"] != from_phase:
            raise ValueError("task transition from_phase does not match current task")
        if to_phase not in ALLOWED_TRANSITIONS[from_phase]:
            raise ValueError(f"invalid task phase transition: {from_phase} -> {to_phase}")
        expected_supersedes = [] if source.event_type == "baseline_adopted" else [source.event_id]
        if event.payload["supersedes"] != expected_supersedes:
            raise ValueError("task transition supersession does not match its source")

    def _validate_task_acceptance(self, event: StateEvent) -> None:
        payload = event.payload["payload"]
        for prior in self.load_all():
            if prior.event_type != "task_acceptance_recorded":
                continue
            prior_handoff = prior.payload["payload"].get("handoff", {})
            for collection in ("backlog_items", "errors", "decisions"):
                used = {
                    str(item["id"])
                    for item in prior_handoff.get(collection, [])
                }
                repeated = {
                    str(item["id"])
                    for item in payload["handoff"][collection]
                } & used
                if repeated:
                    raise ValueError(
                        f"task handoff {collection} ID already exists: {sorted(repeated)}"
                    )
        source = self.get(str(payload["task_event_id"]))
        if source.digest != payload["task_event_sha256"]:
            raise ValueError("task acceptance source-event hash mismatch")
        current = self.current_task_source(str(payload["task_entity_id"]))
        if current is None or current.event_id != source.event_id:
            raise ValueError("task acceptance source is not the current effective task")
        if source.event_type == "baseline_adopted":
            task_payload = source.payload["payload"]["task"]
        else:
            if source.entity_key != ("task", str(payload["task_entity_id"])):
                raise ValueError("task acceptance source does not match task_entity_id")
            if source.event_type not in {"task_opened", "task_updated"}:
                raise ValueError("task acceptance source must be an active task event")
            task_payload = source.payload["payload"]
        expected = [str(item).strip() for item in task_payload["done_when"]]
        actual = [str(item["criterion"]).strip() for item in payload["done_when_results"]]
        if actual != expected:
            raise ValueError("task acceptance must cover every Done When criterion exactly once and in order")
        if str(task_payload.get("phase", "active")) != "verification":
            raise ValueError("task acceptance requires current phase verification")

    def _validate_task_completion(self, event: StateEvent) -> None:
        payload = event.payload["payload"]
        acceptance = self.get(str(payload["acceptance_event_id"]))
        if acceptance.event_type != "task_acceptance_recorded":
            raise ValueError("task completion requires a formal acceptance event")
        if acceptance.digest != payload["acceptance_event_sha256"]:
            raise ValueError("task completion acceptance-event hash mismatch")
        acceptance_payload = acceptance.payload["payload"]
        if acceptance_payload["verdict"] != "accepted":
            raise ValueError("task completion acceptance verdict is not accepted")
        if acceptance_payload["task_event_id"] != payload["task_event_id"]:
            raise ValueError("task completion and acceptance reference different task events")
        if acceptance_payload["task_event_sha256"] != payload["task_event_sha256"]:
            raise ValueError("task completion task-event hash mismatch")
        if acceptance_payload["handoff"] != payload["handoff"]:
            raise ValueError("task completion handoff differs from formal acceptance")
        source = self.get(str(payload["task_event_id"]))
        if (
            source.event_type != "baseline_adopted"
            and payload["task_event_id"] not in event.payload["supersedes"]
        ):
            raise ValueError("task completion must supersede its accepted task event")

    def current_task_source(self, task_entity_id: str = "task-current") -> StateEvent | None:
        latest = self.latest_by_entity()
        current = latest.get(("task", task_entity_id))
        if current is None and task_entity_id == "task-current":
            active_tasks = [
                event
                for (kind, _), event in latest.items()
                if kind == "task" and event.event_type != "task_completed"
            ]
            if len(active_tasks) > 1:
                raise ValueError("multiple effective active task entities")
            current = active_tasks[0] if active_tasks else None
        if current is not None:
            return None if current.event_type == "task_completed" else current
        baselines = [
            event
            for event in self.effective_events()
            if event.event_type == "baseline_adopted"
        ]
        if len(baselines) > 1:
            raise ValueError("multiple effective baseline task sources")
        return baselines[0] if baselines else None

    def verify_evidence(self, event: StateEvent) -> None:
        for evidence in event.payload["evidence"]:
            if evidence["authority"] not in FILE_AUTHORITIES:
                continue
            locator = str(evidence["locator"])
            if "://" in locator:
                continue
            source = Path(locator)
            if not source.is_absolute():
                source = self.project_root / source
            if not source.is_file():
                raise ValueError(f"evidence file does not exist: {locator}")
            if sha256_file(source) != evidence["sha256"]:
                raise ValueError(f"evidence hash changed: {locator}")

    def effective_events(self) -> list[StateEvent]:
        events = self.load_all()
        decisions = {
            event.event_id: self._event_decision(event.event_id, events=events)
            for event in events
            if event.event_type != "review_decision"
        }
        eligible = [
            event
            for event in events
            if decisions.get(event.event_id) != "reject"
            and (not event.review_required or decisions.get(event.event_id) == "approve")
        ]
        superseded = {
            event_id
            for event in eligible
            for event_id in event.payload["supersedes"]
        }
        return [event for event in eligible if event.event_id not in superseded]

    def pending_review_events(self) -> list[StateEvent]:
        events = self.load_all()
        return [
            event
            for event in events
            if event.event_type != "review_decision"
            and event.review_required
            and self._event_decision(event.event_id, events=events) is None
        ]

    def actionable_pending_review_events(self) -> list[StateEvent]:
        """Return only review requests that can still advance current state.

        Older unreviewed events remain immutable history, but are not useful
        queue items once an approved current event for the same entity has
        superseded their source.  A pending event remains actionable only when
        it directly supersedes that current source (that is, it is a proposed
        next state), or when its entity has no current projection.
        """

        current = self.latest_by_entity()
        actionable: list[StateEvent] = []
        for event in self.pending_review_events():
            source = current.get(event.entity_key)
            if source is not None and source.event_id not in event.payload["supersedes"]:
                continue
            actionable.append(event)
        return actionable

    def latest_by_entity(self) -> dict[tuple[str, str], StateEvent]:
        grouped: dict[tuple[str, str], list[StateEvent]] = defaultdict(list)
        for event in self.effective_events():
            if event.event_type == "review_decision":
                continue
            grouped[event.entity_key].append(event)
        conflicts = {key: value for key, value in grouped.items() if len(value) > 1}
        if conflicts:
            rendered = ", ".join(
                f"{kind}:{identifier}={','.join(item.event_id for item in events)}"
                for (kind, identifier), events in conflicts.items()
            )
            raise ValueError(f"multiple unsuperseded events for one entity: {rendered}")
        return {key: values[0] for key, values in grouped.items()}

    def history(self, entity_id: str) -> list[StateEvent]:
        return [
            event
            for event in self.load_all()
            if event.payload["entity"]["id"] == entity_id
            or event.payload.get("payload", {}).get("proposal_id") == entity_id
            or event.payload.get("payload", {}).get("task_entity_id") == entity_id
            or (
                entity_id == "task-current"
                and event.event_type == "baseline_adopted"
            )
        ]

    def proposal_decision(self, proposal_id: str) -> str | None:
        decisions = [
            event
            for event in self.load_all()
            if event.event_type == "review_decision"
            and event.payload["payload"]["proposal_id"] == proposal_id
        ]
        if not decisions:
            return None
        latest = max(
            decisions,
            key=lambda event: (event.payload["recorded_at"], event.event_id),
        )
        return str(latest.payload["payload"]["decision"])

    def _event_decision(
        self,
        event_id: str,
        *,
        events: list[StateEvent] | None = None,
    ) -> str | None:
        decisions = [
            event
            for event in (events if events is not None else self.load_all())
            if event.event_type == "review_decision"
            and event.payload["payload"].get("reviewed_event_id") == event_id
        ]
        if not decisions:
            return None
        latest = max(
            decisions,
            key=lambda event: (event.payload["recorded_at"], event.event_id),
        )
        return str(latest.payload["payload"]["decision"])

    def event_decision(self, event_id: str) -> str | None:
        self.get(event_id)
        return self._event_decision(event_id)

    def record_review(
        self,
        *,
        proposal_id: str,
        decision: str,
        reviewer: str,
        reason: str = "",
        reviewed_event_id: str | None = None,
        reviewed_event_sha256: str | None = None,
    ) -> Path:
        if (reviewed_event_id is None) != (reviewed_event_sha256 is None):
            raise ValueError(
                "reviewed_event_id and reviewed_event_sha256 must be provided together"
            )
        if decision == "reject" and reviewed_event_id is None:
            raise ValueError("reject review requires reviewed event linkage")
        if reviewed_event_id is not None:
            reviewed_event = self.get(reviewed_event_id)
            if reviewed_event.digest != reviewed_event_sha256:
                raise ValueError("reviewed event hash does not match the proposal")
        recorded_at = utc_now()
        suffix = (
            f"{proposal_id}-{decision}-{reviewer}-{reviewed_event_id or ''}-"
            f"{reviewed_event_sha256 or ''}-{recorded_at}"
        )
        from scripts.artifact_io import sha256_text

        event_id = f"review-{sha256_text(suffix)[:24]}"
        event = StateEvent.from_mapping(
            {
                "schema_version": 1,
                "event_id": event_id,
                "event_type": "review_decision",
                "entity": {"kind": "proposal", "id": proposal_id, "module": "state_handoff"},
                "occurred_at": recorded_at,
                "recorded_at": recorded_at,
                "summary": f"{decision} proposal {proposal_id}",
                "payload": {
                    "proposal_id": proposal_id,
                    "decision": decision,
                    "reviewer": reviewer,
                    "reason": reason,
                    **(
                        {
                            "reviewed_event_id": reviewed_event_id,
                            "reviewed_event_sha256": reviewed_event_sha256,
                        }
                        if reviewed_event_id is not None
                        else {}
                    ),
                },
                "evidence": [],
                "supersedes": [],
                "review": {"required": False, "reason_codes": [], "status": "not_required"},
            },
            **({"schema_path": self.schema_path} if self.schema_path else {}),
        )
        return self.record(event)


def event_map(events: Iterable[StateEvent]) -> dict[str, dict[str, Any]]:
    return {event.event_id: event.payload for event in events}
