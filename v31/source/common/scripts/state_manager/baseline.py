from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, sha256_text

from .models import ROOT, StateEvent


def _section(text: str, heading: str) -> str:
    match = re.search(rf"(?m)^{re.escape(heading)}\s*$", text)
    if not match:
        raise ValueError(f"required Markdown section is missing: {heading}")
    next_heading = re.search(r"(?m)^## ", text[match.end() :])
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end].strip()


def _list_items(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        if bullet:
            if current:
                items.append(" ".join(current).strip())
            current = [bullet.group(1).strip()]
        elif current and line.strip() and not line.lstrip().startswith("#"):
            current.append(line.strip())
    if current:
        items.append(" ".join(current).strip())
    return items


def _task_payload(text: str) -> dict[str, object]:
    if START_MARKER_TEXT in text:
        raise ValueError("current task is already a managed projection")
    objective = _section(text, "## Objective")
    step = _section(text, "## One Executable Step")
    done = _list_items(_section(text, "## Done When"))
    payload: dict[str, object] = {
        "objective": objective,
        "one_executable_step": step,
        "done_when": done,
        "phase": "active",
    }
    submission_heading = "## Submission Boundary"
    if re.search(rf"(?m)^{re.escape(submission_heading)}\s*$", text):
        payload["submission_boundary"] = _section(text, submission_heading)
    optional = {
        "## Current Evidence Snapshot": "current_evidence",
        "## Constraints": "constraints",
        "## Authoritative References": "authoritative_references",
    }
    for heading, key in optional.items():
        if re.search(rf"(?m)^{re.escape(heading)}\s*$", text):
            payload[key] = _list_items(_section(text, heading))
    return payload


START_MARKER_TEXT = "<!-- state-handoff:start current_task -->"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "current-state"


def _current_gate_payload(text: str) -> dict[str, object]:
    match = re.search(
        r"(?ms)^(### Current Gate[^\n]*)\s*$\s*(.*?)(?=^### |^## |\Z)",
        text,
    )
    if not match:
        raise ValueError("current state has no Current Gate subsection")
    preceding = text[: match.start()]
    sections = list(re.finditer(r"(?m)^## (.+)$", preceding))
    if not sections:
        raise ValueError("Current Gate is not inside a level-2 section")
    section_heading = f"## {sections[-1].group(1).strip()}"
    body = match.group(2).strip()
    facts_body = re.split(
        r"(?m)^(?:Next action:|<!-- state-handoff:end )",
        body,
        maxsplit=1,
    )[0]
    facts = _list_items(facts_body)
    if not facts:
        raise ValueError("Current Gate has no bullet facts")
    next_action_match = re.search(r"(?m)^Next action:\s*(.+)$", body)
    payload: dict[str, object] = {
        "block_id": f"{_slug(sections[-1].group(1))}-current-gate",
        "section": section_heading,
        "source_heading": match.group(1).strip(),
        "title": match.group(1).removeprefix("### ").strip(),
        "facts": facts,
    }
    if next_action_match:
        payload["next_action"] = next_action_match.group(1).strip()
    return payload


def build_baseline_event(project_root: Path = ROOT) -> StateEvent:
    root = project_root.resolve()
    task_path = root / "tasks" / "current_task.md"
    state_path = root / "docs" / "02_CURRENT_STATE.md"
    task_text = task_path.read_text(encoding="utf-8")
    state_text = state_path.read_text(encoding="utf-8")
    task_hash = sha256_file(task_path)
    state_hash = sha256_file(state_path)
    digest = sha256_text(f"{task_hash}:{state_hash}")
    latest_mtime = max(task_path.stat().st_mtime, state_path.stat().st_mtime)
    recorded_at = datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    date_match = re.search(r"(?m)^### Current Gate[^\n]*(\d{4}-\d{2}-\d{2})", state_text)
    occurred_at = f"{date_match.group(1)}T00:00:00+08:00" if date_match else recorded_at
    return StateEvent.from_mapping(
        {
            "schema_version": 1,
            "event_id": f"baseline-{digest[:24]}",
            "event_type": "baseline_adopted",
            "entity": {"kind": "state", "id": "initial-managed-baseline", "module": "state_handoff"},
            "occurred_at": occurred_at,
            "recorded_at": recorded_at,
            "summary": "Adopt the current task and current-gate block as the initial managed baseline.",
            "payload": {
                "task": _task_payload(task_text),
                "state_blocks": [_current_gate_payload(state_text)],
            },
            "evidence": [
                {
                    "locator": "tasks/current_task.md",
                    "sha256": task_hash,
                    "authority": "repository_document",
                    "observed_at": recorded_at,
                },
                {
                    "locator": "docs/02_CURRENT_STATE.md",
                    "sha256": state_hash,
                    "authority": "repository_document",
                    "observed_at": recorded_at,
                },
            ],
            "supersedes": [],
            "review": {
                "required": True,
                "reason_codes": ["initial_managed_view_adoption"],
                "status": "pending",
            },
        }
    )
